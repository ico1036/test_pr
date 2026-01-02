"""Feedback Loop: Review → Fix → Re-review → Merge.

This is the CORE of the system. Without this loop, everything else is useless.
"""

import asyncio
import subprocess
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    tool,
    create_sdk_mcp_server,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ResultMessage,
)

from ..models import ValidatedIssue, PotentialIssue
from ..config import ReviewConfig, MergeRules
from ..tools import GitHubTool, StorageTool
from .stage1_identify import identify_issues
from .stage2_validate import validate_issues


class LoopResult(Enum):
    """Result of the feedback loop."""
    MERGED = "merged"           # Successfully merged
    MAX_ITERATIONS = "max_iterations"  # Hit max iterations
    UNFIXABLE = "unfixable"     # Issues couldn't be fixed
    ERROR = "error"             # Error occurred


@dataclass
class LoopConfig:
    """Configuration for the feedback loop."""
    max_iterations: int = 5          # Max fix attempts
    auto_fix: bool = True            # Auto-fix issues
    auto_merge: bool = True          # Auto-merge when clean
    min_severity_to_fix: str = "medium"  # Only fix medium+ issues
    commit_message_prefix: str = "fix: "


@dataclass
class LoopStatus:
    """Status of a feedback loop iteration."""
    iteration: int
    issues_found: int
    issues_fixed: int
    result: Optional[LoopResult] = None
    error: Optional[str] = None


FIX_PROMPT = """
You are a senior developer fixing code issues. Fix the following issue in the codebase.

## Issue to Fix
- File: {file_path}
- Lines: {line_start}-{line_end}
- Type: {issue_type}
- Severity: {severity}
- Description: {description}

## Current Code
```
{code_snippet}
```

## Mitigation Suggestion
{mitigation}

## Instructions
1. Use the Edit tool to fix this issue
2. Make minimal changes - only fix the issue, don't refactor
3. Ensure the fix is correct and doesn't introduce new issues
4. After fixing, briefly explain what you changed

Fix this issue now.
"""


async def run_feedback_loop(
    repo: str,
    pr_number: int,
    config: Optional[LoopConfig] = None,
    github_token: Optional[str] = None,
) -> Tuple[LoopResult, List[LoopStatus]]:
    """
    Run the complete feedback loop: Review → Fix → Re-review → Merge.

    This is the CORE function of the entire system.

    Args:
        repo: Repository in format owner/repo
        pr_number: PR number to process
        config: Loop configuration
        github_token: GitHub token

    Returns:
        Tuple of (final result, list of iteration statuses)
    """
    config = config or LoopConfig()
    statuses: List[LoopStatus] = []

    print(f"\n{'='*60}")
    print(f"FEEDBACK LOOP: {repo} PR #{pr_number}")
    print(f"Max iterations: {config.max_iterations}")
    print(f"{'='*60}\n")

    # Initialize GitHub tool
    github = GitHubTool(repo=repo, pr_number=pr_number, token=github_token)

    for iteration in range(1, config.max_iterations + 1):
        print(f"\n--- Iteration {iteration}/{config.max_iterations} ---\n")

        status = LoopStatus(iteration=iteration, issues_found=0, issues_fixed=0)

        try:
            # Step 1: Get PR diff and review
            print("[1/4] Fetching and reviewing PR...")
            diff_text = github.get_diff()

            if not diff_text.strip():
                print("  No changes in PR")
                status.result = LoopResult.MERGED
                statuses.append(status)
                break

            # Step 2: Run Stage 1,2 review
            from ..tools import parse_pr_diff, format_hunks
            file_diffs = parse_pr_diff(diff_text)
            hunks_text = format_hunks(file_diffs)

            print("[2/4] Stage 1: Identifying issues...")
            potential_issues = await identify_issues(hunks_text)

            # Filter by severity
            severity_order = ["low", "medium", "high", "critical"]
            min_idx = severity_order.index(config.min_severity_to_fix)
            potential_issues = [
                i for i in potential_issues
                if severity_order.index(i.severity.lower()) >= min_idx
            ]

            if not potential_issues:
                print("  No issues found - PR is clean!")
                status.result = LoopResult.MERGED
                statuses.append(status)

                if config.auto_merge:
                    print("[4/4] Auto-merging PR...")
                    await _merge_pr(github)

                break

            print(f"  Found {len(potential_issues)} potential issues")

            print("[3/4] Stage 2: Validating issues...")
            validated_issues = await validate_issues(potential_issues, parallel=True)
            valid_issues = [i for i in validated_issues if i.is_valid]

            status.issues_found = len(valid_issues)
            print(f"  {len(valid_issues)} valid issues confirmed")

            if not valid_issues:
                print("  All issues were false positives - PR is clean!")
                status.result = LoopResult.MERGED
                statuses.append(status)

                if config.auto_merge:
                    print("[4/4] Auto-merging PR...")
                    await _merge_pr(github)

                break

            # Step 3: Fix issues
            if config.auto_fix:
                print(f"[3/4] Auto-fixing {len(valid_issues)} issues...")
                fixed_count = await _fix_issues(valid_issues, github)
                status.issues_fixed = fixed_count
                print(f"  Fixed {fixed_count}/{len(valid_issues)} issues")

                if fixed_count > 0:
                    # Commit and push fixes
                    await _commit_and_push(config.commit_message_prefix, iteration)
                    print("  Committed and pushed fixes")
                else:
                    print("  Could not fix any issues")
                    status.result = LoopResult.UNFIXABLE
                    statuses.append(status)
                    break
            else:
                # Just post comments and exit
                print("[3/4] Posting review comments (auto-fix disabled)...")
                for issue in valid_issues:
                    github.post_review_comment(issue)
                status.result = LoopResult.UNFIXABLE
                statuses.append(status)
                break

            statuses.append(status)

        except Exception as e:
            print(f"  ERROR: {e}")
            status.error = str(e)
            status.result = LoopResult.ERROR
            statuses.append(status)
            break

    # Check if we hit max iterations
    if statuses and statuses[-1].result is None:
        statuses[-1].result = LoopResult.MAX_ITERATIONS
        print(f"\n  Hit max iterations ({config.max_iterations})")

    # Print summary
    final_result = statuses[-1].result if statuses else LoopResult.ERROR
    print(f"\n{'='*60}")
    print(f"LOOP COMPLETE: {final_result.value}")
    print(f"Total iterations: {len(statuses)}")
    print(f"{'='*60}\n")

    return final_result, statuses


