"""Git diff parsing utilities."""

from dataclasses import dataclass
from typing import List, Optional
import re


@dataclass
class Hunk:
    """Represents a single hunk from a git diff."""
    file_path: str
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    content: str
    header: str


@dataclass
class FileDiff:
    """Represents all changes to a single file."""
    old_path: Optional[str]
    new_path: str
    hunks: List[Hunk]
    is_new_file: bool = False
    is_deleted: bool = False


def parse_pr_diff(diff_text: str) -> List[FileDiff]:
    """
    Parse a unified diff string into structured FileDiff objects.

    Args:
        diff_text: Raw unified diff output from git

    Returns:
        List of FileDiff objects containing parsed hunks
    """
    if not diff_text or not diff_text.strip():
        return []

    file_diffs = []
    current_file: Optional[FileDiff] = None
    current_hunk_lines: List[str] = []
    current_hunk_header: Optional[str] = None

    # Regex patterns
    file_header_pattern = re.compile(r'^diff --git a/(.*) b/(.*)$')
    old_file_pattern = re.compile(r'^--- (?:a/)?(.*)$')
    new_file_pattern = re.compile(r'^\+\+\+ (?:b/)?(.*)$')
    hunk_header_pattern = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$')

    lines = diff_text.split('\n')

    def save_current_hunk():
        nonlocal current_hunk_lines, current_hunk_header
        if current_file and current_hunk_header and current_hunk_lines:
            match = hunk_header_pattern.match(current_hunk_header)
            if match:
                hunk = Hunk(
                    file_path=current_file.new_path,
                    old_start=int(match.group(1)),
                    old_lines=int(match.group(2) or 1),
                    new_start=int(match.group(3)),
                    new_lines=int(match.group(4) or 1),
                    content='\n'.join(current_hunk_lines),
                    header=current_hunk_header
                )
                current_file.hunks.append(hunk)
        current_hunk_lines = []
        current_hunk_header = None

    for line in lines:
        # Check for new file diff
        file_match = file_header_pattern.match(line)
        if file_match:
            # Save previous hunk and file
            save_current_hunk()
            if current_file:
                file_diffs.append(current_file)

            current_file = FileDiff(
                old_path=file_match.group(1),
                new_path=file_match.group(2),
                hunks=[]
            )
            continue

        # Check for new/deleted file markers
        if current_file:
            if line.startswith('new file mode'):
                current_file.is_new_file = True
                continue
            if line.startswith('deleted file mode'):
                current_file.is_deleted = True
                continue

        # Check for hunk header
        hunk_match = hunk_header_pattern.match(line)
        if hunk_match:
            save_current_hunk()
            current_hunk_header = line
            continue

        # Collect hunk content
        if current_hunk_header is not None:
            if line.startswith('+') or line.startswith('-') or line.startswith(' '):
                current_hunk_lines.append(line)

    # Save final hunk and file
    save_current_hunk()
    if current_file:
        file_diffs.append(current_file)

    return file_diffs


def format_hunks(file_diffs: List[FileDiff]) -> str:
    """
    Format parsed diffs into a readable string for LLM analysis.

    Args:
        file_diffs: List of parsed FileDiff objects

    Returns:
        Formatted string representation of all changes
    """
    if not file_diffs:
        return "No changes found."

    output_parts = []

    for file_diff in file_diffs:
        # File header
        status = ""
        if file_diff.is_new_file:
            status = " (NEW FILE)"
        elif file_diff.is_deleted:
            status = " (DELETED)"

        output_parts.append(f"\n### File: {file_diff.new_path}{status}\n")

        for i, hunk in enumerate(file_diff.hunks, 1):
            output_parts.append(f"\n#### Hunk {i} (lines {hunk.new_start}-{hunk.new_start + hunk.new_lines - 1}):\n")
            output_parts.append("```diff")
            output_parts.append(hunk.content)
            output_parts.append("```\n")

    return '\n'.join(output_parts)


def get_changed_functions(file_diffs: List[FileDiff]) -> List[dict]:
    """
    Extract function/method names that were changed.

    This is a simple heuristic that looks for common function patterns.
    """
    changed_functions = []

    # Patterns for different languages
    patterns = {
        'python': re.compile(r'^\+\s*(?:async\s+)?def\s+(\w+)\s*\('),
        'javascript': re.compile(r'^\+\s*(?:async\s+)?(?:function\s+(\w+)|(\w+)\s*(?:=|:)\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))'),
        'typescript': re.compile(r'^\+\s*(?:async\s+)?(?:function\s+(\w+)|(\w+)\s*(?:=|:)\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))'),
    }

    for file_diff in file_diffs:
        ext = file_diff.new_path.split('.')[-1] if '.' in file_diff.new_path else ''

        # Determine language
        if ext == 'py':
            pattern = patterns['python']
        elif ext in ('js', 'jsx'):
            pattern = patterns['javascript']
        elif ext in ('ts', 'tsx'):
            pattern = patterns['typescript']
        else:
            continue

        for hunk in file_diff.hunks:
            for line in hunk.content.split('\n'):
                match = pattern.match(line)
                if match:
                    func_name = match.group(1) or match.group(2)
                    if func_name:
                        changed_functions.append({
                            'file': file_diff.new_path,
                            'function': func_name,
                            'line': hunk.new_start
                        })

    return changed_functions
