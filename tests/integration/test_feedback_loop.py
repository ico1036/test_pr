"""Integration tests for the feedback loop.

These tests create real PRs and verify the full cycle:
Review → Fix → Re-review → Merge

Requirements:
- GITHUB_TOKEN environment variable
- Write access to the test repository
"""

import asyncio
import os
import subprocess
import tempfile
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import pytest

# Test configuration
TEST_REPO = "ico1036/test_pr"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")


@dataclass
class TestCase:
    """A test case for the feedback loop."""
    name: str
    filename: str
    buggy_code: str
    expected_result: str  # "merged", "ready_to_merge", "unfixable", etc.
    description: str


# Test cases - using production-like filenames to avoid false positive detection
TEST_CASES = [
    TestCase(
        name="sql_injection",
        filename="user_repository.py",
        buggy_code='''"""User repository for database operations."""

def get_user_by_id(user_id: str) -> str:
    """Fetch user from database by ID."""
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    return query
''',
        expected_result="merged",
        description="SQL injection should be fixed with parameterized query",
    ),
    TestCase(
        name="command_injection",
        filename="shell_executor.py",
        buggy_code='''"""Shell command executor utility."""
import subprocess

def execute_command(user_input: str) -> str:
    """Execute a shell command with user input."""
    result = subprocess.run(f"echo {user_input}", shell=True, capture_output=True)
    return result.stdout.decode()
''',
        expected_result="merged",
        description="Command injection should be fixed with list args",
    ),
    TestCase(
        name="division_by_zero",
        filename="math_utils.py",
        buggy_code='''"""Mathematical utility functions."""

def calculate_ratio(numerator: int, denominator: int) -> float:
    """Calculate the ratio of two numbers."""
    return numerator / denominator
''',
        expected_result="merged",
        description="Division by zero should be fixed with check",
    ),
    TestCase(
        name="clean_code",
        filename="safe_operations.py",
        buggy_code='''"""Safe mathematical operations."""

def add_numbers(a: int, b: int) -> int:
    """Add two numbers safely."""
    return a + b


def multiply_numbers(a: int, b: int) -> int:
    """Multiply two numbers safely."""
    return a * b
''',
        expected_result="merged",  # auto_merge=True, so clean code gets merged
        description="Clean code should pass without fixes and get merged",
    ),
]


def run_git_command(cmd: list, cwd: str) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def create_test_branch(test_case: TestCase, repo_dir: str) -> str:
    """Create a test branch with buggy code."""
    branch_name = f"integration-test/{test_case.name}-{int(time.time())}"

    # Create and checkout branch
    run_git_command(["git", "checkout", "-b", branch_name], repo_dir)

    # Write buggy file
    test_dir = Path(repo_dir) / "integration_tests"
    test_dir.mkdir(exist_ok=True)

    file_path = test_dir / test_case.filename
    file_path.write_text(test_case.buggy_code)

    # Commit and push
    run_git_command(["git", "add", str(file_path)], repo_dir)
    run_git_command(
        ["git", "commit", "-m", f"Integration test: {test_case.name}"],
        repo_dir
    )
    run_git_command(["git", "push", "-u", "origin", branch_name], repo_dir)

    return branch_name


def create_pr(branch_name: str, test_case: TestCase, repo_dir: str) -> int:
    """Create a PR and return the PR number."""
    result = subprocess.run(
        [
            "gh", "pr", "create",
            "--title", f"[Integration Test] {test_case.name}",
            "--body", test_case.description,
            "--base", "main",
            "--head", branch_name,
        ],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )

    # Extract PR number from URL
    pr_url = result.stdout.strip()
    pr_number = int(pr_url.split("/")[-1])
    return pr_number


def run_autofix(repo: str, pr_number: int, repo_dir: str) -> tuple[str, list]:
    """Run autofix and return (result, statuses)."""
    from review_agent.pipeline import run_feedback_loop_sync, LoopConfig, LoopResult

    config = LoopConfig(
        max_iterations=3,
        auto_fix=True,
        auto_merge=True,
        min_severity_to_fix="medium",
        working_dir=repo_dir,
    )

    result, statuses = run_feedback_loop_sync(
        repo=repo,
        pr_number=pr_number,
        config=config,
        github_token=GITHUB_TOKEN,
    )

    return result.value, statuses


