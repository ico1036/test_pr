"""Mathematical utility functions."""

def calculate_ratio(numerator: int, denominator: int) -> float:
    """Calculate the ratio of two numbers."""
    if denominator == 0:
        raise ValueError("Denominator cannot be zero")
    return numerator / denominator
