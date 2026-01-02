"""SQL vulnerability test."""

def get_user(user_id: str) -> str:
    """Get user by ID."""
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    return query
