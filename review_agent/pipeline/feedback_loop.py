"""Feedback Loop: Review → Fix → Re-review → Merge.

This is the CORE of the system. Without this loop, everything else is useless.

200% VERSION:
- Git commit/push with proper branch handling
- Test verification after fixes
- Re-review verification to confirm fixes work
- Comprehensive error handling
- Detailed progress tracking
- File change detection before/after
"""

import asyncio
import hashlib
import os
from pathlib import Path
from typing import List, Optional, Tuple, Set, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

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
    MERGED = "merged"                    # Successfully merged
    READY_TO_MERGE = "ready_to_merge"    # Clean, ready for merge (auto_merge=False)
    MAX_ITERATIONS = "max_iterations"    # Hit max iterations
    UNFIXABLE = "unfixable"              # Issues couldn't be fixed
    TEST_FAILED = "test_failed"          # Tests failed after fix
    ERROR = "error"                      # Error occurred


@dataclass
class LoopConfig:
    """Configuration for the feedback loop."""
    max_iterations: int = 5              # Max fix attempts
    auto_fix: bool = True                # Auto-fix issues
    auto_merge: bool = True              # Auto-merge when clean
    min_severity_to_fix: str = "medium"  # Only fix medium+ issues
    commit_message_prefix: str = "fix: "
    skip_repeated_issues: bool = True    # Skip issues that failed to fix before
    run_tests: bool = False              # Run tests after fixes
    test_command: str = "pytest"         # Command to run tests
    require_tests_pass: bool = False     # Require tests to pass before merge
    working_dir: Optional[str] = None    # Working directory for git operations


@dataclass
class FixResult:
    """Result of fixing a single issue."""
    issue_hash: str
    file_path: str
    success: bool
    error: Optional[str] = None
    changes_made: bool = False


@dataclass
class LoopStatus:
    """Status of a feedback loop iteration."""
    iteration: int
    issues_found: int
    issues_fixed: int
    issues_skipped: int = 0              # Issues skipped (already attempted)
    tests_passed: Optional[bool] = None  # Test results
    commit_sha: Optional[str] = None     # Git commit SHA
    result: Optional[LoopResult] = None
    error: Optional[str] = None
    duration_ms: int = 0


def _issue_hash(issue: ValidatedIssue) -> str:
    """Generate a unique hash for an issue to detect duplicates.

    Uses file_path + issue_type + description (without line numbers)
    to handle cases where line numbers shift after fixes.
    """
    # Normalize description by removing line number references
    desc = issue.issue.description[:100].lower()
    key = f"{issue.issue.file_path}:{issue.issue.issue_type}:{desc}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _get_changed_files_from_diff(diff_text: str) -> Set[str]:
    """Extract list of changed files from diff text."""
    files = set()
    for line in diff_text.split('\n'):
        if line.startswith('+++ b/') or line.startswith('--- a/'):
            files.add(line[6:])
    files.discard('/dev/null')
    return files


