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
    config.parallel_validation = args.parallel

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
        help="Validate issues in parallel"
    )
    review_parser.add_argument(
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
    else:
        # No subcommand - show help
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
