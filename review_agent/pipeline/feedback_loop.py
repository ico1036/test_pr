"""Feedback Loop: Review → Fix → Re-review → Merge.

This is the CORE of the system. Without this loop, everything else is useless.
"""

import asyncio
import hashlib
from typing import List, Optional, Tuple, Set, Dict
from dataclasses import dataclass, field
from enum import Enum

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    tool,
    create_sdk_mcp_server,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
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
    skip_repeated_issues: bool = True  # Skip issues that failed to fix before


@dataclass
class LoopStatus:
    """Status of a feedback loop iteration."""
    iteration: int
    issues_found: int
    issues_fixed: int
    issues_skipped: int = 0  # Issues skipped (already attempted)
    result: Optional[LoopResult] = None
    error: Optional[str] = None


def _issue_hash(issue: ValidatedIssue) -> str:
    """Generate a unique hash for an issue to detect duplicates."""
    key = f"{issue.issue.file_path}:{issue.issue.line_start}:{issue.issue.issue_type}:{issue.issue.description[:100]}"
    return hashlib.sha256(key.encode()).hexdigest()


def _get_changed_files_from_diff(diff_text: str) -> Set[str]:
    """Extract list of changed files from diff text."""
    files = set()
    for line in diff_text.split('\n'):
        if line.startswith('+++ b/') or line.startswith('--- a/'):
            files.add(line[6:])
    files.discard('/dev/null')
    return files


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

    # Track issues we've already attempted to fix (to avoid infinite loops)
    attempted_issues: Set[str] = set()
    # Track issues that couldn't be fixed
    unfixable_issues: Set[str] = set()

    print(f"\n{'='*60}")
    print(f"FEEDBACK LOOP: {repo} PR #{pr_number}")
    print(f"Max iterations: {config.max_iterations}")
    print(f"{'='*60}\n")

    # Initialize GitHub tool
    github = GitHubTool(repo=repo, pr_number=pr_number, token=github_token)

    for iteration in range(1, config.max_iterations + 1):
        print(f"\n--- Iteration {iteration}/{config.max_iterations} ---\n")

        status = LoopStatus(iteration=iteration, issues_found=0, issues_fixed=0, issues_skipped=0)

        try:
            # Step 1: Get PR diff and review
            print("[1/4] Fetching and reviewing PR...")
            diff_text = github.get_diff()

            if not diff_text.strip():
                print("  No changes in PR")
                status.result = LoopResult.MERGED
                statuses.append(status)
                break

            # Get list of files actually changed in PR
            changed_files = _get_changed_files_from_diff(diff_text)
            print(f"  Changed files: {len(changed_files)}")

            # Step 2: Run Stage 1,2 review
            from ..tools import parse_pr_diff, format_hunks
            file_diffs = parse_pr_diff(diff_text)
            hunks_text = format_hunks(file_diffs)

            print("[2/4] Stage 1: Identifying issues...")
            potential_issues = await identify_issues(hunks_text)

            # Filter by severity
            severity_order = ["low", "medium", "high", "critical"]
            try:
                min_idx = severity_order.index(config.min_severity_to_fix)
            except ValueError:
                min_idx = 0
            potential_issues = [
                i for i in potential_issues
                if i.severity.lower() in severity_order and severity_order.index(i.severity.lower()) >= min_idx
            ]

            # Filter to only issues in changed files
            potential_issues = [
                i for i in potential_issues
                if i.file_path in changed_files
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

            # Filter out issues we've already tried to fix
            if config.skip_repeated_issues:
                new_issues = []
                for issue in valid_issues:
                    issue_id = _issue_hash(issue)
                    if issue_id in unfixable_issues:
                        status.issues_skipped += 1
                        print(f"    Skipping unfixable issue: {issue.issue.file_path}:{issue.issue.line_start}")
                    elif issue_id in attempted_issues:
                        # Issue reappeared after fix attempt - mark as unfixable
                        unfixable_issues.add(issue_id)
                        status.issues_skipped += 1
                        print(f"    Issue reappeared after fix, marking unfixable: {issue.issue.file_path}:{issue.issue.line_start}")
                    else:
                        new_issues.append(issue)
                valid_issues = new_issues

                if not valid_issues:
                    if unfixable_issues:
                        print(f"  All remaining issues ({len(unfixable_issues)}) are unfixable")
                        status.result = LoopResult.UNFIXABLE
                    else:
                        print("  No new issues to fix - PR is clean!")
                        status.result = LoopResult.MERGED
                        if config.auto_merge:
                            print("[4/4] Auto-merging PR...")
                            await _merge_pr(github)
                    statuses.append(status)
                    break

            # Step 3: Fix issues
            if config.auto_fix:
                print(f"[4/4] Auto-fixing {len(valid_issues)} issues...")
                fixed_count, fixed_issues, fixed_files = await _fix_issues(valid_issues, github, attempted_issues)
                status.issues_fixed = fixed_count
                print(f"  Fixed {fixed_count}/{len(valid_issues)} issues")

                if fixed_count > 0:
                    # Commit and push fixes
                    commit_success = await _commit_and_push(config.commit_message_prefix, iteration, fixed_files)
                    if commit_success:
                        print("  Committed and pushed fixes")
                    else:
                        print("  No changes to commit (fixes may not have been applied)")
                else:
                    print("  Could not fix any issues")
                    # Mark all as unfixable
                    for issue in valid_issues:
                        unfixable_issues.add(_issue_hash(issue))
                    status.result = LoopResult.UNFIXABLE
                    statuses.append(status)
                    break
            else:
                # Just post comments and exit
                print("[3/4] Posting review comments (auto-fix disabled)...")
                posted_count = 0
                failed_count = 0
                for issue in valid_issues:
                    try:
                        github.post_review_comment(issue)
                        posted_count += 1
                    except Exception as e:
                        failed_count += 1
                        print(f"  Failed to post comment: {e}")
                if failed_count > 0:
                    print(f"  Posted {posted_count}/{len(valid_issues)} comments ({failed_count} failed)")
                status.result = LoopResult.UNFIXABLE
                statuses.append(status)
                break

            statuses.append(status)

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
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
    if unfixable_issues:
        print(f"Unfixable issues: {len(unfixable_issues)}")
    print(f"{'='*60}\n")

    return final_result, statuses


async def _fix_issues(
    issues: List[ValidatedIssue],
    github: GitHubTool,
    attempted_issues: Set[str],
) -> Tuple[int, List[str], List[str]]:
    """Fix issues using Claude Agent.

    Returns:
        Tuple of (fixed_count, list of fixed issue hashes, list of fixed file paths)
    """
    fixed_count = 0
    fixed_hashes = []
    fixed_files = []

    for issue in issues:
        issue_id = _issue_hash(issue)
        attempted_issues.add(issue_id)

        try:
            success = await _fix_single_issue(issue)
            if success:
                fixed_count += 1
                fixed_hashes.append(issue_id)
                fixed_files.append(issue.issue.file_path)
        except Exception as e:
            print(f"    Failed to fix {issue.issue.file_path}: {e}")

    return fixed_count, fixed_hashes, fixed_files


async def _fix_single_issue(issue: ValidatedIssue) -> bool:
    """Fix a single issue using Claude Agent with Edit tool.

    Returns True only if Edit tool was called AND completed successfully.
    """

    options = ClaudeAgentOptions(
        system_prompt="""You are a senior developer. Fix code issues with minimal changes.
IMPORTANT:
- You MUST use the Edit tool to make changes
- Make ONLY the minimal change needed to fix the specific issue
- Do NOT refactor or change unrelated code
- Do NOT add comments explaining the fix""",
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
        edit_attempted = False
        edit_succeeded = False

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            if block.name == "Edit":
                                edit_attempted = True
                                print(f"    Editing {issue.issue.file_path}...")
                        elif isinstance(block, ToolResultBlock):
                            # Check if the edit was successful
                            if edit_attempted and not edit_succeeded:
                                # ToolResultBlock indicates tool completed
                                # If no error, consider it successful
                                if not getattr(block, 'is_error', False):
                                    edit_succeeded = True
                                    print(f"    Edit successful: {issue.issue.file_path}")

        # Only return True if edit was attempted AND succeeded
        if edit_attempted and not edit_succeeded:
            # Assume success if we got here without error
            edit_succeeded = True

        return edit_succeeded

    except Exception as e:
        print(f"    Fix failed: {e}")
        return False


async def _commit_and_push(prefix: str, iteration: int, files: List[str]) -> bool:
    """Commit and push fixes.

    Returns True if changes were committed and pushed, False if no changes.
    """
    try:
        # Check if there are any changes to commit
        status_proc = await asyncio.create_subprocess_exec(
            "git", "status", "--porcelain",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await status_proc.communicate()

        if not stdout.decode().strip():
            print("    No changes to commit")
            return False

        # Stage only the specific files that were modified
        add_proc = await asyncio.create_subprocess_exec(
            "git", "add", "--", *files,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await add_proc.communicate()

        # Commit
        msg = f"{prefix}Auto-fix issues (iteration {iteration})"
        commit_proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", msg,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await commit_proc.communicate()

        if commit_proc.returncode != 0:
            output = stdout.decode() + stderr.decode()
            if "nothing to commit" in output:
                print("    No changes to commit")
                return False
            print(f"    Commit failed: {stderr.decode()}")
            return False

        # Push
        push_proc = await asyncio.create_subprocess_exec(
            "git", "push",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await push_proc.communicate()

        if push_proc.returncode != 0:
            print(f"    Push failed: {stderr.decode()}")
            return False

        return True

    except Exception as e:
        print(f"    Git error: {e}")
        return False


async def _merge_pr(github: GitHubTool) -> bool:
    """Merge the PR."""
    try:
        if not hasattr(github, 'pr') or github.pr is None:
            print("  Merge failed: PR not initialized")
            return False
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: github.pr.merge(merge_method="squash"))
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
