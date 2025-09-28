"""The typed :class:`Page` response envelope."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Page[T](BaseModel):
    """A page of results plus the metadata needed to fetch neighbours.

    ``items`` may hold ORM instances (they are validated/serialised by an
    outer ``response_model`` in FastAPI), so arbitrary types are allowed.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    total: int
    limit: int
    offset: int
    next_cursor: str | None = None

    @property
    def has_next(self) -> bool:
        """True when at least one more row exists after this page."""
        if self.next_cursor is not None:
            return True
        return self.offset + len(self.items) < self.total

    @property
    def has_prev(self) -> bool:
        """True when the page does not start at the first row."""
        return self.offset > 0

    @property
    def page_count(self) -> int:
        """Total number of pages given the current ``limit`` (min 1)."""
        if self.limit <= 0:
            return 1
        return max(1, -(-self.total // self.limit))  # ceil division