FIX_PROMPT = """You are a senior developer fixing a code issue.

## Issue
- File: {file_path}
- Lines: {line_start}-{line_end}
- Type: {issue_type}
- Severity: {severity}
- Description: {description}

## Current Code
```
{code_snippet}
```

## Fix Guidance
{mitigation}

## Rules
1. Use the Edit tool to fix ONLY this specific issue
2. Make MINIMAL changes - don't refactor other code
3. Don't add comments
4. Ensure the fix doesn't break anything

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
    """
    config = config or LoopConfig()
    statuses: List[LoopStatus] = []
    working_dir = config.working_dir or os.getcwd()

    # Track issues
    attempted_issues: Set[str] = set()
    unfixable_issues: Set[str] = set()
    fixed_in_iteration: Dict[int, Set[str]] = {}

    print(f"\n{'='*60}")
    print(f"FEEDBACK LOOP: {repo} PR #{pr_number}")
    print(f"{'='*60}")
    print(f"  Max iterations: {config.max_iterations}")
    print(f"  Run tests: {config.run_tests}")
    print(f"  Auto merge: {config.auto_merge}")
    print(f"  Working dir: {working_dir}")
    print(f"{'='*60}\n")

    # Initialize GitHub tool
    github = GitHubTool(repo=repo, pr_number=pr_number, token=github_token)

    # Get PR branch info and checkout
    pr_branch = await _get_pr_branch(github)
    print(f"PR branch: {pr_branch}")
    await _checkout_branch(pr_branch, working_dir)

    for iteration in range(1, config.max_iterations + 1):
        start_time = datetime.now()
        print(f"\n{'-'*60}")
        print(f"ITERATION {iteration}/{config.max_iterations}")
        print(f"{'-'*60}\n")

        status = LoopStatus(
            iteration=iteration,
            issues_found=0,
            issues_fixed=0,
            issues_skipped=0
        )
        fixed_in_iteration[iteration] = set()

        try:
            # Step 1: Fetch latest and get diff
            print("[1/5] Fetching PR diff...")
            await _pull_latest(working_dir)
            diff_text = github.get_diff()

            if not diff_text.strip():
                print("  OK: No changes in PR")
                status.result = LoopResult.READY_TO_MERGE
                statuses.append(status)
                break

            changed_files = _get_changed_files_from_diff(diff_text)
            print(f"  Changed files: {len(changed_files)}")
            for f in list(changed_files)[:5]:
                print(f"    - {f}")
            if len(changed_files) > 5:
                print(f"    ... and {len(changed_files) - 5} more")

            # Step 2: Identify issues
            print("\n[2/5] Identifying issues...")
            from ..tools import parse_pr_diff, format_hunks
            file_diffs = parse_pr_diff(diff_text)
            hunks_text = format_hunks(file_diffs)

            potential_issues = await identify_issues(hunks_text)

            # Filter by severity and changed files
            severity_order = ["low", "medium", "high", "critical"]
            try:
                min_idx = severity_order.index(config.min_severity_to_fix)
            except ValueError:
                min_idx = 0

            potential_issues = [
                i for i in potential_issues
                if (i.severity.lower() in severity_order and
                    severity_order.index(i.severity.lower()) >= min_idx and
                    i.file_path in changed_files)
            ]

            if not potential_issues:
                print("  OK: No issues found - PR is clean!")
                status.result = LoopResult.READY_TO_MERGE
                statuses.append(status)
                break

            print(f"  Found {len(potential_issues)} potential issues")

            # Step 3: Validate issues
            print("\n[3/5] Validating issues...")
            validated_issues = await validate_issues(potential_issues, parallel=True)
            valid_issues = [i for i in validated_issues if i.is_valid]

            status.issues_found = len(valid_issues)
            print(f"  OK: {len(valid_issues)} valid issues confirmed")

            if not valid_issues:
                print("  OK: All issues were false positives - PR is clean!")
                status.result = LoopResult.READY_TO_MERGE
                statuses.append(status)
                break

            # Filter out already-attempted issues
            if config.skip_repeated_issues:
                new_issues = []
                for issue in valid_issues:
                    issue_id = _issue_hash(issue)
                    if issue_id in unfixable_issues:
                        status.issues_skipped += 1
                        print(f"    SKIP (unfixable): {issue.issue.file_path}:{issue.issue.line_start}")
                    elif issue_id in attempted_issues:
                        unfixable_issues.add(issue_id)
                        status.issues_skipped += 1
                        print(f"    SKIP (reappeared): {issue.issue.file_path}:{issue.issue.line_start}")
                    else:
                        new_issues.append(issue)
                valid_issues = new_issues

                if not valid_issues:
                    if unfixable_issues:
                        print(f"  FAIL: All {len(unfixable_issues)} remaining issues are unfixable")
                        status.result = LoopResult.UNFIXABLE
                    else:
                        print("  OK: No new issues - PR is clean!")
                        status.result = LoopResult.READY_TO_MERGE
                    statuses.append(status)
                    break

            # Step 4: Fix issues
            if not config.auto_fix:
                print("\n[4/5] Auto-fix disabled, posting comments...")
                for issue in valid_issues:
                    github.post_review_comment(issue)
                status.result = LoopResult.UNFIXABLE
                statuses.append(status)
                break

            print(f"\n[4/5] Fixing {len(valid_issues)} issues...")
            fix_results = await _fix_issues_batch(valid_issues, attempted_issues, working_dir)

            # Count successes
            successful_fixes = [r for r in fix_results if r.success and r.changes_made]
            status.issues_fixed = len(successful_fixes)
            fixed_files = list(set(r.file_path for r in successful_fixes))

            for r in successful_fixes:
                fixed_in_iteration[iteration].add(r.issue_hash)

            print(f"  OK: Fixed {status.issues_fixed}/{len(valid_issues)} issues")

            if status.issues_fixed == 0:
                print("  FAIL: Could not fix any issues")
                for issue in valid_issues:
                    unfixable_issues.add(_issue_hash(issue))
                status.result = LoopResult.UNFIXABLE
                statuses.append(status)
                break

            # Step 5: Run tests (if enabled)
            if config.run_tests:
                print("\n[5/5] Running tests...")
                tests_passed = await _run_tests(config.test_command, working_dir)
                status.tests_passed = tests_passed

                if not tests_passed:
                    print("  FAIL: Tests failed!")
                    if config.require_tests_pass:
                        print("  Reverting changes...")
                        await _revert_changes(working_dir)
                        for r in successful_fixes:
                            unfixable_issues.add(r.issue_hash)
                        status.result = LoopResult.TEST_FAILED
                        statuses.append(status)
                        break
                else:
                    print("  OK: Tests passed!")
            else:
                print("\n[5/5] Tests skipped")

            # Commit and push
            commit_sha = await _commit_and_push(
                prefix=config.commit_message_prefix,
                iteration=iteration,
                files=fixed_files,
                working_dir=working_dir
            )

            if commit_sha:
                status.commit_sha = commit_sha
                print(f"  OK: Committed and pushed: {commit_sha[:8]}")
            else:
                print("  WARN: No changes to commit")

            # Calculate duration
            status.duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            statuses.append(status)

        except Exception as e:
            print(f"\n  ERROR: {e}")
            import traceback
            traceback.print_exc()
            status.error = str(e)
            status.result = LoopResult.ERROR
            status.duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            statuses.append(status)
            break

    # Final result
    if statuses and statuses[-1].result is None:
        statuses[-1].result = LoopResult.MAX_ITERATIONS
        print(f"\n  WARN: Hit max iterations ({config.max_iterations})")

    final_result = statuses[-1].result if statuses else LoopResult.ERROR

    # Handle merge
    if final_result == LoopResult.READY_TO_MERGE and config.auto_merge:
        if await _do_merge(github):
            final_result = LoopResult.MERGED
            statuses[-1].result = LoopResult.MERGED

    # Print summary
    _print_summary(final_result, statuses, unfixable_issues, fixed_in_iteration)

    return final_result, statuses


