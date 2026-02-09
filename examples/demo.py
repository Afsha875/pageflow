"""Self-contained pageflow demo. Run: uv run python examples/demo.py

Everything is in-memory SQLite; no network, no external services. The output
of this script is what the README quotes verbatim.
"""

from __future__ import annotations

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from pageflow import Filter, Paginator, QueryParams, SortKey


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40))
    price: Mapped[int] = mapped_column()  # cents
    in_stock: Mapped[bool] = mapped_column(default=True)


SEED = [
    ("Cable", 799, True),
    ("Mouse", 1999, True),
    ("Keyboard", 4999, True),
    ("Monitor", 18999, False),
    ("Webcam", 6999, True),
    ("Dock", 12999, True),
    ("Stand", 2999, False),
    ("Hub", 3499, True),
    ("Mat", 1299, True),
    ("Lamp", 5499, True),
]

catalog: Paginator[Product] = Paginator(
    Product,
    sortable={"id", "name", "price"},
    filterable={"price", "in_stock", "name"},
    default_limit=3,
    default_sort=[SortKey("id")],
)


def main() -> None:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(Product(name=n, price=p, in_stock=s) for n, p, s in SEED)
        db.commit()

        # 1) offset page
        page = catalog.paginate(db, select(Product), QueryParams(limit=3, offset=0))
        print("offset page 1:", [p.name for p in page.items])
        print(f"  total={page.total} limit={page.limit} pages={page.page_count} "
              f"has_next={page.has_next}")

        # 2) filter + sort: in-stock items under $50, cheapest first
        params = QueryParams(
            limit=10,
            offset=0,
            sort=[SortKey("price")],
            filters=[Filter("in_stock", "eq", "true"), Filter("price", "lt", "5000")],
        )
        cheap = catalog.paginate(db, select(Product), params)
        print("in-stock < $50, cheapest first:",
              [(p.name, p.price) for p in cheap.items])

        # 3) keyset cursor walk
        seen: list[str] = []
        cursor: str | None = ""
        hops = 0
        while True:
            pg = catalog.paginate(
                db,
                select(Product),
                QueryParams(limit=4, offset=0, sort=[SortKey("name")], cursor=cursor),
            )
            hops += 1
            seen.extend(p.name for p in pg.items)
            if pg.next_cursor is None:
                break
            cursor = pg.next_cursor
        print(f"cursor walk visited {len(seen)} rows in {hops} hops:", seen)


if __name__ == "__main__":
    main()
