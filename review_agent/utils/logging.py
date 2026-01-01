"""Logging utilities."""

import logging
import sys
from typing import Optional


def setup_logging(
    level: int = logging.INFO,
    format_str: Optional[str] = None
) -> logging.Logger:
    """
    Setup logging for the review agent.

    Args:
        level: Logging level (default: INFO)
        format_str: Custom format string

    Returns:
        Configured logger
    """
    if format_str is None:
        format_str = "[%(asctime)s] %(levelname)s - %(message)s"

    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    logger = logging.getLogger("review_agent")
    logger.setLevel(level)

    return logger


def get_logger(name: str = "review_agent") -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
