"""Integration tests against a real in-memory SQLite database."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from pageflow import QueryParams, SortKey
from tests.conftest import User, user_paginator


def _names(page: object) -> list[str]:
    return [u.name for u in page.items]  # type: ignore[attr-defined]


def test_default_limit_and_total(session: Session) -> None:
    page = user_paginator.paginate(session, select(User), QueryParams(limit=5, offset=0))
    assert page.total == 12
    assert len(page.items) == 5
    assert page.has_next is True
    assert page.has_prev is False
    assert page.page_count == 3


def test_offset_walks_pages(session: Session) -> None:
    p1 = user_paginator.paginate(
        session, select(User), QueryParams(limit=5, offset=0, sort=[SortKey("id")])
    )
    p3 = user_paginator.paginate(
        session, select(User), QueryParams(limit=5, offset=10, sort=[SortKey("id")])
    )
    assert _names(p1) == ["alice", "bob", "carol", "dave", "erin"]
    assert _names(p3) == ["mallory", "niaj"]
    assert p3.has_next is False
    assert p3.has_prev is True


def test_sort_desc_by_age_with_tiebreak(session: Session) -> None:
    page = user_paginator.paginate(
        session,
        select(User),
        QueryParams(limit=12, offset=0, sort=[SortKey("age", descending=True)]),
    )
    ages = [u.age for u in page.items]
    assert ages == sorted(ages, reverse=True)
    # grace (55) is oldest, frank (22) youngest
    assert page.items[0].name == "grace"
    assert page.items[-1].name == "frank"


def test_filter_gte(session: Session) -> None:
    from pageflow import Filter

    page = user_paginator.paginate(
        session,
        select(User),
        QueryParams(limit=50, offset=0, filters=[Filter("age", "gte", "40")]),
    )
    assert sorted(_names(page)) == ["carol", "grace", "judy"]
    assert page.total == 3


def test_filter_in_and_bool(session: Session) -> None:
    from pageflow import Filter

    page = user_paginator.paginate(
        session,
        select(User),
        QueryParams(
            limit=50,
            offset=0,
            filters=[Filter("age", "in", "25,30"), Filter("active", "eq", "true")],
        ),
    )
    # age in {25,30} AND active: bob, dave, niaj (25) + alice (30); heidi(30) inactive
    assert sorted(_names(page)) == ["alice", "bob", "dave", "niaj"]


def test_filter_like(session: Session) -> None:
    from pageflow import Filter

    page = user_paginator.paginate(
        session,
        select(User),
        QueryParams(limit=50, offset=0, filters=[Filter("name", "like", "%a%")]),
    )
    # names containing 'a': alice, carol, dave, frank, grace, ivan, mallory, niaj
    assert sorted(_names(page)) == [
        "alice",
        "carol",
        "dave",
        "frank",
        "grace",
        "ivan",
        "mallory",
        "niaj",
    ]


def test_date_coercion_on_filter(session: Session) -> None:
    from pageflow import Filter

    page = user_paginator.paginate(
        session,
        select(User),
        QueryParams(limit=50, offset=0, filters=[Filter("joined", "gte", "2020-10-01")]),
    )
    assert sorted(_names(page)) == ["judy", "mallory", "niaj"]
