"""Data models for Multi-PR Orchestration (Phase 2)."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Set
from datetime import datetime


class PRStatus(Enum):
    """Status of a PR in the orchestration queue."""
    PENDING = "pending"           # Waiting to be reviewed
    REVIEWING = "reviewing"       # Currently being reviewed
    REVIEW_PASSED = "review_passed"  # Review passed, ready for merge
    REVIEW_FAILED = "review_failed"  # Review found critical/high issues
    MERGING = "merging"           # Merge in progress
    MERGED = "merged"             # Successfully merged
    FAILED = "failed"             # Merge failed
    CONFLICT = "conflict"         # Has merge conflicts
    BLOCKED = "blocked"           # Blocked by dependencies


@dataclass
class PRNode:
    """Represents a PR in the orchestration graph."""
    pr_number: int
    branch: str
    base: str                     # Target branch (usually main)
    status: PRStatus = PRStatus.PENDING
    changed_files: List[str] = field(default_factory=list)
    depends_on: List[int] = field(default_factory=list)      # PR numbers this depends on
    conflicts_with: List[int] = field(default_factory=list)  # PRs with file overlap
    review_result: Optional[dict] = None  # Review stats from Stage 1,2
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def is_ready_for_merge(self) -> bool:
        """Check if PR is ready to be merged."""
        return self.status == PRStatus.REVIEW_PASSED

    @property
    def is_blocked(self) -> bool:
        """Check if PR is blocked by dependencies or conflicts."""
        return self.status in (PRStatus.BLOCKED, PRStatus.CONFLICT)


@dataclass
class MergeResult:
    """Result of a merge operation."""
    pr_number: int
    success: bool
    method: str = "squash"  # squash, merge, rebase
    commit_sha: Optional[str] = None
    error: Optional[str] = None
    merged_at: Optional[datetime] = None


@dataclass
class OrchestratorConfig:
    """Configuration for the PR orchestrator."""
    # Merge settings
    merge_method: str = "squash"  # squash, merge, rebase
    auto_merge: bool = False      # Auto-merge when all checks pass
    delete_branch_after_merge: bool = True

    # Review requirements
    require_review_pass: bool = True
    allow_merge_with_medium_issues: bool = True
    max_medium_issues_for_merge: int = 3

    # Conflict handling
    auto_rebase_on_conflict: bool = True
    notify_on_conflict: bool = True

    # Parallel processing
    max_parallel_reviews: int = 5
    max_parallel_merges: int = 1  # Usually 1 to avoid race conditions


@dataclass
class OrchestrationPlan:
    """A plan for reviewing and merging multiple PRs."""
    pr_order: List[int]              # Ordered list of PR numbers to process
    parallel_groups: List[List[int]]  # Groups that can be reviewed in parallel
    conflict_pairs: List[tuple]       # Pairs of PRs with potential conflicts
    total_prs: int = 0
    estimated_reviews: int = 0

    def __post_init__(self):
        self.total_prs = len(self.pr_order)
        self.estimated_reviews = self.total_prs
