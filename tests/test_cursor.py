"""Keyset (cursor) pagination correctness against SQLite."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from pageflow import QueryParams, SortKey
from tests.conftest import User, user_paginator


def _walk_all_by_cursor(session: Session, sort: list[SortKey], limit: int) -> list[str]:
    seen: list[str] = []
    cursor: str | None = ""  # empty string => first cursor page
    while True:
        page = user_paginator.paginate(
            session,
            select(User),
            QueryParams(limit=limit, offset=0, sort=sort, cursor=cursor),
        )
        seen.extend(u.name for u in page.items)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    return seen


def test_cursor_covers_every_row_once_ascending(session: Session) -> None:
    names = _walk_all_by_cursor(session, [SortKey("id")], limit=5)
    assert len(names) == 12
    assert len(set(names)) == 12  # no duplicates, no gaps


def test_cursor_matches_offset_order(session: Session) -> None:
    cursor_order = _walk_all_by_cursor(session, [SortKey("name")], limit=4)
    offset_page = user_paginator.paginate(
        session,
        select(User),
        QueryParams(limit=50, offset=0, sort=[SortKey("name")]),
    )
    offset_order = [u.name for u in offset_page.items]
    assert cursor_order == offset_order


def test_cursor_with_desc_secondary_key(session: Session) -> None:
    # age desc, then id asc tiebreak (auto-appended)
    names = _walk_all_by_cursor(session, [SortKey("age", descending=True)], limit=3)
    full = user_paginator.paginate(
        session,
        select(User),
        QueryParams(limit=50, offset=0, sort=[SortKey("age", descending=True)]),
    )
    assert names == [u.name for u in full.items]


def test_next_cursor_none_on_last_page(session: Session) -> None:
    page = user_paginator.paginate(
        session,
        select(User),
        QueryParams(limit=50, offset=0, sort=[SortKey("id")], cursor=""),
    )
    assert page.next_cursor is None
    assert len(page.items) == 12
