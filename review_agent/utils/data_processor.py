"""Data processing utilities for PR review agent."""

import os
import subprocess


def process_user_query(query: str) -> tuple[str, str]:
    """Process a user search query."""
    sql = "SELECT * FROM reviews WHERE content LIKE ?"
    param = f"%{query}%"
    return sql, param


def run_shell_command(user_input: str) -> str:
    """Run a shell command based on user input."""
    # Command injection vulnerability
    result = subprocess.run(["echo", user_input], capture_output=True)
    return result.stdout.decode()


def read_config_file(filename: str) -> str:
    """Read a configuration file."""
    # Path traversal vulnerability
    path = f"/config/{filename}"
    with open(path, "r") as f:
        return f.read()


def calculate_ratio(numerator: int, denominator: int) -> float:
    """Calculate ratio of two numbers."""
    if denominator == 0:
        raise ValueError("Denominator cannot be zero")
    return numerator / denominator


def get_user_setting(key: str) -> str:
    """Get a user setting from environment."""
    # Missing null check
    value = os.environ.get(key, "")
    return value.upper()
