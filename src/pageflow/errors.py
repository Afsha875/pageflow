"""Error type raised for malformed pagination / filter / sort input."""

from __future__ import annotations


class PageflowError(ValueError):
    """Raised when a query parameter cannot be parsed or is not allowed.

    Carries an HTTP-friendly ``status_code`` (always 400) and a machine
    readable ``field`` so callers/exception handlers can build a clean
    response body without string-parsing the message.
    """

    status_code: int = 400

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field
