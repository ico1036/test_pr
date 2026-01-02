"""User repository for database operations."""

def get_user_by_id(user_id: str) -> tuple:
    """Fetch user from database by ID."""
    query = "SELECT * FROM users WHERE id = ?"
    return (query, (user_id,))
