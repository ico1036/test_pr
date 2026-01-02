"""Main PR Orchestrator for Multi-PR management."""

import asyncio
import os
from typing import List, Dict, Optional, Set
from datetime import datetime

from github import Github, GithubException
from github.Repository import Repository as GHRepository

from ..models import (
    PRNode,
    PRStatus,
    MergeResult,
    OrchestratorConfig,
    OrchestrationPlan,
)
from ..config import ReviewConfig
from ..tools import GitHubTool
from ..utils import get_logger
from .dependency import DependencyAnalyzer
from .conflict import ConflictPredictor
from .merge import MergeExecutor


class PROrchestrator:
    """
    Orchestrates review and merge of multiple PRs.

    Features:
    - PR queue management
    - Dependency graph analysis (topological sort)
    - Conflict prediction
    - Optimal merge order determination
    - Parallel review execution
    """

    def __init__(
        self,
        repo: str,
        token: Optional[str] = None,
        config: Optional[OrchestratorConfig] = None
    ):
        """
        Initialize PR Orchestrator.

        Args:
            repo: Repository in format "owner/repo"
            token: GitHub token (defaults to GITHUB_TOKEN env var)
            config: Orchestrator configuration
        """
        self.repo_name = repo
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GitHub token required")

        self.config = config or OrchestratorConfig()
        self.logger = get_logger()

        # Initialize GitHub client
        self.gh = Github(self.token)
        self.repo: GHRepository = self.gh.get_repo(repo)

        # Initialize analyzers
        self.dependency_analyzer = DependencyAnalyzer()
        self.conflict_predictor = ConflictPredictor()
        self.merge_executor = MergeExecutor(self.repo, self.config)

        # PR queue
        self._queue: Dict[int, PRNode] = {}
        self._merged: Set[int] = set()

    async def load_open_prs(self, base: str = "main") -> List[PRNode]:
        """
        Load all open PRs targeting a base branch.

        Args:
            base: Base branch to filter PRs

        Returns:
            List of PRNode objects
        """
        self._queue.clear()

        prs = self.repo.get_pulls(state="open", base=base)

        for pr in prs:
            node = PRNode(
                pr_number=pr.number,
                branch=pr.head.ref,
                base=pr.base.ref,
                changed_files=[f.filename for f in pr.get_files()],
                created_at=pr.created_at,
                updated_at=pr.updated_at,
            )
            self._queue[pr.number] = node

        self.logger.info(f"Loaded {len(self._queue)} open PRs targeting {base}")
        return list(self._queue.values())

    async def analyze(self) -> OrchestrationPlan:
        """
        Analyze loaded PRs and create orchestration plan.

        Returns:
            OrchestrationPlan with optimal ordering
        """
        if not self._queue:
            return OrchestrationPlan(
                pr_order=[],
                parallel_groups=[],
                conflict_pairs=[]
            )

        prs = list(self._queue.values())

        # Get dependency-based order
        try:
            dep_order = self.dependency_analyzer.topological_sort(prs)
        except ValueError as e:
            self.logger.error(f"Dependency analysis failed: {e}")
            # Fall back to creation time order
            dep_order = sorted(
                [pr.pr_number for pr in prs],
                key=lambda n: self._queue[n].created_at
            )

        # Find conflict pairs
        self.conflict_predictor.analyze(prs)
        conflict_pairs = self.conflict_predictor.get_all_conflict_pairs(prs)

        # Update PR nodes with conflict info
        for pr_a, pr_b, files in conflict_pairs:
            self._queue[pr_a].conflicts_with.append(pr_b)
            self._queue[pr_b].conflicts_with.append(pr_a)

        # Get conflict-aware order
        final_order = self.conflict_predictor.get_conflict_free_order(prs, dep_order)

        # Get parallel groups
        parallel_groups = self.dependency_analyzer.get_parallel_groups(prs)

        plan = OrchestrationPlan(
            pr_order=final_order,
            parallel_groups=parallel_groups,
            conflict_pairs=[(a, b) for a, b, _ in conflict_pairs]
        )

        self.logger.info(
            f"Analysis complete: {plan.total_prs} PRs, "
            f"{len(parallel_groups)} parallel groups, "
            f"{len(conflict_pairs)} potential conflicts"
        )

        return plan

    async def review_pr(self, pr_number: int, config: Optional[ReviewConfig] = None) -> dict:
        """
        Run review on a single PR.

        Args:
            pr_number: PR number to review
            config: Review configuration

        Returns:
            Review statistics
        """
        from ..main import run_review

        if pr_number not in self._queue:
            raise ValueError(f"PR #{pr_number} not in queue")

        node = self._queue[pr_number]
        node.status = PRStatus.REVIEWING

        review_config = config or ReviewConfig(
            repo=self.repo_name,
            pr_number=pr_number,
            github_token=self.token
        )

        try:
            stats = await run_review(review_config)
            node.review_result = stats

            # Determine status based on review
            if stats.get("status") == "completed":
                # Check for blocking issues
                # (In real impl, would check issue severities)
                node.status = PRStatus.REVIEW_PASSED
            else:
                node.status = PRStatus.REVIEW_FAILED

            return stats

        except Exception as e:
            self.logger.exception(f"Review failed for PR #{pr_number}")
            node.status = PRStatus.REVIEW_FAILED
            return {"status": "error", "error": str(e)}

    async def review_parallel_group(
        self,
        pr_numbers: List[int],
        config: Optional[ReviewConfig] = None
    ) -> Dict[int, dict]:
        """
        Review multiple PRs in parallel.

        Args:
            pr_numbers: List of PR numbers to review
            config: Base review configuration

        Returns:
            Dict mapping PR number to review stats
        """
        # Limit parallelism
        semaphore = asyncio.Semaphore(self.config.max_parallel_reviews)

        async def limited_review(pr_num: int) -> tuple[int, dict]:
            async with semaphore:
                stats = await self.review_pr(pr_num, config)
                return pr_num, stats

        tasks = [limited_review(pr) for pr in pr_numbers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            pr_num: stats if not isinstance(stats, Exception) else {"error": str(stats)}
            for pr_num, stats in results
        }

    async def execute_plan(
        self,
        plan: OrchestrationPlan,
        review_config: Optional[ReviewConfig] = None,
        merge: bool = False
    ) -> dict:
        """
        Execute an orchestration plan.

        Args:
            plan: The plan to execute
            review_config: Configuration for reviews
            merge: Whether to merge after review

        Returns:
            Execution summary
        """
        results = {
            "reviews": {},
            "merges": [],
            "summary": {
                "total_prs": plan.total_prs,
                "reviewed": 0,
                "passed": 0,
                "failed": 0,
                "merged": 0,
            }
        }

        # Review PRs by parallel groups
        for group in plan.parallel_groups:
            self.logger.info(f"Reviewing parallel group: {group}")

            group_results = await self.review_parallel_group(group, review_config)
            results["reviews"].update(group_results)

            for pr_num, stats in group_results.items():
                results["summary"]["reviewed"] += 1
                if stats.get("status") == "completed":
                    results["summary"]["passed"] += 1
                else:
                    results["summary"]["failed"] += 1

        # Merge if requested
        if merge and self.config.auto_merge:
            ready_prs = [
                pr for pr in plan.pr_order
                if self._queue[pr].status == PRStatus.REVIEW_PASSED
            ]

            if ready_prs:
                self.logger.info(f"Merging {len(ready_prs)} PRs: {ready_prs}")
                merge_results = await self.merge_executor.execute_merge_plan(ready_prs)
                results["merges"] = [
                    {
                        "pr_number": r.pr_number,
                        "success": r.success,
                        "error": r.error
                    }
                    for r in merge_results
                ]
                results["summary"]["merged"] = sum(1 for r in merge_results if r.success)

        return results

    async def dry_run(self, plan: Optional[OrchestrationPlan] = None) -> dict:
        """
        Perform a dry run of the orchestration.

        Args:
            plan: Optional plan (will analyze if not provided)

        Returns:
            Dry run results
        """
        if plan is None:
            await self.load_open_prs()
            plan = await self.analyze()

        merge_statuses = await self.merge_executor.dry_run(plan.pr_order)

        return {
            "plan": {
                "total_prs": plan.total_prs,
                "order": plan.pr_order,
                "parallel_groups": plan.parallel_groups,
                "conflicts": plan.conflict_pairs,
            },
            "merge_readiness": merge_statuses
        }

    def get_queue_status(self) -> Dict[int, dict]:
        """Get current status of all PRs in queue."""
        return {
            pr_num: {
                "branch": node.branch,
                "status": node.status.value,
                "conflicts_with": node.conflicts_with,
                "depends_on": node.depends_on,
                "review_result": node.review_result,
            }
            for pr_num, node in self._queue.items()
        }

    def get_pr(self, pr_number: int) -> Optional[PRNode]:
        """Get a specific PR from the queue."""
        return self._queue.get(pr_number)

    def is_pr_blocked(self, pr_number: int) -> bool:
        """Check if a PR is blocked by dependencies."""
        return self.dependency_analyzer.is_blocked(pr_number, self._merged)
