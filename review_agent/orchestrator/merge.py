"""Merge executor for Multi-PR Orchestration."""

import asyncio
from typing import List, Optional
from datetime import datetime

from github import Github, GithubException
from github.PullRequest import PullRequest as GHPullRequest
from github.Repository import Repository as GHRepository

from ..models import PRNode, PRStatus, MergeResult, OrchestratorConfig
from ..utils import get_logger


class MergeExecutor:
    """
    Executes merge operations for PRs.

    Handles:
    - Conflict detection and auto-rebase
    - CI status checking
    - Sequential merge execution
    - Rollback on failure
    """

    def __init__(
        self,
        repo: GHRepository,
        config: OrchestratorConfig
    ):
        """
        Initialize merge executor.

        Args:
            repo: GitHub repository object
            config: Orchestrator configuration
        """
        self.repo = repo
        self.config = config
        self.logger = get_logger()

    async def check_mergeable(self, pr_number: int) -> tuple[bool, str]:
        """
        Check if a PR is mergeable.

        Args:
            pr_number: PR number to check

        Returns:
            Tuple of (is_mergeable, reason)
        """
        try:
            pr = self.repo.get_pull(pr_number)

            # Wait for mergeable state to be computed
            for _ in range(10):
                if pr.mergeable is not None:
                    break
                await asyncio.sleep(1)
                pr = self.repo.get_pull(pr_number)

            if pr.mergeable is None:
                return False, "Mergeable state unknown"

            if not pr.mergeable:
                return False, f"PR has conflicts (mergeable_state: {pr.mergeable_state})"

            if pr.mergeable_state == "blocked":
                return False, "PR is blocked by branch protection rules"

            if pr.mergeable_state == "behind":
                return False, "PR is behind base branch"

            return True, "OK"

        except GithubException as e:
            return False, f"GitHub API error: {e}"

    async def check_ci_status(self, pr_number: int) -> tuple[bool, str]:
        """
        Check if CI checks have passed.

        Args:
            pr_number: PR number to check

        Returns:
            Tuple of (all_passed, status_message)
        """
        try:
            pr = self.repo.get_pull(pr_number)
            commit = self.repo.get_commit(pr.head.sha)

            # Get combined status
            combined = commit.get_combined_status()

            if combined.state == "pending":
                return False, "CI checks still running"
            if combined.state == "failure":
                failed = [s.context for s in combined.statuses if s.state == "failure"]
                return False, f"CI checks failed: {', '.join(failed)}"
            if combined.state == "error":
                return False, "CI checks errored"

            # Also check check runs (GitHub Actions)
            check_runs = commit.get_check_runs()
            for run in check_runs:
                if run.conclusion not in ("success", "skipped", "neutral"):
                    if run.status == "in_progress":
                        return False, f"Check '{run.name}' still running"
                    return False, f"Check '{run.name}' failed: {run.conclusion}"

            return True, "All checks passed"

        except GithubException as e:
            return False, f"GitHub API error: {e}"

    async def attempt_rebase(self, pr_number: int) -> bool:
        """
        Attempt to rebase a PR onto its base branch.

        Args:
            pr_number: PR number to rebase

        Returns:
            True if rebase succeeded
        """
        try:
            pr = self.repo.get_pull(pr_number)

            # GitHub's update branch feature (equivalent to rebase)
            pr.update_branch()

            self.logger.info(f"PR #{pr_number} rebased successfully")
            return True

        except GithubException as e:
            self.logger.warning(f"Failed to rebase PR #{pr_number}: {e}")
            return False

    async def merge(self, pr_number: int) -> MergeResult:
        """
        Merge a single PR.

        Args:
            pr_number: PR number to merge

        Returns:
            MergeResult with success/failure info
        """
        try:
            pr = self.repo.get_pull(pr_number)

            # Check if already merged
            if pr.merged:
                return MergeResult(
                    pr_number=pr_number,
                    success=True,
                    method=self.config.merge_method,
                    commit_sha=pr.merge_commit_sha,
                    merged_at=pr.merged_at
                )

            # Check mergeable
            is_mergeable, reason = await self.check_mergeable(pr_number)
            if not is_mergeable:
                # Try auto-rebase if enabled
                if self.config.auto_rebase_on_conflict and "behind" in reason.lower():
                    if await self.attempt_rebase(pr_number):
                        is_mergeable, reason = await self.check_mergeable(pr_number)

                if not is_mergeable:
                    return MergeResult(
                        pr_number=pr_number,
                        success=False,
                        error=reason
                    )

            # Check CI status
            ci_passed, ci_status = await self.check_ci_status(pr_number)
            if not ci_passed:
                return MergeResult(
                    pr_number=pr_number,
                    success=False,
                    error=ci_status
                )

            # Perform merge
            merge_commit = pr.merge(
                merge_method=self.config.merge_method,
                commit_message=f"Merge PR #{pr_number}: {pr.title}"
            )

            # Delete branch if configured
            if self.config.delete_branch_after_merge:
                try:
                    ref = self.repo.get_git_ref(f"heads/{pr.head.ref}")
                    ref.delete()
                    self.logger.info(f"Deleted branch {pr.head.ref}")
                except GithubException:
                    pass  # Branch might already be deleted or protected

            return MergeResult(
                pr_number=pr_number,
                success=True,
                method=self.config.merge_method,
                commit_sha=merge_commit.sha,
                merged_at=datetime.now()
            )

        except GithubException as e:
            return MergeResult(
                pr_number=pr_number,
                success=False,
                error=str(e)
            )

    async def execute_merge_plan(
        self,
        pr_order: List[int],
        stop_on_failure: bool = True
    ) -> List[MergeResult]:
        """
        Execute a merge plan (ordered list of PRs).

        Args:
            pr_order: Ordered list of PR numbers to merge
            stop_on_failure: Stop if any merge fails

        Returns:
            List of MergeResult for each PR
        """
        results = []

        for pr_number in pr_order:
            self.logger.info(f"Merging PR #{pr_number}...")

            result = await self.merge(pr_number)
            results.append(result)

            if result.success:
                self.logger.info(f"PR #{pr_number} merged successfully")
            else:
                self.logger.error(f"PR #{pr_number} merge failed: {result.error}")
                if stop_on_failure:
                    self.logger.warning("Stopping merge plan due to failure")
                    break

            # Small delay between merges to let GitHub process
            await asyncio.sleep(2)

        return results

    async def dry_run(self, pr_order: List[int]) -> List[dict]:
        """
        Perform a dry run of the merge plan.

        Checks mergeability and CI status without actually merging.

        Args:
            pr_order: Ordered list of PR numbers

        Returns:
            List of status dicts for each PR
        """
        statuses = []

        for pr_number in pr_order:
            is_mergeable, merge_reason = await self.check_mergeable(pr_number)
            ci_passed, ci_status = await self.check_ci_status(pr_number)

            statuses.append({
                "pr_number": pr_number,
                "mergeable": is_mergeable,
                "merge_reason": merge_reason,
                "ci_passed": ci_passed,
                "ci_status": ci_status,
                "ready": is_mergeable and ci_passed
            })

        return statuses
