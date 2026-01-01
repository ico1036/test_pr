"""Data models for issues."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class Severity(Enum):
    """Issue severity levels."""
    CRITICAL = "critical"   # Security, data loss
    HIGH = "high"           # Bugs, serious performance
    MEDIUM = "medium"       # Code quality
    LOW = "low"             # Style, suggestions


class IssueType(Enum):
    """Types of issues that can be detected."""
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    LOGIC_ERROR = "logic_error"
    TYPE_ERROR = "type_error"
    UNUSED_CODE = "unused_code"
    BEST_PRACTICE = "best_practice"


@dataclass
class PotentialIssue:
    """Stage 1 output - potential issue found in code."""
    file_path: str
    line_start: int
    line_end: int
    issue_type: str  # IssueType value
    severity: str    # Severity value
    description: str
    code_snippet: str


@dataclass
class ValidatedIssue:
    """Stage 2 output - validated issue with evidence."""
    issue: PotentialIssue
    is_valid: bool
    evidence: List[str] = field(default_factory=list)
    library_reference: Optional[str] = None
    mitigation: Optional[str] = None
    confidence: float = 0.0