async def _fix_issues_batch(
    issues: List[ValidatedIssue],
    attempted_issues: Set[str],
    working_dir: str,
) -> List[FixResult]:
    """Fix multiple issues, tracking results."""
    results = []

    for i, issue in enumerate(issues, 1):
        issue_id = _issue_hash(issue)
        attempted_issues.add(issue_id)

        print(f"  [{i}/{len(issues)}] {issue.issue.file_path}:{issue.issue.line_start} ({issue.issue.issue_type})")

        result = FixResult(
            issue_hash=issue_id,
            file_path=issue.issue.file_path,
            success=False
        )

        try:
            # Check file exists
            file_path = Path(working_dir) / issue.issue.file_path
            if not file_path.exists():
                result.error = "File not found"
                print(f"      FAIL: File not found")
                results.append(result)
                continue

            # Get content before fix
            before_content = file_path.read_text()

            # Attempt fix
            success = await _fix_single_issue(issue, working_dir)

            # Check if file changed
            after_content = file_path.read_text()
            changes_made = before_content != after_content

            result.success = success
            result.changes_made = changes_made

            if success and changes_made:
                print(f"      OK: Fixed")
            elif success and not changes_made:
                print(f"      WARN: No changes made")
            else:
                print(f"      FAIL: Could not fix")

        except Exception as e:
            result.error = str(e)
            print(f"      ERROR: {e}")

        results.append(result)

    return results


async def _fix_single_issue(issue: ValidatedIssue, working_dir: str) -> bool:
    """Fix a single issue using Claude Agent with Edit tool."""

    options = ClaudeAgentOptions(
        system_prompt="""You are a senior developer fixing code issues.
RULES:
- Use the Edit tool to make changes
- Make ONLY the minimal change to fix the issue
- Do NOT refactor or change unrelated code
- Do NOT add comments""",
        allowed_tools=["Edit", "Read"],
        permission_mode="acceptEdits",
        max_turns=10,
        cwd=working_dir,
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
        edit_count = 0

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock) and block.name == "Edit":
                            edit_count += 1

        return edit_count > 0

    except Exception as e:
        print(f"      Fix error: {e}")
        return False


