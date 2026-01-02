"""Tests for Phase 3: TDD-Based Test Generation.

Following the testing philosophy from CLAUDE.md:
- Client-perspective behavior verification
- Given-When-Then structure
- Minimal mocking (only external APIs)
"""

import pytest
from pathlib import Path

from review_agent.models import (
    TestType,
    TestCategory,
    GeneratedTest,
    CoverageResult,
    MergeDecision,
    TestGenConfig,
    ValidatedIssue,
    PotentialIssue,
)
from review_agent.config import MergeRules
from review_agent.pipeline.stage4_coverage import CoverageGate


class TestGeneratedTest:
    """Tests for GeneratedTest model."""

    def test_generated_test_counts_test_functions(self):
        """Given test content with test functions, should count them correctly."""
        # Given
        content = """
import pytest

def test_login_success():
    pass

def test_login_failure():
    pass

def test_logout():
    pass
"""
        # When
        test = GeneratedTest(
            file_path="tests/test_auth.py",
            content=content,
            covers_functions=["login", "logout"],
        )

        # Then
        assert test.test_count == 3

    def test_generated_test_default_type_is_unit(self):
        """Given no test_type specified, should default to unit."""
        # When
        test = GeneratedTest(
            file_path="tests/test_feature.py",
            content="def test_foo(): pass",
            covers_functions=["foo"],
        )

        # Then
        assert test.test_type == TestType.UNIT


class TestCoverageResult:
    """Tests for CoverageResult model."""

    def test_all_tests_passed_when_no_failures(self):
        """Given no failed tests, all_tests_passed should be True."""
        # Given
        result = CoverageResult(
            total_coverage=85.0,
            new_code_coverage=92.0,
            tests_passed=10,
            tests_failed=0,
        )

        # Then
        assert result.all_tests_passed is True

    def test_all_tests_passed_false_when_failures(self):
        """Given failed tests, all_tests_passed should be False."""
        # Given
        result = CoverageResult(
            total_coverage=85.0,
            new_code_coverage=92.0,
            tests_passed=8,
            tests_failed=2,
        )

        # Then
        assert result.all_tests_passed is False

    def test_total_tests_calculation(self):
        """Should correctly calculate total tests."""
        # Given
        result = CoverageResult(
            total_coverage=85.0,
            new_code_coverage=92.0,
            tests_passed=8,
            tests_failed=2,
            tests_skipped=1,
        )

        # Then
        assert result.total_tests == 11


class TestMergeDecision:
    """Tests for MergeDecision model."""

    def test_approved_decision_summary(self):
        """Given approved decision, summary should show approval."""
        # Given
        decision = MergeDecision(
            approved=True,
            reason="All conditions met",
            conditions_met={"all_tests_pass": True, "min_coverage": True},
        )

        # When
        summary = decision.summary()

        # Then
        assert "APPROVED" in summary
        assert "All conditions met" in summary

    def test_blocked_decision_shows_issues(self):
        """Given blocked decision, summary should list blocking issues."""
        # Given
        decision = MergeDecision(
            approved=False,
            reason="Coverage too low",
            blocking_issues=["Coverage 70% < 80%", "2 tests failed"],
        )

        # When
        summary = decision.summary()

        # Then
        assert "BLOCKED" in summary
        assert "Coverage 70% < 80%" in summary
        assert "2 tests failed" in summary


