"""Tests for Phase 2: Multi-PR Orchestration.

Following the testing philosophy from CLAUDE.md:
- Client-perspective behavior verification
- Given-When-Then structure
- Minimal mocking (only external APIs)
"""

import pytest
from datetime import datetime

from review_agent.models import PRNode, PRStatus, OrchestratorConfig, OrchestrationPlan
from review_agent.orchestrator.dependency import DependencyAnalyzer
from review_agent.orchestrator.conflict import ConflictPredictor


class TestDependencyAnalyzer:
    """Tests for dependency graph analysis."""

    def test_topological_sort_independent_prs(self):
        """Given PRs with no dependencies, should return them in PR number order."""
        # Given
        prs = [
            PRNode(pr_number=3, branch="feature-c", base="main", changed_files=["c.py"]),
            PRNode(pr_number=1, branch="feature-a", base="main", changed_files=["a.py"]),
            PRNode(pr_number=2, branch="feature-b", base="main", changed_files=["b.py"]),
        ]

        # When
        analyzer = DependencyAnalyzer()
        order = analyzer.topological_sort(prs)

        # Then - should be sorted by PR number when no dependencies
        assert order == [1, 2, 3]

    def test_topological_sort_chain_dependency(self):
        """Given chained PR dependencies, should return in dependency order."""
        # Given - PR 3 depends on PR 2, PR 2 depends on PR 1
        prs = [
            PRNode(pr_number=1, branch="feature-a", base="main", changed_files=["a.py"]),
            PRNode(pr_number=2, branch="feature-b", base="feature-a", changed_files=["b.py"]),
            PRNode(pr_number=3, branch="feature-c", base="feature-b", changed_files=["c.py"]),
        ]

        # When
        analyzer = DependencyAnalyzer()
        order = analyzer.topological_sort(prs)

        # Then - should respect dependency order
        assert order.index(1) < order.index(2) < order.index(3)

    def test_topological_sort_circular_dependency_raises(self):
        """Given circular dependencies, should raise ValueError."""
        # Given - PR 1 -> PR 2 -> PR 1 (circular)
        prs = [
            PRNode(pr_number=1, branch="feature-a", base="feature-b", changed_files=["a.py"]),
            PRNode(pr_number=2, branch="feature-b", base="feature-a", changed_files=["b.py"]),
        ]

        # When/Then
        analyzer = DependencyAnalyzer()
        with pytest.raises(ValueError, match="Circular dependency"):
            analyzer.topological_sort(prs)

    def test_get_parallel_groups_independent(self):
        """Given independent PRs, should group them all together."""
        # Given
        prs = [
            PRNode(pr_number=1, branch="feature-a", base="main", changed_files=["a.py"]),
            PRNode(pr_number=2, branch="feature-b", base="main", changed_files=["b.py"]),
            PRNode(pr_number=3, branch="feature-c", base="main", changed_files=["c.py"]),
        ]

        # When
        analyzer = DependencyAnalyzer()
        groups = analyzer.get_parallel_groups(prs)

        # Then - all in one group
        assert len(groups) == 1
        assert set(groups[0]) == {1, 2, 3}

    def test_get_parallel_groups_with_dependencies(self):
        """Given dependencies, should create sequential groups."""
        # Given - PR 2 depends on PR 1
        prs = [
            PRNode(pr_number=1, branch="feature-a", base="main", changed_files=["a.py"]),
            PRNode(pr_number=2, branch="feature-b", base="feature-a", changed_files=["b.py"]),
            PRNode(pr_number=3, branch="feature-c", base="main", changed_files=["c.py"]),
        ]

        # When
        analyzer = DependencyAnalyzer()
        groups = analyzer.get_parallel_groups(prs)

        # Then - PR 1 and 3 in first group, PR 2 in second
        assert len(groups) == 2
        assert set(groups[0]) == {1, 3}
        assert set(groups[1]) == {2}


