"""Filter operators and value coercion for SQLAlchemy columns."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.orm import InstrumentedAttribute

from .errors import PageflowError

# Operators that consume a single scalar value.
_SCALAR_OPS: dict[str, Callable[[InstrumentedAttribute[Any], Any], ColumnElement[bool]]] = {
    "eq": lambda col, v: col == v,
    "ne": lambda col, v: col != v,
    "lt": lambda col, v: col < v,
    "lte": lambda col, v: col <= v,
    "gt": lambda col, v: col > v,
    "gte": lambda col, v: col >= v,
    "like": lambda col, v: col.like(v),
    "ilike": lambda col, v: col.ilike(v),
}

# Operators that consume a comma-separated list of values.
_LIST_OPS = frozenset({"in", "nin"})

# Operators that take a boolean-ish value and ignore column typing.
_NULL_OPS = frozenset({"isnull"})

OPERATORS: frozenset[str] = frozenset(_SCALAR_OPS) | _LIST_OPS | _NULL_OPS


def _coerce_scalar(raw: str, python_type: type[Any], *, field: str) -> Any:
    """Coerce a raw query-string token into the column's Python type."""
    try:
        if python_type is bool:
            return _coerce_bool(raw)
        if python_type in (int, float):
            return python_type(raw)
        if python_type is datetime:
            return datetime.fromisoformat(raw)
        if python_type is date:
            return date.fromisoformat(raw)
    except (ValueError, TypeError) as exc:
        raise PageflowError(
            f"cannot parse {raw!r} as {python_type.__name__} for field {field!r}",
            field=field,
        ) from exc
    return raw  # str and anything else pass through unchanged


def _coerce_bool(raw: str) -> bool:
    lowered = raw.strip().lower()
    if lowered in ("true", "1", "yes", "on"):
        return True
    if lowered in ("false", "0", "no", "off"):
        return False
    raise ValueError(raw)


def build_clause(
    column: InstrumentedAttribute[Any],
    op: str,
    raw_value: str,
    *,
    field: str,
) -> ColumnElement[bool]:
    """Build a SQLAlchemy boolean clause for ``column <op> raw_value``.

    ``raw_value`` is coerced to the column's Python type first, so callers
    always pass strings straight from the query string.
    """
    if op not in OPERATORS:
        raise PageflowError(f"unknown operator {op!r} for field {field!r}", field=field)

    python_type = _column_python_type(column)

    if op in _NULL_OPS:
        want_null = _coerce_bool(raw_value) if raw_value else True
        return column.is_(None) if want_null else column.is_not(None)

    if op in _LIST_OPS:
        values = [
            _coerce_scalar(tok, python_type, field=field)
            for tok in (t.strip() for t in raw_value.split(","))
            if tok
        ]
        if not values:
            raise PageflowError(f"operator {op!r} needs at least one value", field=field)
        return column.in_(values) if op == "in" else column.notin_(values)

    value = _coerce_scalar(raw_value, python_type, field=field)
    return _SCALAR_OPS[op](column, value)


def _column_python_type(column: InstrumentedAttribute[Any]) -> type[Any]:
    try:
        return column.type.python_type  # type: ignore[no-any-return]
    except NotImplementedError:
        return str