class TestCoverageGate:
    """Tests for CoverageGate."""

    def test_check_conditions_all_passing(self):
        """Given all conditions met, should return all True."""
        # Given
        rules = MergeRules(
            min_total_coverage=80.0,
            min_new_code_coverage=90.0,
        )
        gate = CoverageGate(rules=rules)

        coverage = CoverageResult(
            total_coverage=85.0,
            new_code_coverage=95.0,
            tests_passed=10,
            tests_failed=0,
        )
        issues = []  # No issues

        # When
        conditions = gate._check_conditions(coverage, issues)

        # Then
        assert conditions["all_tests_pass"] is True
        assert conditions["min_total_coverage"] is True
        assert conditions["min_new_code_coverage"] is True
        assert conditions["no_critical_issues"] is True

    def test_check_conditions_coverage_fail(self):
        """Given low coverage, should fail coverage condition."""
        # Given
        rules = MergeRules(min_total_coverage=80.0)
        gate = CoverageGate(rules=rules)

        coverage = CoverageResult(
            total_coverage=70.0,  # Below threshold
            new_code_coverage=95.0,
            tests_passed=10,
            tests_failed=0,
        )

        # When
        conditions = gate._check_conditions(coverage, [])

        # Then
        assert conditions["min_total_coverage"] is False

    def test_check_conditions_critical_issue_blocks(self):
        """Given critical issue, should fail no_critical_issues condition."""
        # Given
        rules = MergeRules(block_on_critical=True)
        gate = CoverageGate(rules=rules)

        coverage = CoverageResult(
            total_coverage=90.0,
            new_code_coverage=95.0,
            tests_passed=10,
            tests_failed=0,
        )

        # Create a critical issue
        potential = PotentialIssue(
            file_path="src/auth.py",
            line_start=10,
            line_end=15,
            issue_type="security",
            severity="critical",
            description="SQL injection",
            code_snippet="cursor.execute(f'SELECT * FROM users WHERE id={user_id}')",
        )
        critical_issue = ValidatedIssue(
            issue=potential,
            is_valid=True,
            confidence=0.95,
        )

        # When
        conditions = gate._check_conditions(coverage, [critical_issue])

        # Then
        assert conditions["no_critical_issues"] is False

    def test_make_decision_approved_when_all_pass(self):
        """Given all conditions pass, should approve."""
        # Given
        rules = MergeRules()
        gate = CoverageGate(rules=rules)

        conditions = {
            "all_tests_pass": True,
            "min_total_coverage": True,
            "min_new_code_coverage": True,
            "no_critical_issues": True,
            "no_high_issues": True,
            "medium_issues_limit": True,
        }
        coverage = CoverageResult(
            total_coverage=90.0,
            new_code_coverage=95.0,
            tests_passed=10,
            tests_failed=0,
        )

        # When
        decision = gate._make_decision(conditions, coverage, generated_tests_count=5)

        # Then
        assert decision.approved is True
        assert "ready for merge" in decision.reason.lower()

    def test_make_decision_blocked_when_condition_fails(self):
        """Given a failing condition, should block."""
        # Given
        rules = MergeRules()
        gate = CoverageGate(rules=rules)

        conditions = {
            "all_tests_pass": False,  # Failed
            "min_total_coverage": True,
            "min_new_code_coverage": True,
            "no_critical_issues": True,
            "no_high_issues": True,
            "medium_issues_limit": True,
        }
        coverage = CoverageResult(
            total_coverage=90.0,
            new_code_coverage=95.0,
            tests_passed=8,
            tests_failed=2,
        )

        # When
        decision = gate._make_decision(conditions, coverage, generated_tests_count=5)

        # Then
        assert decision.approved is False
        assert "all_tests_pass" in decision.reason


class TestMergeRules:
    """Tests for MergeRules configuration."""

    def test_default_merge_rules(self):
        """Default rules should have sensible values."""
        # When
        rules = MergeRules()

        # Then
        assert rules.min_total_coverage == 80.0
        assert rules.min_new_code_coverage == 90.0
        assert rules.block_on_critical is True
        assert rules.block_on_high is True
        assert rules.auto_merge_on_pass is False


class TestTestGenConfig:
    """Tests for TestGenConfig."""

    def test_default_config(self):
        """Default config should have pytest settings."""
        # When
        config = TestGenConfig()

        # Then
        assert config.test_framework == "pytest"
        assert config.min_tests_per_function == 3
        assert config.test_dir == "tests"
