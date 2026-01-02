"""Conflict prediction for Multi-PR Orchestration."""

from typing import List, Dict, Set, Tuple
from collections import defaultdict
from pathlib import Path

from ..models import PRNode


class ConflictPredictor:
    """
    Predicts potential merge conflicts between PRs.

    Conflicts are predicted based on:
    1. Overlapping file changes
    2. Directory-level overlap (rough indicator)
    3. Same logical component changes
    """

    def __init__(self):
        self._file_to_prs: Dict[str, Set[int]] = defaultdict(set)
        self._dir_to_prs: Dict[str, Set[int]] = defaultdict(set)

    def analyze(self, prs: List[PRNode]) -> None:
        """
        Analyze PRs for potential conflicts.

        Args:
            prs: List of PRNode objects
        """
        self._file_to_prs.clear()
        self._dir_to_prs.clear()

        for pr in prs:
            for file_path in pr.changed_files:
                self._file_to_prs[file_path].add(pr.pr_number)

                # Track directory-level changes
                path = Path(file_path)
                for parent in path.parents:
                    parent_str = str(parent)
                    if parent_str != ".":
                        self._dir_to_prs[parent_str].add(pr.pr_number)

    def predict_conflicts(
        self,
        pr_a: int,
        pr_b: int,
        prs: List[PRNode]
    ) -> Tuple[bool, List[str]]:
        """
        Predict if two PRs will have merge conflicts.

        Args:
            pr_a: First PR number
            pr_b: Second PR number
            prs: List of all PRNode objects

        Returns:
            Tuple of (has_conflict, conflicting_files)
        """
        pr_map = {pr.pr_number: pr for pr in prs}

        if pr_a not in pr_map or pr_b not in pr_map:
            return False, []

        files_a = set(pr_map[pr_a].changed_files)
        files_b = set(pr_map[pr_b].changed_files)

        overlapping = files_a & files_b
        return bool(overlapping), list(overlapping)

    def get_all_conflict_pairs(self, prs: List[PRNode]) -> List[Tuple[int, int, List[str]]]:
        """
        Get all pairs of PRs that may conflict.

        Args:
            prs: List of PRNode objects

        Returns:
            List of (pr_a, pr_b, conflicting_files) tuples
        """
        self.analyze(prs)
        conflicts = []

        pr_numbers = [pr.pr_number for pr in prs]
        n = len(pr_numbers)

        for i in range(n):
            for j in range(i + 1, n):
                has_conflict, files = self.predict_conflicts(
                    pr_numbers[i],
                    pr_numbers[j],
                    prs
                )
                if has_conflict:
                    conflicts.append((pr_numbers[i], pr_numbers[j], files))

        return conflicts

    def get_conflict_free_order(
        self,
        prs: List[PRNode],
        base_order: List[int]
    ) -> List[int]:
        """
        Reorder PRs to minimize conflict risk.

        PRs with file overlaps should be merged sequentially
        in order of creation (oldest first).

        Args:
            prs: List of PRNode objects
            base_order: Initial ordering (from dependency analysis)

        Returns:
            Reordered list of PR numbers
        """
        self.analyze(prs)
        pr_map = {pr.pr_number: pr for pr in prs}

        # Group PRs by overlapping files
        conflict_groups = self._find_conflict_groups(prs)

        # Sort within each conflict group by creation time
        for group in conflict_groups:
            group.sort(key=lambda pr: pr_map[pr].created_at)

        # Merge groups back respecting base_order
        result = []
        used = set()

        for pr_num in base_order:
            if pr_num in used:
                continue

            # Find the conflict group containing this PR
            for group in conflict_groups:
                if pr_num in group:
                    # Add entire group in order
                    for g_pr in group:
                        if g_pr not in used:
                            result.append(g_pr)
                            used.add(g_pr)
                    break
            else:
                # PR not in any conflict group
                result.append(pr_num)
                used.add(pr_num)

        return result

    def _find_conflict_groups(self, prs: List[PRNode]) -> List[List[int]]:
        """
        Find groups of PRs that have file overlaps.

        Uses union-find to group PRs with transitive overlaps.
        """
        pr_numbers = [pr.pr_number for pr in prs]

        # Union-Find data structure
        parent = {pr: pr for pr in pr_numbers}

        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Union PRs that share files
        for file_path, pr_set in self._file_to_prs.items():
            pr_list = list(pr_set)
            for i in range(1, len(pr_list)):
                union(pr_list[0], pr_list[i])

        # Group by root
        groups: Dict[int, List[int]] = defaultdict(list)
        for pr in pr_numbers:
            groups[find(pr)].append(pr)

        return [g for g in groups.values() if len(g) > 1]

    def get_files_by_pr(self, pr_number: int, prs: List[PRNode]) -> List[str]:
        """Get list of changed files for a PR."""
        for pr in prs:
            if pr.pr_number == pr_number:
                return pr.changed_files
        return []

    def get_prs_by_file(self, file_path: str) -> Set[int]:
        """Get all PRs that modify a specific file."""
        return self._file_to_prs.get(file_path, set()).copy()