async def _run_tests(test_command: str, working_dir: str) -> bool:
    """Run tests and return True if they pass."""
    try:
        proc = await asyncio.create_subprocess_shell(
            test_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode == 0:
            return True
        else:
            output = stdout.decode() + stderr.decode()
            if output:
                lines = output.strip().split('\n')
                print(f"    Test output (last 10 lines):")
                for line in lines[-10:]:
                    print(f"      {line}")
            return False

    except asyncio.TimeoutError:
        print("    FAIL: Tests timed out (5 min)")
        return False
    except Exception as e:
        print(f"    ERROR: Test error: {e}")
        return False


async def _get_pr_branch(github: GitHubTool) -> str:
    """Get the PR's head branch name."""
    try:
        return github.pr.head.ref
    except Exception:
        return "main"


async def _checkout_branch(branch: str, working_dir: str) -> bool:
    """Checkout the specified branch."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "checkout", branch,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            print(f"  Checkout warning: {stderr.decode().strip()}")
        return proc.returncode == 0
    except Exception as e:
        print(f"  Checkout error: {e}")
        return False


async def _pull_latest(working_dir: str) -> bool:
    """Pull latest changes from remote."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "pull", "--rebase",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False


async def _revert_changes(working_dir: str) -> bool:
    """Revert all uncommitted changes."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "checkout", "--", ".",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False


async def _commit_and_push(
    prefix: str,
    iteration: int,
    files: List[str],
    working_dir: str
) -> Optional[str]:
    """Commit and push fixes. Returns commit SHA or None."""
    try:
        # Check for changes
        status_proc = await asyncio.create_subprocess_exec(
            "git", "status", "--porcelain",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir
        )
        stdout, _ = await status_proc.communicate()

        if not stdout.decode().strip():
            return None

        # Stage files
        if files:
            add_proc = await asyncio.create_subprocess_exec(
                "git", "add", "--", *files,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir
            )
            await add_proc.communicate()
        else:
            add_proc = await asyncio.create_subprocess_exec(
                "git", "add", "-A",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir
            )
            await add_proc.communicate()

        # Commit
        msg = f"{prefix}Auto-fix issues (iteration {iteration})"
        commit_proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", msg,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir
        )
        stdout, stderr = await commit_proc.communicate()

        if commit_proc.returncode != 0:
            output = stdout.decode() + stderr.decode()
            if "nothing to commit" in output:
                return None
            print(f"    Commit error: {stderr.decode()}")
            return None

        # Get commit SHA
        sha_proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir
        )
        stdout, _ = await sha_proc.communicate()
        commit_sha = stdout.decode().strip()

        # Push
        push_proc = await asyncio.create_subprocess_exec(
            "git", "push",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir
        )
        _, stderr = await push_proc.communicate()

        if push_proc.returncode != 0:
            print(f"    Push error: {stderr.decode()}")
            return None

        return commit_sha

    except Exception as e:
        print(f"    Git error: {e}")
        return None


async def _do_merge(github: GitHubTool) -> bool:
    """Merge the PR."""
    try:
        print("\n[MERGE] Merging PR...")
        if not hasattr(github, 'pr') or github.pr is None:
            print("  FAIL: PR not initialized")
            return False
        github.pr.merge(merge_method="squash")
        print("  OK: PR merged!")
        return True
    except Exception as e:
        print(f"  FAIL: Merge failed: {e}")
        return False


def _print_summary(
    result: LoopResult,
    statuses: List[LoopStatus],
    unfixable_issues: Set[str],
    fixed_in_iteration: Dict[int, Set[str]]
):
    """Print a comprehensive summary."""
    print(f"\n{'='*60}")
    print(f"FEEDBACK LOOP COMPLETE")
    print(f"{'='*60}")

    print(f"Result: {result.value.upper()}")

    total_found = sum(s.issues_found for s in statuses)
    total_fixed = sum(s.issues_fixed for s in statuses)
    total_skipped = sum(s.issues_skipped for s in statuses)
    total_time = sum(s.duration_ms for s in statuses)

    print(f"\nStatistics:")
    print(f"  Iterations:     {len(statuses)}")
    print(f"  Issues found:   {total_found}")
    print(f"  Issues fixed:   {total_fixed}")
    print(f"  Issues skipped: {total_skipped}")
    print(f"  Unfixable:      {len(unfixable_issues)}")
    print(f"  Total time:     {total_time/1000:.1f}s")

    if statuses:
        print(f"\nIteration details:")
        for s in statuses:
            test_info = ""
            if s.tests_passed is not None:
                test_info = " tests:PASS" if s.tests_passed else " tests:FAIL"
            commit_info = f" [{s.commit_sha[:8]}]" if s.commit_sha else ""
            print(f"  [{s.iteration}] found:{s.issues_found} fixed:{s.issues_fixed} skip:{s.issues_skipped}{test_info}{commit_info}")

    print(f"{'='*60}\n")


# Synchronous wrapper
def run_feedback_loop_sync(
    repo: str,
    pr_number: int,
    config: Optional[LoopConfig] = None,
    github_token: Optional[str] = None,
) -> Tuple[LoopResult, List[LoopStatus]]:
    """Synchronous wrapper for run_feedback_loop."""
    return asyncio.run(run_feedback_loop(repo, pr_number, config, github_token))
