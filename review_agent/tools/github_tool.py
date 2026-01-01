"""GitHub API wrapper for PR operations."""

import os
from dataclasses import dataclass
from typing import List, Optional
from github import Github, GithubException
from github.PullRequest import PullRequest

from ..models import ValidatedIssue


@dataclass
class ReviewComment:
    """Represents a review comment to post on PR."""
    file_path: str
    line: int
    body: str
    side: str = "RIGHT"  # LEFT for deletions, RIGHT for additions


class GitHubTool:
    """
    GitHub API wrapper for PR review operations.

    Handles:
    - Fetching PR diff
    - Posting review comments
    - Managing PR status
    """

    def __init__(self, repo: str, pr_number: int, token: Optional[str] = None):
        """
        Initialize GitHub tool.

        Args:
            repo: Repository in format "owner/repo"
            pr_number: Pull request number
            token: GitHub token (defaults to GITHUB_TOKEN env var)
        """
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GitHub token required. Set GITHUB_TOKEN env var or pass token parameter.")

        self.gh = Github(self.token)
        self.repo = self.gh.get_repo(repo)
        self.pr_number = pr_number
        self._pr: Optional[PullRequest] = None

    @property
    def pr(self) -> PullRequest:
        """Get the pull request object (cached)."""
        if self._pr is None:
            self._pr = self.repo.get_pull(self.pr_number)
        return self._pr

    def get_diff(self) -> str:
        """
        Get the unified diff for this PR.

        Returns:
            Raw diff string
        """
        # GitHub API returns diff when Accept header is set
        # PyGithub doesn't support this directly, so we use the files
        files = self.pr.get_files()

        diff_parts = []
        for file in files:
            if file.patch:
                diff_parts.append(f"diff --git a/{file.filename} b/{file.filename}")
                if file.status == "added":
                    diff_parts.append("new file mode 100644")
                elif file.status == "removed":
                    diff_parts.append("deleted file mode 100644")
                diff_parts.append(f"--- a/{file.filename}")
                diff_parts.append(f"+++ b/{file.filename}")
                diff_parts.append(file.patch)
                diff_parts.append("")

        return '\n'.join(diff_parts)

    def get_changed_files(self) -> List[str]:
        """Get list of files changed in this PR."""
        return [f.filename for f in self.pr.get_files()]

    def post_review_comment(
        self,
        issue: ValidatedIssue,
        commit_sha: Optional[str] = None
    ) -> bool:
        """
        Post a review comment for a validated issue.

        Args:
            issue: The validated issue to comment on
            commit_sha: Specific commit SHA (defaults to latest)

        Returns:
            True if comment was posted successfully
        """
        if not issue.is_valid:
            return False

        commit = self.repo.get_commit(commit_sha or self.pr.head.sha)

        # Build comment body
        body = self._format_issue_comment(issue)

        try:
            self.pr.create_review_comment(
                body=body,
                commit=commit,
                path=issue.issue.file_path,
                line=issue.issue.line_end,
                side="RIGHT"
            )
            return True
        except GithubException as e:
            print(f"Failed to post comment: {e}")
            return False

    def post_review_summary(
        self,
        validated_issues: List[ValidatedIssue],
        stats: Optional[dict] = None
    ):
        """
        Post a summary comment on the PR.

        Args:
            validated_issues: All validated issues
            stats: Optional statistics dict
        """
        valid_issues = [i for i in validated_issues if i.is_valid]

        # Build summary
        body_parts = ["## AI Code Review Summary\n"]

        if not valid_issues:
            body_parts.append("No significant issues found. The code looks good.\n")
        else:
            # Group by severity
            by_severity = {}
            for issue in valid_issues:
                sev = issue.issue.severity
                if sev not in by_severity:
                    by_severity[sev] = []
                by_severity[sev].append(issue)

            body_parts.append(f"Found **{len(valid_issues)}** issues:\n")

            severity_order = ["critical", "high", "medium", "low"]
            severity_emoji = {
                "critical": "",
                "high": "",
                "medium": "",
                "low": ""
            }

            for sev in severity_order:
                if sev in by_severity:
                    emoji = severity_emoji.get(sev, "")
                    body_parts.append(f"\n### {emoji} {sev.upper()} ({len(by_severity[sev])})\n")
                    for issue in by_severity[sev]:
                        body_parts.append(
                            f"- **{issue.issue.file_path}:{issue.issue.line_start}** - "
                            f"{issue.issue.description[:100]}..."
                        )

        # Add stats if provided
        if stats:
            body_parts.append("\n---\n")
            body_parts.append("### Stats\n")
            body_parts.append(f"- Potential issues found: {stats.get('potential', 0)}")
            body_parts.append(f"- Validated as real: {stats.get('valid', 0)}")
            body_parts.append(f"- False positives filtered: {stats.get('false_positives', 0)}")

        body_parts.append("\n\n---\n*Reviewed by AI PR Review Agent*")

        self.pr.create_issue_comment('\n'.join(body_parts))

    def _format_issue_comment(self, issue: ValidatedIssue) -> str:
        """Format a validated issue as a review comment."""
        parts = [
            f"**{issue.issue.severity.upper()}**: {issue.issue.issue_type}\n",
            f"\n{issue.issue.description}\n",
        ]

        if issue.evidence:
            parts.append("\n**Evidence:**\n")
            for ev in issue.evidence[:3]:  # Limit to 3 evidence items
                parts.append(f"- {ev}\n")

        if issue.mitigation:
            parts.append(f"\n**Suggested Fix:**\n{issue.mitigation}\n")

        if issue.library_reference:
            parts.append(f"\n**Reference:** {issue.library_reference}\n")

        parts.append(f"\n*Confidence: {int(issue.confidence * 100)}%*")

        return ''.join(parts)

    def approve_pr(self, message: str = "Approved by AI Review Agent"):
        """Approve the PR."""
        self.pr.create_review(body=message, event="APPROVE")

    def request_changes(self, message: str):
        """Request changes on the PR."""
        self.pr.create_review(body=message, event="REQUEST_CHANGES")
