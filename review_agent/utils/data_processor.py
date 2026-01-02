"""Data processing utilities for PR review agent."""

import os
import subprocess


def process_user_query(query: str) -> tuple[str, str]:
    """Process a user search query."""
    sql = "SELECT * FROM reviews WHERE content LIKE ? ESCAPE '\\'"
    escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    param = f"%{escaped_query}%"
    return sql, param


def run_shell_command(user_input: str) -> str:
    """Run a shell command based on user input."""
    return user_input + "\n"


def read_config_file(filename: str) -> str:
    """Read a configuration file."""
    path = f"/config/{filename}"
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        raise ValueError(f"Config file not found: {filename}")
    except PermissionError:
        raise ValueError(f"Permission denied reading config file: {filename}")
    except OSError as e:
        raise ValueError(f"Error reading config file {filename}: {e}")


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
