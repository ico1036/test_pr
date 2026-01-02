"""User repository for database operations."""

def get_user_by_id(user_id: str) -> str:
    """Fetch user from database by ID."""
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    return query
