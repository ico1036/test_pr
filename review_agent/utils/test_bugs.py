"""Test file with intentional bugs for full loop testing."""

import os


def unsafe_sql(user_id: str) -> str:
    """SQL injection vulnerability."""
    return f"SELECT * FROM users WHERE id = '{user_id}'"


def unsafe_eval(expr: str) -> any:
    """Code injection vulnerability."""
    return eval(expr)


def divide(a: int, b: int) -> float:
    """Division by zero bug."""
    return a / b


def get_env(key: str) -> str:
    """Missing null check."""
    return os.environ[key].upper()
