"""Parsed, validated query parameters produced by the FastAPI dependency."""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import PageflowError
from .filters import OPERATORS


@dataclass(frozen=True, slots=True)
class SortKey:
    """A single ``ORDER BY`` term."""

    field: str
    descending: bool = False


@dataclass(frozen=True, slots=True)
class Filter:
    """A single ``field op value`` predicate, value still a raw string."""

    field: str
    op: str
    value: str


@dataclass(frozen=True, slots=True)
class QueryParams:
    """Everything a request asks for, already parsed and range-checked."""

    limit: int
    offset: int
    sort: list[SortKey] = field(default_factory=list)
    filters: list[Filter] = field(default_factory=list)
    cursor: str | None = None


def parse_sort(raw: str | None) -> list[SortKey]:
    """Parse ``sort=field:asc,other:desc`` (also ``-field`` shorthand)."""
    if not raw:
        return []
    keys: list[SortKey] = []
    for chunk in (c.strip() for c in raw.split(",")):
        if not chunk:
            continue
        if ":" in chunk:
            name, _, direction = chunk.partition(":")
            direction = direction.strip().lower()
            if direction not in ("asc", "desc"):
                raise PageflowError(
                    f"sort direction must be 'asc' or 'desc', got {direction!r}",
                    field=name.strip(),
                )
            keys.append(SortKey(name.strip(), descending=direction == "desc"))
        elif chunk.startswith("-"):
            keys.append(SortKey(chunk[1:].strip(), descending=True))
        else:
            keys.append(SortKey(chunk, descending=False))
    return keys


def parse_filters(raw: list[str] | None) -> list[Filter]:
    """Parse repeated ``filter=field:op:value`` query parameters."""
    if not raw:
        return []
    parsed: list[Filter] = []
    for item in raw:
        name, sep_op, rest = item.partition(":")
        op, sep_val, value = rest.partition(":")
        if not sep_op or not sep_val:
            raise PageflowError(
                f"filter must look like 'field:op:value', got {item!r}",
                field=name or None,
            )
        op = op.strip().lower()
        if op not in OPERATORS:
            raise PageflowError(f"unknown filter operator {op!r}", field=name)
        parsed.append(Filter(field=name.strip(), op=op, value=value))
    return parsed
