"""Example file with intentional bugs for testing auto-fix."""

import os
import subprocess


def unsafe_command(user_input: str) -> str:
    """Execute a command with user input - COMMAND INJECTION VULNERABILITY."""
    # BUG: Command injection vulnerability
    result = subprocess.run(["echo", user_input], capture_output=True)
    return result.stdout.decode()


def sql_query(table: str, user_id: str) -> tuple[str, tuple]:
    """Build SQL query - returns parameterized query and params."""
    allowed_tables = {"users", "orders", "products"}
    if table not in allowed_tables:
        raise ValueError(f"Invalid table name: {table}")
    query = f"SELECT * FROM {table} WHERE user_id = ?"
    return query, (user_id,)


def divide_numbers(a: int, b: int) -> float:
    """Divide two numbers."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


def get_item(items: list, index: int) -> any:
    """Get item from list - INDEX OUT OF BOUNDS BUG."""
    if not items or index < -len(items) or index >= len(items):
        raise IndexError("Index out of bounds")
    return items[index]


def read_file(filename: str, base_dir: str = ".") -> str:
    """Read file contents - PATH TRAVERSAL VULNERABILITY."""
    safe_filename = os.path.basename(filename)
    safe_path = os.path.realpath(os.path.join(base_dir, safe_filename))
    if not safe_path.startswith(os.path.realpath(base_dir) + os.sep):
        raise ValueError("Invalid file path")
    with open(safe_path, 'r') as f:
        return f.read()


def process_data(data: dict) -> str:
    """Process data dict - NULL POINTER EXCEPTION."""
    # BUG: No null check, will crash if 'name' key missing
    name = data.get('name')
    if name is None:
        raise ValueError("'name' key is missing or None")
    return name.upper()
