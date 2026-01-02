#!/usr/bin/env python3
"""
AI PR Review Agent - Main Entry Point

Uses Claude Agent SDK with MCP servers (serena, context7, sequential-thinking)
to perform intelligent code review on GitHub Pull Requests.

Usage:
    python -m review_agent.main --repo owner/repo --pr-number 123

Or via GitHub Actions (see .github/workflows/pr-review.yml)
"""

import argparse
import asyncio
import sys
from typing import List

from .config import ReviewConfig
from .models import ValidatedIssue
from .pipeline import identify_issues, validate_issues
from .tools import GitHubTool, parse_pr_diff, format_hunks
from .utils import setup_logging, get_logger


async def run_review(config: ReviewConfig) -> dict:
    """
    Run the complete PR review pipeline.

    Args:
        config: Review configuration

    Returns:
        Dictionary with review statistics
    """
    logger = get_logger()

    logger.info(f"Starting review for {config.repo} PR #{config.pr_number}")

    # Initialize GitHub tool
    github = GitHubTool(
        repo=config.repo,
        pr_number=config.pr_number,
        token=config.github_token
    )

    # Get PR diff
    logger.info("Fetching PR diff...")
    diff_text = github.get_diff()

    if not diff_text.strip():
        logger.info("No changes found in PR")
        return {"status": "no_changes", "potential": 0, "valid": 0}

    # Parse diff into hunks
    file_diffs = parse_pr_diff(diff_text)
    hunks_text = format_hunks(file_diffs)

    logger.info(f"Analyzing {len(file_diffs)} changed files...")

    # Stage 1: Identify potential issues
    logger.info("Stage 1: Identifying potential issues...")
    potential_issues = await identify_issues(hunks_text)
    logger.info(f"Stage 1 complete: Found {len(potential_issues)} potential issues")

    # Filter by min_severity before Stage 2 (skip validation for low severity)
    severity_order = ["low", "medium", "high", "critical"]
    min_sev_idx = severity_order.index(config.min_severity)
    filtered_issues = [
        issue for issue in potential_issues
        if severity_order.index(issue.severity.lower()) >= min_sev_idx
    ]

    if len(filtered_issues) < len(potential_issues):
        skipped = len(potential_issues) - len(filtered_issues)
        logger.info(f"Filtered out {skipped} issues below {config.min_severity} severity")

    potential_issues = filtered_issues

    if not potential_issues:
        logger.info("No potential issues found")
        if config.post_summary:
            github.post_review_summary([], {"potential": 0, "valid": 0, "false_positives": 0})
        return {"status": "clean", "potential": 0, "valid": 0}

    # Stage 2: Validate issues with evidence
    logger.info("Stage 2: Validating issues with evidence...")
    validated_issues = await validate_issues(
        potential_issues,
        parallel=config.parallel_validation
    )

    # Filter by confidence and severity
    reportable_issues = filter_reportable_issues(validated_issues, config)

    valid_count = len([i for i in validated_issues if i.is_valid])
    false_positives = len(potential_issues) - valid_count

    logger.info(f"Stage 2 complete: {valid_count} valid issues, {false_positives} false positives filtered")
    logger.info(f"Reporting {len(reportable_issues)} issues (after confidence/severity filtering)")

    stats = {
        "status": "completed",
        "potential": len(potential_issues),
        "valid": valid_count,
        "false_positives": false_positives,
        "reported": len(reportable_issues),
    }

    # Post comments
    if config.post_comments and reportable_issues:
        logger.info("Posting review comments...")
        for issue in reportable_issues:
            success = github.post_review_comment(issue)
            if not success:
                logger.warning(f"Failed to post comment for {issue.issue.file_path}:{issue.issue.line_start}")

    # Post summary
    if config.post_summary:
        logger.info("Posting review summary...")
        github.post_review_summary(validated_issues, stats)

    logger.info("Review complete!")
    return stats


def filter_reportable_issues(
    validated_issues: List[ValidatedIssue],
    config: ReviewConfig
) -> List[ValidatedIssue]:
    """Filter issues based on confidence and severity settings."""
    reportable = []

    for issue in validated_issues:
        # Skip if not valid or below confidence threshold
        if not issue.is_valid:
            continue
        if issue.confidence < config.min_confidence:
            continue

        # Check severity settings
        severity = issue.issue.severity.lower()
        if severity == "critical" and not config.report_critical:
            continue
        if severity == "high" and not config.report_high:
            continue
        if severity == "medium" and not config.report_medium:
            continue
        if severity == "low" and not config.report_low:
            continue

        reportable.append(issue)

    return reportable


def cmd_init(args):
    """Handle 'init' subcommand."""
    from pathlib import Path
    from .cli import init_repository

    target = Path(args.path) if args.path else Path.cwd()
    success = init_repository(target)
    sys.exit(0 if success else 1)


