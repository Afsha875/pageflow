# pageflow

**Drop-in pagination, filtering and sorting for FastAPI + SQLAlchemy - one dependency, a typed Page[T] out.**

## The problem

Every FastAPI service reinvents list endpoints: parse "limit"/"offset", hand-roll
"sort=name:asc", translate "?age__gte=18" into SQLAlchemy, whitelist which columns
are safe to touch, and shape a consistent response envelope. It is copy-pasted,
subtly different in every service, and usually missing keyset (cursor) pagination
because it is fiddly to get right.

pageflow is that layer, done once:

- A configurable **FastAPI dependency** that parses "limit", "offset", "sort",
  repeatable "filter=field:op:value", and an opaque "cursor" - and rejects any
  column you did not explicitly whitelist (400, not 500).
- A **query applier** that turns those params into "WHERE" / "ORDER BY" / "LIMIT"
  on any "select()", coercing string values to each column's real Python type
  ("int", "bool", "date", "datetime").
- Both **offset** and **keyset (cursor)** pagination, the latter with correct
  lexicographic "strictly after" logic across mixed "asc"/"desc" keys plus an
  auto-appended primary-key tiebreaker.
- A typed **Page[T]** envelope ("items", "total", "limit", "offset",
  "next_cursor", plus "has_next" / "has_prev" / "page_count").

Library only - no models, no migrations, no config. Import it and go.

## Quickstart

```bash
git clone <this-repo> && cd pageflow
uv sync
uv run pytest -q          # 27 passing tests
uv run python examples/demo.py
```

Wiring it into an app is three lines around your existing route:

```python
from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session
from pageflow import Page, Paginator, QueryParams, install_error_handler

app = FastAPI()
install_error_handler(app)  # PageflowError -> 400 JSON

users = Paginator(
    User,
    sortable={"id", "name", "age"},
    filterable={"age", "name", "active"},
    default_limit=20,
    max_limit=100,
)

@app.get("/users", response_model=Page[UserOut])
def list_users(
    params: QueryParams = Depends(users),
    db: Session = Depends(get_db),
) -> Page[User]:
    return users.paginate(db, select(User), params)
```

Now these all work, safely:

```
GET /users?limit=10&offset=20
GET /users?sort=age:desc,name:asc
GET /users?filter=age:gte:18&filter=active:eq:true
GET /users?sort=name:asc&cursor=WyJhbGljZSIsMV0    # keyset page
```

## Filter operators

filter=field:op:value, repeatable. Values are coerced to the column type.

| op | meaning | example |
|----|---------|---------|
| eq / ne | equal / not equal | active:eq:true |
| lt, lte, gt, gte | comparisons | age:gte:18 |
| like / ilike | SQL pattern | name:like:a% |
| in / nin | (not) in comma list | age:in:25,30 |
| isnull | NULL check | deleted_at:isnull:true |

## Real output

"uv run python examples/demo.py" (a 10-row in-memory catalog) prints:

```
offset page 1: ['Cable', 'Mouse', 'Keyboard']
  total=10 limit=3 pages=4 has_next=True
in-stock < $50, cheapest first: [('Cable', 799), ('Mat', 1299), ('Mouse', 1999), ('Hub', 3499), ('Keyboard', 4999)]
cursor walk visited 10 rows in 3 hops: ['Cable', 'Dock', 'Hub', 'Keyboard', 'Lamp', 'Mat', 'Monitor', 'Mouse', 'Stand', 'Webcam']
```

Note the cursor walk visits **all 10 rows exactly once across 3 hops** with no
duplicates or gaps - the property the "tests/test_cursor.py" suite pins down.

## Design notes

- **Safety first.** Columns are whitelisted per Paginator; an untrusted
  "?sort=password:asc" or "?filter=ssn:eq:x" returns a 400 naming the bad field,
  never a query. Value coercion failures ("age:gte:notanumber") are 400s too.
- **Cursor correctness.** Keyset pagination appends the primary key as a final
  tiebreaker so ties never drop or repeat rows, and the "after" predicate is a
  proper "OR"-of-"AND"s that honours each key's direction - verified against the
  offset ordering in tests.
- **Typed end to end.** strict mypy, PEP 695 generics (Page[T],
  Paginator[ModelT]), and Page[UserOut] as a real response_model.

## What I'd build next

- **Async engine support** (AsyncSession) alongside the sync path.
- **fields= projection** to select a subset of columns / relationships.
- **Full-text and JSON-path operators** for Postgres (@@, ->>).
- **Link headers** (rel="next"/"prev") generated from next_cursor.
- A tiny **OpenAPI example generator** so the docs page shows real filter syntax.

## Development

```bash
uv run ruff check .        # lint (E,F,I,UP,B,SIM,RUF, line-length 100)
uv run mypy src tests      # strict type check
uv run pytest -q           # tests
```

## Maintainer

Afsha Fathima
Python Backend Developer
Email: fathimaafsha08@gmail.com
LinkedIn: https://www.linkedin.com/in/afsha-fathima-lnu-a29996298/

Afsha is a Python Backend Developer with over 4 years of experience building backend applications, REST APIs, and business-critical software. She specializes in FastAPI, SQLAlchemy, and database integrations, focusing on creating maintainable and high-performance solutions. She currently maintains this project to provide a standardized approach to pagination and filtering in the FastAPI ecosystem.