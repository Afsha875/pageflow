"""The FastAPI dependency plus the select-application / execution helpers."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable, Sequence
from typing import Annotated, Any, cast

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.orm.decl_api import DeclarativeBase
from sqlalchemy.sql.expression import ColumnClause

from .errors import PageflowError
from .filters import _coerce_scalar, _column_python_type, build_clause
from .page import Page
from .params import Filter, QueryParams, SortKey, parse_filters, parse_sort


class Paginator[ModelT: DeclarativeBase]:
    """A configurable FastAPI dependency + query applier for one ORM model.

    Instantiate once per model at import time and reuse it in routes via
    ``Depends(paginator)``. It whitelists which columns may be sorted and
    filtered so untrusted query strings can never touch other columns.
    """

    def __init__(
        self,
        model: type[ModelT],
        *,
        sortable: Iterable[str],
        filterable: Iterable[str],
        default_limit: int = 20,
        max_limit: int = 100,
        default_sort: Sequence[SortKey] | None = None,
    ) -> None:
        self.model = model
        self.sortable = frozenset(sortable)
        self.filterable = frozenset(filterable)
        self.default_limit = default_limit
        self.max_limit = max_limit
        self.default_sort = list(default_sort or [])
        pk = list(model.__mapper__.primary_key)
        if len(pk) != 1:
            raise ValueError("Paginator only supports single-column primary keys")
        self._pk_name: str = pk[0].name

    # -- FastAPI dependency ------------------------------------------------

    def __call__(
        self,
        limit: Annotated[int | None, Query(ge=1, description="Page size")] = None,
        offset: Annotated[int, Query(ge=0, description="Rows to skip")] = 0,
        sort: Annotated[str | None, Query(description="e.g. name:asc,age:desc")] = None,
        filter: Annotated[  # matches the public query-param name
            list[str] | None, Query(description="Repeatable field:op:value")
        ] = None,
        cursor: Annotated[str | None, Query(description="Opaque keyset cursor")] = None,
    ) -> QueryParams:
        # PageflowError raised here propagates to install_error_handler -> 400.
        sorts = parse_sort(sort)
        filters = parse_filters(filter)
        self._validate(sorts, filters)
        if not sorts:
            sorts = list(self.default_sort)
        resolved_limit = self.default_limit if limit is None else min(limit, self.max_limit)
        return QueryParams(
            limit=resolved_limit,
            offset=offset,
            sort=sorts,
            filters=filters,
            cursor=cursor,
        )

    def _validate(self, sorts: list[SortKey], filters: list[Filter]) -> None:
        for key in sorts:
            if key.field not in self.sortable:
                raise PageflowError(f"field {key.field!r} is not sortable", field=key.field)
        for flt in filters:
            if flt.field not in self.filterable:
                raise PageflowError(f"field {flt.field!r} is not filterable", field=flt.field)

    # -- column resolution -------------------------------------------------

    def _column(self, name: str) -> InstrumentedAttribute[Any]:
        return cast(InstrumentedAttribute[Any], getattr(self.model, name))

    # -- select building ---------------------------------------------------

    def apply_filters(self, stmt: Select[Any], params: QueryParams) -> Select[Any]:
        clauses = [
            build_clause(self._column(f.field), f.op, f.value, field=f.field)
            for f in params.filters
        ]
        return stmt.where(*clauses) if clauses else stmt

    def _order_keys(self, params: QueryParams) -> list[SortKey]:
        keys = list(params.sort)
        if all(k.field != self._pk_name for k in keys):
            keys.append(SortKey(self._pk_name, descending=False))
        return keys

    def apply_sort(self, stmt: Select[Any], params: QueryParams) -> Select[Any]:
        order_cols = []
        for key in self._order_keys(params):
            col = self._column(key.field)
            order_cols.append(col.desc() if key.descending else col.asc())
        return stmt.order_by(*order_cols)

    # -- execution ---------------------------------------------------------

    def paginate(
        self,
        session: Session,
        base: Select[Any],
        params: QueryParams,
    ) -> Page[Any]:
        """Execute ``base`` under ``params`` and return a :class:`Page`.

        Uses keyset (cursor) windowing when ``params.cursor`` is a valid
        token or when a client asks for the first cursor page (``cursor=""``);
        otherwise plain ``limit``/``offset``.
        """
        filtered = self.apply_filters(base, params)
        total = session.scalar(select(func.count()).select_from(filtered.subquery())) or 0

        if params.cursor is not None:
            items, next_cursor = self._keyset_page(session, filtered, params)
            return Page(
                items=items,
                total=total,
                limit=params.limit,
                offset=0,
                next_cursor=next_cursor,
            )

        stmt = self.apply_sort(filtered, params).limit(params.limit).offset(params.offset)
        items = list(session.scalars(stmt).all())
        return Page(items=items, total=total, limit=params.limit, offset=params.offset)

    # -- keyset / cursor windowing ----------------------------------------

    def _keyset_page(
        self,
        session: Session,
        filtered: Select[Any],
        params: QueryParams,
    ) -> tuple[list[Any], str | None]:
        keys = self._order_keys(params)
        stmt = self.apply_sort(filtered, params)
        after = self._decode_cursor(params.cursor, keys)
        if after is not None:
            stmt = stmt.where(self._after_clause(keys, after))
        # fetch one extra row to know whether a further page exists
        rows = list(session.scalars(stmt.limit(params.limit + 1)).all())
        has_more = len(rows) > params.limit
        page_rows = rows[: params.limit]
        next_cursor = (
            self._encode_cursor(page_rows[-1], keys) if has_more and page_rows else None
        )
        return page_rows, next_cursor

    def _after_clause(
        self, keys: list[SortKey], values: list[Any]
    ) -> ColumnElement[bool]:
        # Lexicographic "strictly after" across mixed asc/desc keys:
        #   OR_i ( k0==v0 AND ... AND k[i-1]==v[i-1] AND cmp(k_i, v_i) )
        ors: list[ColumnElement[bool]] = []
        for i, key in enumerate(keys):
            eq_prefix: list[ColumnElement[bool]] = [
                self._column(keys[j].field) == values[j] for j in range(i)
            ]
            col = self._column(key.field)
            strict = col < values[i] if key.descending else col > values[i]
            ors.append(and_(*eq_prefix, strict))
        return or_(*ors)

    def _encode_cursor(self, row: Any, keys: list[SortKey]) -> str:
        payload = [_jsonify(getattr(row, k.field)) for k in keys]
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode()

    def _decode_cursor(self, cursor: str | None, keys: list[SortKey]) -> list[Any] | None:
        if not cursor:
            return None
        try:
            raw = base64.urlsafe_b64decode(cursor.encode())
            payload = json.loads(raw)
            if not isinstance(payload, list) or len(payload) != len(keys):
                raise ValueError("cursor shape mismatch")
        except (ValueError, json.JSONDecodeError) as exc:
            raise PageflowError("invalid cursor", field="cursor") from exc
        out: list[Any] = []
        for key, token in zip(keys, payload, strict=True):
            col: InstrumentedAttribute[Any] | ColumnClause[Any] = self._column(key.field)
            py_type = _column_python_type(col)  # type: ignore[arg-type]
            out.append(_coerce_scalar(str(token), py_type, field=key.field))
        return out


def _jsonify(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def install_error_handler(app: FastAPI) -> None:
    """Register a handler turning :class:`PageflowError` into a 400 response.

    Call once on your app so malformed ``sort``/``filter``/``cursor`` values
    return ``{"detail": {"error": ..., "field": ...}}`` instead of a 500.
    """

    async def _handle(_: Request, exc: Exception) -> JSONResponse:
        err = exc if isinstance(exc, PageflowError) else PageflowError(str(exc))
        return JSONResponse(
            status_code=err.status_code,
            content={"detail": {"error": str(err), "field": err.field}},
        )

    app.add_exception_handler(PageflowError, _handle)
