"""Configuration for PR Review Agent."""

from dataclasses import dataclass, field
from typing import Optional
import os


@dataclass
class ReviewConfig:
    """Configuration for the review agent."""

    # GitHub settings
    repo: str = ""
    pr_number: int = 0
    github_token: Optional[str] = None

    # Review behavior
    min_confidence: float = 0.7  # Minimum confidence to report issue
    post_comments: bool = True   # Post inline comments
    post_summary: bool = True    # Post summary comment

    # Severity filtering
    report_critical: bool = True
    report_high: bool = True
    report_medium: bool = True
    report_low: bool = False  # Skip low severity by default

    # Parallel processing
    parallel_validation: bool = True  # Validate issues in parallel (default: enabled)

    # Severity filtering at Stage 1 (skip validation for low severity)
    min_severity: str = "medium"  # low, medium, high, critical

    # MCP servers
    use_serena: bool = True
    use_context7: bool = True
    use_sequential_thinking: bool = True

    @classmethod
    def from_env(cls) -> "ReviewConfig":
        """Create config from environment variables."""
        return cls(
            repo=os.environ.get("GITHUB_REPOSITORY", ""),
            pr_number=int(os.environ.get("PR_NUMBER", "0")),
            github_token=os.environ.get("GITHUB_TOKEN"),
            min_confidence=float(os.environ.get("MIN_CONFIDENCE", "0.7")),
            post_comments=os.environ.get("POST_COMMENTS", "true").lower() == "true",
            post_summary=os.environ.get("POST_SUMMARY", "true").lower() == "true",
            report_low=os.environ.get("REPORT_LOW", "false").lower() == "true",
            parallel_validation=os.environ.get("PARALLEL_VALIDATION", "true").lower() == "true",
            min_severity=os.environ.get("MIN_SEVERITY", "medium"),
        )


@dataclass
class MergeRules:
    """Rules for Phase 3: TDD-based merge decisions."""

    # Coverage thresholds
    min_total_coverage: float = 80.0       # Total codebase coverage
    min_new_code_coverage: float = 90.0    # Coverage for new code only

    # Test requirements
    all_tests_must_pass: bool = True
    min_tests_per_function: int = 2
    require_edge_case_tests: bool = True

    # Issue thresholds
    allow_low_severity_issues: bool = True
    block_on_critical: bool = True
    block_on_high: bool = True
    max_medium_issues: int = 3

    # Automation level
    auto_merge_on_pass: bool = False       # Auto-merge when all checks pass
    auto_commit_tests: bool = True         # Commit generated tests to PR
    auto_fix_simple_issues: bool = False   # Auto-fix simple issues


# Default configurations
DEFAULT_CONFIG = ReviewConfig()
DEFAULT_MERGE_RULES = MergeRules()
