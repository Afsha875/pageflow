"""Unit tests for the pure string parsers (no DB, no HTTP)."""

from __future__ import annotations

import pytest

from pageflow import PageflowError, SortKey, parse_filters, parse_sort


def test_parse_sort_multiple_directions() -> None:
    assert parse_sort("name:asc,age:desc") == [
        SortKey("name", descending=False),
        SortKey("age", descending=True),
    ]


def test_parse_sort_dash_shorthand() -> None:
    assert parse_sort("-created,id") == [
        SortKey("created", descending=True),
        SortKey("id", descending=False),
    ]


def test_parse_sort_empty_is_empty() -> None:
    assert parse_sort(None) == []
    assert parse_sort("") == []


def test_parse_sort_bad_direction() -> None:
    with pytest.raises(PageflowError) as exc:
        parse_sort("age:sideways")
    assert exc.value.field == "age"


def test_parse_filters_basic() -> None:
    filters = parse_filters(["age:gte:18", "name:like:a%"])
    assert [(f.field, f.op, f.value) for f in filters] == [
        ("age", "gte", "18"),
        ("name", "like", "a%"),
    ]


def test_parse_filters_value_may_contain_colon() -> None:
    (flt,) = parse_filters(["joined:gte:2020-01-01T09:30:00"])
    assert flt.value == "2020-01-01T09:30:00"


def test_parse_filters_rejects_bad_shape() -> None:
    with pytest.raises(PageflowError):
        parse_filters(["age-18"])


def test_parse_filters_rejects_unknown_operator() -> None:
    with pytest.raises(PageflowError) as exc:
        parse_filters(["age:between:18"])
    assert exc.value.field == "age"
