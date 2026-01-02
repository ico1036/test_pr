"""Data models for Phase 3: TDD-Based Test Generation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict
from datetime import datetime


class TestType(Enum):
    """Types of generated tests."""
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"


class TestCategory(Enum):
    """Test case categories."""
    HAPPY_PATH = "happy_path"      # Normal successful execution
    EDGE_CASE = "edge_case"        # Boundary values, empty, null
    ERROR_CASE = "error_case"      # Exception handling, error paths
    REGRESSION = "regression"      # Tests for discovered issues


@dataclass
class GeneratedTest:
    """A single generated test file."""
    file_path: str                    # e.g., tests/test_new_feature.py
    content: str                      # Test code content
    covers_functions: List[str]       # Functions this test covers
    covers_issues: List[int] = field(default_factory=list)  # Issue IDs covered
    test_type: TestType = TestType.UNIT
    categories: List[TestCategory] = field(default_factory=list)
    test_count: int = 0               # Number of test cases in file

    def __post_init__(self):
        # Count test functions if not set
        if self.test_count == 0:
            self.test_count = self.content.count("def test_")


@dataclass
class CoverageResult:
    """Result of running tests with coverage."""
    total_coverage: float             # Overall codebase coverage %
    new_code_coverage: float          # Coverage for PR changes only %
    uncovered_lines: Dict[str, List[int]] = field(default_factory=dict)  # file -> lines
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    test_duration_seconds: float = 0.0
    coverage_report_path: Optional[str] = None

    @property
    def all_tests_passed(self) -> bool:
        return self.tests_failed == 0

    @property
    def total_tests(self) -> int:
        return self.tests_passed + self.tests_failed + self.tests_skipped


@dataclass
class MergeDecision:
    """Final decision on whether to approve merge."""
    approved: bool
    reason: str
    coverage: Optional[CoverageResult] = None
    conditions_met: Dict[str, bool] = field(default_factory=dict)
    generated_tests_count: int = 0
    blocking_issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """Generate human-readable summary."""
        status = "✅ APPROVED" if self.approved else "❌ BLOCKED"
        lines = [f"## Merge Decision: {status}", "", self.reason, ""]

        if self.conditions_met:
            lines.append("### Conditions")
            for cond, met in self.conditions_met.items():
                icon = "✅" if met else "❌"
                lines.append(f"- {icon} {cond}")

        if self.blocking_issues:
            lines.append("")
            lines.append("### Blocking Issues")
            for issue in self.blocking_issues:
                lines.append(f"- {issue}")

        if self.recommendations:
            lines.append("")
            lines.append("### Recommendations")
            for rec in self.recommendations:
                lines.append(f"- {rec}")

        return "\n".join(lines)


@dataclass
class TestGenConfig:
    """Configuration for test generation."""
    # Test generation settings
    min_tests_per_function: int = 3   # happy, edge, error
    include_regression_tests: bool = True
    follow_existing_patterns: bool = True

    # Test framework
    test_framework: str = "pytest"    # pytest, unittest, jest
    async_support: bool = True

    # Coverage settings
    coverage_tool: str = "pytest-cov"
    coverage_report_format: str = "json"

    # File patterns
    test_file_pattern: str = "test_{name}.py"
    test_dir: str = "tests"