async def _fix_issues(issues: List[ValidatedIssue], github: GitHubTool) -> int:
    """Fix issues using Claude Agent."""
    fixed_count = 0

    for issue in issues:
        try:
            success = await _fix_single_issue(issue)
            if success:
                fixed_count += 1
        except Exception as e:
            print(f"    Failed to fix {issue.issue.file_path}: {e}")

    return fixed_count


async def _fix_single_issue(issue: ValidatedIssue) -> bool:
    """Fix a single issue using Claude Agent with Edit tool."""

    options = ClaudeAgentOptions(
        system_prompt="You are a senior developer. Fix code issues with minimal changes.",
        allowed_tools=["Edit", "Read"],
        permission_mode="acceptEdits",
        max_turns=10,
    )

    prompt = FIX_PROMPT.format(
        file_path=issue.issue.file_path,
        line_start=issue.issue.line_start,
        line_end=issue.issue.line_end,
        issue_type=issue.issue.issue_type,
        severity=issue.issue.severity,
        description=issue.issue.description,
        code_snippet=issue.issue.code_snippet,
        mitigation=issue.mitigation or "Use best practices to fix this issue.",
    )

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            if block.name == "Edit":
                                print(f"    Editing {issue.issue.file_path}...")
                                return True

        return False

    except Exception as e:
        print(f"    Fix failed: {e}")
        return False


async def _commit_and_push(prefix: str, iteration: int) -> bool:
    """Commit and push fixes."""
    try:
        # Stage all changes
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)

        # Commit
        msg = f"{prefix}Auto-fix issues (iteration {iteration})"
        subprocess.run(
            ["git", "commit", "-m", msg],
            check=True,
            capture_output=True
        )

        # Push
        subprocess.run(["git", "push"], check=True, capture_output=True)

        return True

    except subprocess.CalledProcessError as e:
        print(f"    Git error: {e}")
        return False


async def _merge_pr(github: GitHubTool) -> bool:
    """Merge the PR."""
    try:
        github.pr.merge(merge_method="squash")
        print("  PR merged successfully!")
        return True
    except Exception as e:
        print(f"  Merge failed: {e}")
        return False


# Synchronous wrapper
def run_feedback_loop_sync(
    repo: str,
    pr_number: int,
    config: Optional[LoopConfig] = None,
    github_token: Optional[str] = None,
) -> Tuple[LoopResult, List[LoopStatus]]:
    """Synchronous wrapper for run_feedback_loop."""
    return asyncio.run(run_feedback_loop(repo, pr_number, config, github_token))
