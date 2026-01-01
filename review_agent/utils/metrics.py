"""Metrics calculation utilities for review agent."""

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timedelta

from ..models import ValidatedIssue, PotentialIssue


@dataclass
class ReviewMetrics:
    """Review metrics calculated from validation results."""
    
    # Basic counts
    total_potential: int = 0
    total_validated: int = 0
    valid_issues: int = 0
    false_positives: int = 0
    
    # Precision metrics
    precision: float = 0.0  # Valid issues / Total reported
    false_positive_rate: float = 0.0  # False positives / Total reported
    
    # Severity breakdown
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    
    # Confidence stats
    avg_confidence: float = 0.0
    min_confidence: float = 1.0
    max_confidence: float = 0.0
    
    # Timing
    review_duration_ms: Optional[int] = None
    
    def __post_init__(self):
        """Calculate derived metrics."""
        if self.total_validated > 0:
            self.precision = self.valid_issues / self.total_validated
            self.false_positive_rate = self.false_positives / self.total_validated


def calculate_metrics(
    potential_issues: List[PotentialIssue],
    validated_issues: List[ValidatedIssue],
    duration_ms: Optional[int] = None
) -> ReviewMetrics:
    """
    Calculate review metrics from potential and validated issues.
    
    Args:
        potential_issues: Issues found in Stage 1
        validated_issues: Issues validated in Stage 2
        duration_ms: Review duration in milliseconds
        
    Returns:
        ReviewMetrics object with calculated statistics
    """
    total_potential = len(potential_issues)
    total_validated = len(validated_issues)
    
    valid_issues = [v for v in validated_issues if v.is_valid]
    false_positives = total_validated - len(valid_issues)
    
    # Severity breakdown
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for issue in valid_issues:
        severity = issue.issue.severity.lower()
        if severity in severity_counts:
            severity_counts[severity] += 1
    
    # Confidence statistics
    confidences = [v.confidence for v in valid_issues if v.is_valid]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    min_confidence = min(confidences) if confidences else 1.0
    max_confidence = max(confidences) if confidences else 0.0
    
    metrics = ReviewMetrics(
        total_potential=total_potential,
        total_validated=total_validated,
        valid_issues=len(valid_issues),
        false_positives=false_positives,
        critical_count=severity_counts["critical"],
        high_count=severity_counts["high"],
        medium_count=severity_counts["medium"],
        low_count=severity_counts["low"],
        avg_confidence=avg_confidence,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        review_duration_ms=duration_ms,
    )
    
    return metrics


def format_metrics_report(metrics: ReviewMetrics) -> str:
    """
    Format metrics as a human-readable report.
    
    Args:
        metrics: ReviewMetrics object
        
    Returns:
        Formatted report string
    """
    lines = [
        "## Review Metrics",
        "",
        "### Summary",
        f"- Potential issues found: {metrics.total_potential}",
        f"- Validated issues: {metrics.total_validated}",
        f"- Valid issues: {metrics.valid_issues}",
        f"- False positives: {metrics.false_positives}",
        "",
        "### Quality Metrics",
        f"- Precision: {metrics.precision:.1%}",
        f"- False Positive Rate: {metrics.false_positive_rate:.1%}",
        "",
        "### Severity Breakdown",
        f"- Critical: {metrics.critical_count}",
        f"- High: {metrics.high_count}",
        f"- Medium: {metrics.medium_count}",
        f"- Low: {metrics.low_count}",
        "",
        "### Confidence Statistics",
        f"- Average: {metrics.avg_confidence:.1%}",
        f"- Range: {metrics.min_confidence:.1%} - {metrics.max_confidence:.1%}",
    ]
    
    if metrics.review_duration_ms:
        duration_sec = metrics.review_duration_ms / 1000
        lines.append("")
        lines.append("### Performance")
        lines.append(f"- Review duration: {duration_sec:.2f}s")
    
    return "\n".join(lines)


def check_quality_targets(metrics: ReviewMetrics) -> dict:
    """
    Check if metrics meet PRD quality targets.
    
    Targets from PRD.md Section 7:
    - Precision > 80%
    - False Positive Rate < 20%
    
    Args:
        metrics: ReviewMetrics object
        
    Returns:
        Dictionary with target check results
    """
    targets = {
        "precision_target": metrics.precision >= 0.80,
        "fpr_target": metrics.false_positive_rate <= 0.20,
    }
    
    targets["all_targets_met"] = all(targets.values())
    
    return targets
