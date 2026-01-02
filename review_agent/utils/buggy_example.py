"""Example file with intentional bugs for testing auto-fix."""

import os
import subprocess


def unsafe_command(user_input: str) -> str:
    """Execute a command with user input - COMMAND INJECTION VULNERABILITY."""
    # BUG: Command injection vulnerability
    result = subprocess.run(f"echo {user_input}", shell=True, capture_output=True)
    return result.stdout.decode()


def sql_query(table: str, user_id: str) -> str:
    """Build SQL query - SQL INJECTION VULNERABILITY."""
    # BUG: SQL injection vulnerability
    query = f"SELECT * FROM {table} WHERE user_id = '{user_id}'"
    return query


def divide_numbers(a: int, b: int) -> float:
    """Divide two numbers - DIVISION BY ZERO BUG."""
    # BUG: No check for division by zero
    return a / b


def get_item(items: list, index: int) -> any:
    """Get item from list - INDEX OUT OF BOUNDS BUG."""
    # BUG: No bounds checking
    return items[index]


def read_file(filename: str) -> str:
    """Read file contents - PATH TRAVERSAL VULNERABILITY."""
    # BUG: Path traversal vulnerability
    with open(filename, 'r') as f:
        return f.read()


def process_data(data: dict) -> str:
    """Process data dict - NULL POINTER EXCEPTION."""
    # BUG: No null check, will crash if 'name' key missing
    return data['name'].upper()
