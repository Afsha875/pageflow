"""pageflow: drop-in FastAPI pagination, filtering and sorting for SQLAlchemy.

Typical usage::

    from pageflow import Paginator, Page
    from sqlalchemy import select

    users = Paginator(User, sortable={"id", "name", "age"}, filterable={"age", "name"})

    @app.get("/users", response_model=Page[UserOut])
    def list_users(params=Depends(users), db: Session = Depends(get_db)):
        return users.paginate(db, select(User), params)
"""

from __future__ import annotations

from .errors import PageflowError
from .filters import OPERATORS, build_clause
from .page import Page
from .paginator import Paginator, install_error_handler
from .params import Filter, QueryParams, SortKey, parse_filters, parse_sort

__all__ = [
    "OPERATORS",
    "Filter",
    "Page",
    "PageflowError",
    "Paginator",
    "QueryParams",
    "SortKey",
    "build_clause",
    "install_error_handler",
    "parse_filters",
    "parse_sort",
]
