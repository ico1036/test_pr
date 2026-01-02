"""Dependency analysis for Multi-PR Orchestration."""

from typing import List, Dict, Set, Tuple
from collections import defaultdict

from ..models import PRNode, PRStatus


class DependencyAnalyzer:
    """
    Analyzes dependencies between PRs for optimal ordering.

    Dependencies are determined by:
    1. Explicit branch dependencies (PR A's base is PR B's branch)
    2. File overlap (PRs touching same files should merge sequentially)
    """

    def __init__(self):
        self._graph: Dict[int, Set[int]] = defaultdict(set)  # PR -> depends on
        self._reverse_graph: Dict[int, Set[int]] = defaultdict(set)  # PR -> depended by

    def build_dependency_graph(self, prs: List[PRNode]) -> None:
        """
        Build dependency graph from list of PRs.

        Args:
            prs: List of PRNode objects
        """
        self._graph.clear()
        self._reverse_graph.clear()

        pr_by_branch = {pr.branch: pr.pr_number for pr in prs}

        for pr in prs:
            # Check if this PR's base is another PR's branch
            if pr.base in pr_by_branch:
                dependency = pr_by_branch[pr.base]
                self._graph[pr.pr_number].add(dependency)
                self._reverse_graph[dependency].add(pr.pr_number)

            # Add explicit dependencies
            for dep in pr.depends_on:
                self._graph[pr.pr_number].add(dep)
                self._reverse_graph[dep].add(pr.pr_number)

    def topological_sort(self, prs: List[PRNode]) -> List[int]:
        """
        Return PRs in topological order (dependencies first).

        Uses Kahn's algorithm for topological sorting.

        Args:
            prs: List of PRNode objects

        Returns:
            List of PR numbers in merge order

        Raises:
            ValueError: If circular dependency detected
        """
        self.build_dependency_graph(prs)

        pr_numbers = {pr.pr_number for pr in prs}
        in_degree = {pr: 0 for pr in pr_numbers}

        # Calculate in-degrees
        for pr in pr_numbers:
            for dep in self._graph[pr]:
                if dep in pr_numbers:
                    in_degree[pr] += 1

        # Start with PRs that have no dependencies
        queue = [pr for pr, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # Sort by PR number for deterministic ordering
            queue.sort()
            current = queue.pop(0)
            result.append(current)

            # Reduce in-degree for dependent PRs
            for dependent in self._reverse_graph[current]:
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        if len(result) != len(pr_numbers):
            # Circular dependency detected
            remaining = pr_numbers - set(result)
            raise ValueError(f"Circular dependency detected among PRs: {remaining}")

        return result

    def get_parallel_groups(self, prs: List[PRNode]) -> List[List[int]]:
        """
        Group PRs that can be reviewed in parallel.

        PRs in the same group have no dependencies on each other.

        Args:
            prs: List of PRNode objects

        Returns:
            List of groups, where each group can run in parallel
        """
        self.build_dependency_graph(prs)

        pr_numbers = {pr.pr_number for pr in prs}
        processed = set()
        groups = []

        while len(processed) < len(pr_numbers):
            # Find all PRs whose dependencies are all processed
            current_group = []

            for pr_num in pr_numbers:
                if pr_num in processed:
                    continue

                deps = self._graph[pr_num] & pr_numbers
                if deps <= processed:
                    current_group.append(pr_num)

            if not current_group:
                # Should not happen if no circular deps
                remaining = pr_numbers - processed
                raise ValueError(f"Cannot resolve dependencies for PRs: {remaining}")

            current_group.sort()
            groups.append(current_group)
            processed.update(current_group)

        return groups

    def get_dependencies(self, pr_number: int) -> Set[int]:
        """Get direct dependencies of a PR."""
        return self._graph.get(pr_number, set()).copy()

    def get_dependents(self, pr_number: int) -> Set[int]:
        """Get PRs that depend on this PR."""
        return self._reverse_graph.get(pr_number, set()).copy()

    def is_blocked(self, pr_number: int, merged_prs: Set[int]) -> bool:
        """
        Check if a PR is blocked by unmerged dependencies.

        Args:
            pr_number: PR to check
            merged_prs: Set of already merged PR numbers

        Returns:
            True if blocked by dependencies
        """
        deps = self._graph.get(pr_number, set())
        return bool(deps - merged_prs)