def cmd_review(args):
    """Handle 'review' subcommand."""
    import logging
    setup_logging(level=logging.DEBUG if args.debug else logging.INFO)
    logger = get_logger()

    # Build config
    config = ReviewConfig.from_env()

    if args.repo:
        config.repo = args.repo
    if args.pr_number:
        config.pr_number = args.pr_number

    config.min_confidence = args.min_confidence
    config.post_comments = not args.no_comments
    config.post_summary = not args.no_summary
    config.report_low = args.report_low
    config.parallel_validation = args.parallel and not args.no_parallel
    config.min_severity = args.min_severity

    # Validate
    if not config.repo:
        logger.error("Repository required. Use --repo or set GITHUB_REPOSITORY env var")
        sys.exit(1)
    if not config.pr_number:
        logger.error("PR number required. Use --pr-number or set PR_NUMBER env var")
        sys.exit(1)

    # Run
    try:
        stats = asyncio.run(run_review(config))
        logger.info(f"Review stats: {stats}")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Review failed: {e}")
        sys.exit(1)


def cmd_orchestrate(args):
    """Handle 'orchestrate' subcommand."""
    import logging
    setup_logging(level=logging.DEBUG if args.debug else logging.INFO)
    logger = get_logger()

    from .orchestrator import PROrchestrator
    from .models import OrchestratorConfig

    if not args.repo:
        logger.error("Repository required. Use --repo")
        sys.exit(1)

    config = OrchestratorConfig(
        merge_method=args.merge_method,
        auto_merge=args.auto_merge,
        delete_branch_after_merge=not args.keep_branch,
        max_parallel_reviews=args.max_parallel,
    )

    orchestrator = PROrchestrator(
        repo=args.repo,
        config=config
    )

    async def run():
        # Load PRs
        await orchestrator.load_open_prs(base=args.base)

        # Analyze
        plan = await orchestrator.analyze()

        if args.dry_run:
            result = await orchestrator.dry_run(plan)
            print("\n=== Dry Run Results ===")
            print(f"Total PRs: {result['plan']['total_prs']}")
            print(f"Merge order: {result['plan']['order']}")
            print(f"Parallel groups: {result['plan']['parallel_groups']}")
            print(f"Potential conflicts: {result['plan']['conflicts']}")
            print("\nMerge readiness:")
            for status in result['merge_readiness']:
                ready = "READY" if status['ready'] else "NOT READY"
                print(f"  PR #{status['pr_number']}: {ready}")
                if not status['mergeable']:
                    print(f"    - Merge: {status['merge_reason']}")
                if not status['ci_passed']:
                    print(f"    - CI: {status['ci_status']}")
            return

        # Execute
        review_config = ReviewConfig(
            repo=args.repo,
            parallel_validation=True,
            min_severity="medium",
        )

        result = await orchestrator.execute_plan(
            plan,
            review_config=review_config,
            merge=args.auto_merge
        )

        print("\n=== Orchestration Results ===")
        print(f"Total PRs: {result['summary']['total_prs']}")
        print(f"Reviewed: {result['summary']['reviewed']}")
        print(f"Passed: {result['summary']['passed']}")
        print(f"Failed: {result['summary']['failed']}")
        if args.auto_merge:
            print(f"Merged: {result['summary']['merged']}")

    try:
        asyncio.run(run())
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Orchestration failed: {e}")
        sys.exit(1)


