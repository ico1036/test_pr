"""Stage 4: Coverage Gate - Run tests and make merge decision."""

import asyncio
import subprocess
import json
import os
from typing import List, Optional, Dict
from pathlib import Path

from ..models import (
    ValidatedIssue,
    GeneratedTest,
    CoverageResult,
    MergeDecision,
    TestGenConfig,
)
from ..config import MergeRules


class CoverageGate:
    """
    Coverage Gate for Phase 3: TDD-based merge decisions.

    Responsibilities:
    1. Write generated tests to disk
    2. Run tests with coverage
    3. Analyze coverage results
    4. Make merge decision based on rules
    """

    def __init__(
        self,
        rules: Optional[MergeRules] = None,
        config: Optional[TestGenConfig] = None,
        work_dir: Optional[Path] = None,
    ):
        self.rules = rules or MergeRules()
        self.config = config or TestGenConfig()
        self.work_dir = work_dir or Path.cwd()

    async def execute(
        self,
        generated_tests: List[GeneratedTest],
        validated_issues: List[ValidatedIssue],
        changed_files: List[str],
    ) -> MergeDecision:
        """
        Execute the coverage gate pipeline.

        Args:
            generated_tests: Tests from Stage 3
            validated_issues: Issues from Stage 1,2
            changed_files: List of files changed in PR

        Returns:
            MergeDecision with approval status
        """
        print("  [Stage 4] Starting coverage gate...")

        # Step 1: Write generated tests to disk
        written_tests = await self._write_tests(generated_tests)
        print(f"  [Stage 4] Wrote {len(written_tests)} test files")

        # Step 2: Run tests with coverage
        coverage = await self._run_tests_with_coverage(changed_files)
        print(f"  [Stage 4] Tests: {coverage.tests_passed} passed, {coverage.tests_failed} failed")
        print(f"  [Stage 4] Coverage: {coverage.new_code_coverage:.1f}% (new code), {coverage.total_coverage:.1f}% (total)")

        # Step 3: Check conditions and make decision
        conditions = self._check_conditions(coverage, validated_issues)
        decision = self._make_decision(conditions, coverage, len(generated_tests))

        status = "APPROVED" if decision.approved else "BLOCKED"
        print(f"  [Stage 4] Decision: {status}")

        return decision

    async def _write_tests(self, tests: List[GeneratedTest]) -> List[str]:
        """Write generated tests to disk."""
        written = []

        for test in tests:
            try:
                test_path = self.work_dir / test.file_path

                # Create parent directories
                test_path.parent.mkdir(parents=True, exist_ok=True)

                # Write test file
                test_path.write_text(test.content)
                written.append(str(test_path))
                print(f"  [Stage 4] Wrote: {test.file_path}")

            except Exception as e:
                print(f"  [Stage 4] Failed to write {test.file_path}: {e}")

        return written

    async def _run_tests_with_coverage(
        self,
        changed_files: List[str],
    ) -> CoverageResult:
        """Run pytest with coverage and return results."""
        # Build coverage source filter
        source_dirs = set()
        for f in changed_files:
            parts = Path(f).parts
            if parts:
                source_dirs.add(parts[0])

        source_arg = ",".join(source_dirs) if source_dirs else "."

        # Run pytest with coverage
        cmd = [
            "pytest",
            f"--cov={source_arg}",
            "--cov-report=json",
            "--cov-report=term",
            "-v",
            str(self.work_dir / self.config.test_dir)
        ]

        print(f"  [Stage 4] Running: {' '.join(cmd)}")

        try:
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.work_dir)
            )

            stdout, stderr = await result.communicate()
            output = stdout.decode() + stderr.decode()

            # Parse results
            return self._parse_pytest_output(output, changed_files)

        except Exception as e:
            print(f"  [Stage 4] Test execution failed: {e}")
            return CoverageResult(
                total_coverage=0.0,
                new_code_coverage=0.0,
                tests_passed=0,
                tests_failed=1,
            )

    def _parse_pytest_output(
        self,
        output: str,
        changed_files: List[str]
    ) -> CoverageResult:
        """Parse pytest output for coverage and test results."""
        tests_passed = 0
        tests_failed = 0
        tests_skipped = 0
        total_coverage = 0.0
        new_code_coverage = 0.0
        uncovered_lines: Dict[str, List[int]] = {}

        # Parse test results from output
        for line in output.split("\n"):
            if " passed" in line and " failed" not in line:
                # e.g., "5 passed in 1.23s"
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "passed" and i > 0:
                        try:
                            tests_passed = int(parts[i-1])
                        except ValueError:
                            pass
                    if p == "failed" and i > 0:
                        try:
                            tests_failed = int(parts[i-1])
                        except ValueError:
                            pass
                    if p == "skipped" and i > 0:
                        try:
                            tests_skipped = int(parts[i-1])
                        except ValueError:
                            pass

            # Parse coverage summary
            if "TOTAL" in line and "%" in line:
                # e.g., "TOTAL    1234    123    90%"
                parts = line.split()
                for p in parts:
                    if p.endswith("%"):
                        try:
                            total_coverage = float(p.rstrip("%"))
                        except ValueError:
                            pass

        # Try to read detailed coverage from JSON
        coverage_json = self.work_dir / "coverage.json"
        if coverage_json.exists():
            try:
                with open(coverage_json) as f:
                    cov_data = json.load(f)

                # Calculate new code coverage
                new_covered = 0
                new_total = 0

                for file_path, file_data in cov_data.get("files", {}).items():
                    # Check if this file is in changed files
                    is_changed = any(
                        file_path.endswith(cf) or cf.endswith(file_path)
                        for cf in changed_files
                    )

                    if is_changed:
                        missing = file_data.get("missing_lines", [])
                        executed = file_data.get("executed_lines", [])
                        new_total += len(missing) + len(executed)
                        new_covered += len(executed)

                        if missing:
                            uncovered_lines[file_path] = missing

                if new_total > 0:
                    new_code_coverage = (new_covered / new_total) * 100

                # Get total coverage from summary
                total_coverage = cov_data.get("totals", {}).get("percent_covered", total_coverage)

            except Exception as e:
                print(f"  [Stage 4] Failed to parse coverage.json: {e}")

        return CoverageResult(
            total_coverage=total_coverage,
            new_code_coverage=new_code_coverage,
            uncovered_lines=uncovered_lines,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            tests_skipped=tests_skipped,
            coverage_report_path=str(coverage_json) if coverage_json.exists() else None,
        )

    def _check_conditions(
        self,
        coverage: CoverageResult,
        issues: List[ValidatedIssue]
    ) -> Dict[str, bool]:
        """Check all merge conditions."""
        conditions = {}

        # Test conditions
        conditions["all_tests_pass"] = coverage.all_tests_passed

        # Coverage conditions
        conditions["min_total_coverage"] = coverage.total_coverage >= self.rules.min_total_coverage
        conditions["min_new_code_coverage"] = coverage.new_code_coverage >= self.rules.min_new_code_coverage

        # Issue conditions
        critical_issues = [
            i for i in issues
            if i.is_valid and i.issue.severity.lower() == "critical"
        ]
        high_issues = [
            i for i in issues
            if i.is_valid and i.issue.severity.lower() == "high"
        ]
        medium_issues = [
            i for i in issues
            if i.is_valid and i.issue.severity.lower() == "medium"
        ]

        conditions["no_critical_issues"] = len(critical_issues) == 0
        conditions["no_high_issues"] = len(high_issues) == 0 if self.rules.block_on_high else True
        conditions["medium_issues_limit"] = len(medium_issues) <= self.rules.max_medium_issues

        return conditions

    def _make_decision(
        self,
        conditions: Dict[str, bool],
        coverage: CoverageResult,
        generated_tests_count: int
    ) -> MergeDecision:
        """Make final merge decision based on conditions."""
        # All conditions must be met for approval
        approved = all(conditions.values())

        # Build reason
        if approved:
            reason = "All conditions met. PR is ready for merge."
        else:
            failed = [k for k, v in conditions.items() if not v]
            reason = f"Blocked due to failed conditions: {', '.join(failed)}"

        # Build blocking issues list
        blocking = []
        if not conditions.get("all_tests_pass"):
            blocking.append(f"{coverage.tests_failed} tests failed")
        if not conditions.get("min_total_coverage"):
            blocking.append(f"Total coverage {coverage.total_coverage:.1f}% < {self.rules.min_total_coverage}%")
        if not conditions.get("min_new_code_coverage"):
            blocking.append(f"New code coverage {coverage.new_code_coverage:.1f}% < {self.rules.min_new_code_coverage}%")
        if not conditions.get("no_critical_issues"):
            blocking.append("Critical issues found")
        if not conditions.get("no_high_issues"):
            blocking.append("High severity issues found")

        # Build recommendations
        recommendations = []
        if coverage.uncovered_lines:
            recommendations.append("Add tests for uncovered lines")
        if coverage.tests_failed > 0:
            recommendations.append("Fix failing tests before merge")
        if not conditions.get("min_new_code_coverage"):
            recommendations.append("Increase test coverage for new code")

        return MergeDecision(
            approved=approved,
            reason=reason,
            coverage=coverage,
            conditions_met=conditions,
            generated_tests_count=generated_tests_count,
            blocking_issues=blocking,
            recommendations=recommendations,
        )

    async def dry_run(
        self,
        generated_tests: List[GeneratedTest],
        validated_issues: List[ValidatedIssue],
    ) -> dict:
        """
        Dry run - analyze without writing files or running tests.

        Returns summary of what would happen.
        """
        return {
            "would_write_tests": [t.file_path for t in generated_tests],
            "total_test_count": sum(t.test_count for t in generated_tests),
            "covers_functions": list(set(
                fn for t in generated_tests for fn in t.covers_functions
            )),
            "regression_tests": sum(
                1 for t in generated_tests
                if any(c.value == "regression" for c in t.categories)
            ),
            "issues_covered": sum(
                len(t.covers_issues) for t in generated_tests
            ),
            "rules": {
                "min_total_coverage": self.rules.min_total_coverage,
                "min_new_code_coverage": self.rules.min_new_code_coverage,
                "block_on_critical": self.rules.block_on_critical,
                "block_on_high": self.rules.block_on_high,
            }
        }


# Convenience functions
async def run_coverage_gate(
    generated_tests: List[GeneratedTest],
    validated_issues: List[ValidatedIssue],
    changed_files: List[str],
    rules: Optional[MergeRules] = None,
) -> MergeDecision:
    """Run the coverage gate and return merge decision."""
    gate = CoverageGate(rules=rules)
    return await gate.execute(generated_tests, validated_issues, changed_files)


def run_coverage_gate_sync(
    generated_tests: List[GeneratedTest],
    validated_issues: List[ValidatedIssue],
    changed_files: List[str],
    rules: Optional[MergeRules] = None,
) -> MergeDecision:
    """Synchronous wrapper for run_coverage_gate."""
    return asyncio.run(run_coverage_gate(
        generated_tests, validated_issues, changed_files, rules
    ))