def cleanup_branch(branch_name: str, repo_dir: str):
    """Delete the test branch."""
    run_git_command(["git", "checkout", "main"], repo_dir)
    run_git_command(["git", "branch", "-D", branch_name], repo_dir)
    run_git_command(["git", "push", "origin", "--delete", branch_name], repo_dir)


class TestFeedbackLoopIntegration:
    """Integration tests for the feedback loop."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        if not GITHUB_TOKEN:
            pytest.skip("GITHUB_TOKEN not set")

        self.repo_dir = os.getcwd()

        # Ensure we're on main
        run_git_command(["git", "checkout", "main"], self.repo_dir)
        run_git_command(["git", "pull", "origin", "main"], self.repo_dir)

    @pytest.mark.parametrize("test_case", TEST_CASES, ids=[tc.name for tc in TEST_CASES])
    def test_feedback_loop(self, test_case: TestCase):
        """Test the feedback loop with various bug types."""
        branch_name = None

        try:
            # Create test branch and PR
            print(f"\n{'='*60}")
            print(f"TEST: {test_case.name}")
            print(f"{'='*60}")
            print(f"Description: {test_case.description}")
            print(f"Expected result: {test_case.expected_result}")

            branch_name = create_test_branch(test_case, self.repo_dir)
            print(f"Created branch: {branch_name}")

            pr_number = create_pr(branch_name, test_case, self.repo_dir)
            print(f"Created PR: #{pr_number}")

            # Run autofix
            print(f"\nRunning autofix...")
            result, statuses = run_autofix(TEST_REPO, pr_number, self.repo_dir)

            print(f"\nResult: {result}")
            print(f"Iterations: {len(statuses)}")
            for s in statuses:
                print(f"  [{s.iteration}] found:{s.issues_found} fixed:{s.issues_fixed}")

            # Verify result
            assert result == test_case.expected_result, \
                f"Expected {test_case.expected_result}, got {result}"

            print(f"\n✅ TEST PASSED: {test_case.name}")

        except Exception as e:
            print(f"\n❌ TEST FAILED: {test_case.name}")
            print(f"Error: {e}")
            raise

        finally:
            # Cleanup (only delete branch if not merged)
            if branch_name:
                try:
                    cleanup_branch(branch_name, self.repo_dir)
                except Exception:
                    pass  # Branch might be deleted after merge


def run_single_test(test_name: str):
    """Run a single test case by name."""
    test_case = next((tc for tc in TEST_CASES if tc.name == test_name), None)
    if not test_case:
        print(f"Test case not found: {test_name}")
        print(f"Available: {[tc.name for tc in TEST_CASES]}")
        return

    repo_dir = os.getcwd()
    branch_name = None

    try:
        print(f"\n{'='*60}")
        print(f"TEST: {test_case.name}")
        print(f"{'='*60}")

        # Checkout main
        run_git_command(["git", "checkout", "main"], repo_dir)
        run_git_command(["git", "pull", "origin", "main"], repo_dir)

        branch_name = create_test_branch(test_case, repo_dir)
        print(f"Created branch: {branch_name}")

        pr_number = create_pr(branch_name, test_case, repo_dir)
        print(f"Created PR: #{pr_number}")

        print(f"\nRunning autofix...")
        result, statuses = run_autofix(TEST_REPO, pr_number, repo_dir)

        print(f"\n{'='*60}")
        print(f"RESULT: {result}")
        print(f"Expected: {test_case.expected_result}")
        print(f"{'='*60}")

        if result == test_case.expected_result:
            print("✅ PASSED")
        else:
            print("❌ FAILED")

    finally:
        if branch_name:
            try:
                cleanup_branch(branch_name, repo_dir)
            except Exception:
                pass


def run_all_tests():
    """Run all integration tests."""
    results = []

    for test_case in TEST_CASES:
        try:
            run_single_test(test_case.name)
            results.append((test_case.name, "PASSED"))
        except Exception as e:
            results.append((test_case.name, f"FAILED: {e}"))

    print(f"\n{'='*60}")
    print("INTEGRATION TEST SUMMARY")
    print(f"{'='*60}")
    for name, status in results:
        icon = "✅" if status == "PASSED" else "❌"
        print(f"  {icon} {name}: {status}")

    passed = sum(1 for _, s in results if s == "PASSED")
    print(f"\nTotal: {passed}/{len(results)} passed")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        run_single_test(sys.argv[1])
    else:
        run_all_tests()