def cmd_testgen(args):
    """Handle 'testgen' subcommand (Phase 3)."""
    import logging
    setup_logging(level=logging.DEBUG if args.debug else logging.INFO)
    logger = get_logger()

    from .pipeline import generate_tests, CoverageGate
    from .config import MergeRules
    from .models import TestGenConfig

    # Initialize GitHub tool
    github = GitHubTool(
        repo=args.repo,
        pr_number=args.pr_number
    )

    async def run():
        logger.info(f"Starting test generation for {args.repo} PR #{args.pr_number}")

        # Get PR diff
        logger.info("Fetching PR diff...")
        diff_text = github.get_diff()
        changed_files = github.get_changed_files()

        if not diff_text.strip():
            logger.info("No changes found in PR")
            return

        # First run Stage 1,2 to get validated issues
        logger.info("Running Stage 1,2 review first...")
        file_diffs = parse_pr_diff(diff_text)
        hunks_text = format_hunks(file_diffs)

        potential_issues = await identify_issues(hunks_text)
        validated_issues = await validate_issues(potential_issues, parallel=True)

        valid_count = len([i for i in validated_issues if i.is_valid])
        logger.info(f"Found {valid_count} valid issues for regression tests")

        # Stage 3: Generate tests
        logger.info("Stage 3: Generating tests...")
        config = TestGenConfig()
        generated_tests = await generate_tests(diff_text, validated_issues, config)

        logger.info(f"Generated {len(generated_tests)} test files")
        for test in generated_tests:
            logger.info(f"  - {test.file_path} ({test.test_count} tests)")

        if args.dry_run:
            print("\n=== Dry Run Results ===")
            print(f"Would generate {len(generated_tests)} test files:")
            for test in generated_tests:
                print(f"  - {test.file_path}")
                print(f"    Covers: {', '.join(test.covers_functions)}")
                print(f"    Tests: {test.test_count}")
            return

        if args.skip_coverage:
            logger.info("Skipping coverage gate (--skip-coverage)")
            return

        # Stage 4: Coverage gate
        logger.info("Stage 4: Running coverage gate...")
        rules = MergeRules(
            min_total_coverage=args.min_coverage,
            min_new_code_coverage=args.min_new_coverage,
        )

        gate = CoverageGate(rules=rules)
        decision = await gate.execute(generated_tests, validated_issues, changed_files)

        # Print decision
        print("\n" + decision.summary())

        # Auto-commit if requested
        if args.auto_commit and decision.approved:
            logger.info("Auto-committing generated tests...")
            # TODO: Implement git commit logic
            logger.warning("Auto-commit not yet implemented")

        return decision

    try:
        asyncio.run(run())
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Test generation failed: {e}")
        sys.exit(1)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AI PR Review Agent using Claude Agent SDK"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize review-agent in a repository")
    init_parser.add_argument(
        "path",
        nargs="?",
        help="Target repository path (default: current directory)"
    )

    # review command
    review_parser = subparsers.add_parser("review", help="Run PR review")
    review_parser.add_argument(
        "--repo",
        type=str,
        help="Repository in format owner/repo"
    )
    review_parser.add_argument(
        "--pr-number",
        type=int,
        help="Pull request number"
    )
    review_parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.7,
        help="Minimum confidence threshold (default: 0.7)"
    )
    review_parser.add_argument(
        "--no-comments",
        action="store_true",
        help="Don't post inline comments"
    )
    review_parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Don't post summary comment"
    )
    review_parser.add_argument(
        "--report-low",
        action="store_true",
        help="Include low severity issues"
    )
    review_parser.add_argument(
        "--parallel",
        action="store_true",
        default=True,
        help="Validate issues in parallel (default: enabled)"
    )
    review_parser.add_argument(
        "--no-parallel",
        action="store_true",
        help="Disable parallel validation"
    )
    review_parser.add_argument(
        "--min-severity",
        type=str,
        default="medium",
        choices=["low", "medium", "high", "critical"],
        help="Minimum severity to validate (default: medium, skips low)"
    )
    review_parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    # orchestrate command (Phase 2)
    orch_parser = subparsers.add_parser(
        "orchestrate",
        help="Orchestrate multiple PRs (review, merge in optimal order)"
    )
    orch_parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="Repository in format owner/repo"
    )
    orch_parser.add_argument(
        "--base",
        type=str,
        default="main",
        help="Base branch to target (default: main)"
    )
    orch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and show plan without executing"
    )
    orch_parser.add_argument(
        "--auto-merge",
        action="store_true",
        help="Automatically merge PRs that pass review"
    )
    orch_parser.add_argument(
        "--merge-method",
        type=str,
        default="squash",
        choices=["squash", "merge", "rebase"],
        help="Merge method to use (default: squash)"
    )
    orch_parser.add_argument(
        "--keep-branch",
        action="store_true",
        help="Don't delete branches after merge"
    )
    orch_parser.add_argument(
        "--max-parallel",
        type=int,
        default=5,
        help="Maximum parallel reviews (default: 5)"
    )
    orch_parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    # testgen command (Phase 3)
    testgen_parser = subparsers.add_parser(
        "testgen",
        help="Generate tests and run coverage gate (Phase 3)"
    )
    testgen_parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="Repository in format owner/repo"
    )
    testgen_parser.add_argument(
        "--pr-number",
        type=int,
        required=True,
        help="Pull request number"
    )
    testgen_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate tests without writing or running them"
    )
    testgen_parser.add_argument(
        "--skip-coverage",
        action="store_true",
        help="Skip coverage gate (only generate tests)"
    )
    testgen_parser.add_argument(
        "--min-coverage",
        type=float,
        default=80.0,
        help="Minimum total coverage required (default: 80%%)"
    )
    testgen_parser.add_argument(
        "--min-new-coverage",
        type=float,
        default=90.0,
        help="Minimum coverage for new code (default: 90%%)"
    )
    testgen_parser.add_argument(
        "--auto-commit",
        action="store_true",
        help="Commit generated tests to PR branch"
    )
    testgen_parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    # Route to subcommand
    if args.command == "init":
        cmd_init(args)
    elif args.command == "review":
        cmd_review(args)
    elif args.command == "orchestrate":
        cmd_orchestrate(args)
    elif args.command == "testgen":
        cmd_testgen(args)
    else:
        # No subcommand - show help
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
