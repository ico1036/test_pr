"""Storage Tool for collecting structured agent outputs."""

from typing import List, TypeVar, Generic, Any

T = TypeVar('T')


class StorageTool(Generic[T]):
    """
    Collects agent outputs in structured form.
    Uses Tool Call as data transfer layer.

    Based on Hyperithm's pattern:
    "Treat agent as black-box function with fixed I/O schema"
    """

    def __init__(self):
        self._values: List[T] = []

    def store(self, value: T) -> dict[str, Any]:
        """
        Tool function called by agent to store results.

        Returns MCP-compatible response format.
        """
        self._values.append(value)
        return {
            "content": [{
                "type": "text",
                "text": f"Stored successfully. Total: {len(self._values)}"
            }]
        }

    @property
    def values(self) -> List[T]:
        """Get copy of stored values."""
        return self._values.copy()

    def clear(self):
        """Clear all stored values."""
        self._values.clear()

    def __len__(self) -> int:
        return len(self._values)
