"""Multi-PR Orchestration (Phase 2).

This module provides:
- PROrchestrator: Main orchestrator for managing multiple PRs
- DependencyAnalyzer: Analyzes dependencies between PRs
- ConflictPredictor: Predicts file conflicts between PRs
- MergeExecutor: Executes merge operations safely
"""

from .orchestrator import PROrchestrator
from .dependency import DependencyAnalyzer
from .conflict import ConflictPredictor
from .merge import MergeExecutor

__all__ = [
    "PROrchestrator",
    "DependencyAnalyzer",
    "ConflictPredictor",
    "MergeExecutor",
]