class TestConflictPredictor:
    """Tests for conflict prediction."""

    def test_predict_conflicts_no_overlap(self):
        """Given PRs with different files, should predict no conflict."""
        # Given
        prs = [
            PRNode(pr_number=1, branch="feature-a", base="main", changed_files=["a.py", "b.py"]),
            PRNode(pr_number=2, branch="feature-b", base="main", changed_files=["c.py", "d.py"]),
        ]

        # When
        predictor = ConflictPredictor()
        has_conflict, files = predictor.predict_conflicts(1, 2, prs)

        # Then
        assert has_conflict is False
        assert files == []

    def test_predict_conflicts_with_overlap(self):
        """Given PRs with overlapping files, should predict conflict."""
        # Given
        prs = [
            PRNode(pr_number=1, branch="feature-a", base="main", changed_files=["shared.py", "a.py"]),
            PRNode(pr_number=2, branch="feature-b", base="main", changed_files=["shared.py", "b.py"]),
        ]

        # When
        predictor = ConflictPredictor()
        has_conflict, files = predictor.predict_conflicts(1, 2, prs)

        # Then
        assert has_conflict is True
        assert "shared.py" in files

    def test_get_all_conflict_pairs(self):
        """Given multiple PRs, should find all conflict pairs."""
        # Given - PR 1 & 2 conflict on shared.py, PR 2 & 3 conflict on other.py
        prs = [
            PRNode(pr_number=1, branch="a", base="main", changed_files=["shared.py"]),
            PRNode(pr_number=2, branch="b", base="main", changed_files=["shared.py", "other.py"]),
            PRNode(pr_number=3, branch="c", base="main", changed_files=["other.py"]),
        ]

        # When
        predictor = ConflictPredictor()
        conflicts = predictor.get_all_conflict_pairs(prs)

        # Then
        assert len(conflicts) == 2
        pr_pairs = [(a, b) for a, b, _ in conflicts]
        assert (1, 2) in pr_pairs
        assert (2, 3) in pr_pairs

    def test_conflict_free_order_respects_creation_time(self):
        """Given conflicting PRs, should order by creation time within conflict groups."""
        # Given - two PRs touching same file, older should come first
        older_time = datetime(2024, 1, 1)
        newer_time = datetime(2024, 1, 2)

        prs = [
            PRNode(pr_number=2, branch="b", base="main", changed_files=["shared.py"], created_at=newer_time),
            PRNode(pr_number=1, branch="a", base="main", changed_files=["shared.py"], created_at=older_time),
        ]

        # When
        predictor = ConflictPredictor()
        order = predictor.get_conflict_free_order(prs, [2, 1])

        # Then - older PR (1) should come first despite base_order
        assert order[0] == 1
        assert order[1] == 2


class TestPRModels:
    """Tests for PR data models."""

    def test_pr_node_is_ready_for_merge(self):
        """Given PR with REVIEW_PASSED status, should be ready for merge."""
        # Given
        pr = PRNode(pr_number=1, branch="feature", base="main")
        pr.status = PRStatus.REVIEW_PASSED

        # Then
        assert pr.is_ready_for_merge is True

    def test_pr_node_is_blocked(self):
        """Given PR with BLOCKED status, should report as blocked."""
        # Given
        pr = PRNode(pr_number=1, branch="feature", base="main")
        pr.status = PRStatus.BLOCKED

        # Then
        assert pr.is_blocked is True

    def test_orchestration_plan_counts(self):
        """Given orchestration plan, should correctly count PRs."""
        # Given
        plan = OrchestrationPlan(
            pr_order=[1, 2, 3, 4],
            parallel_groups=[[1, 2], [3, 4]],
            conflict_pairs=[(1, 2)]
        )

        # Then
        assert plan.total_prs == 4
        assert plan.estimated_reviews == 4


class TestOrchestratorConfig:
    """Tests for orchestrator configuration."""

    def test_default_config_values(self):
        """Default config should have sensible values."""
        # When
        config = OrchestratorConfig()

        # Then
        assert config.merge_method == "squash"
        assert config.auto_merge is False
        assert config.max_parallel_reviews == 5
        assert config.require_review_pass is True
