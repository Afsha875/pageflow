"""Shared fixtures: a tiny in-memory SQLite model, seed data, and demo app."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from pageflow import Page, Paginator, QueryParams, SortKey, install_error_handler


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    age: Mapped[int] = mapped_column()
    active: Mapped[bool] = mapped_column(default=True)
    joined: Mapped[date] = mapped_column()


# Deterministic seed: 12 users with predictable names/ages so assertions are exact.
SEED: list[tuple[str, int, bool, date]] = [
    ("alice", 30, True, date(2020, 1, 1)),
    ("bob", 25, True, date(2020, 2, 1)),
    ("carol", 41, False, date(2020, 3, 1)),
    ("dave", 25, True, date(2020, 4, 1)),
    ("erin", 38, False, date(2020, 5, 1)),
    ("frank", 22, True, date(2020, 6, 1)),
    ("grace", 55, True, date(2020, 7, 1)),
    ("heidi", 30, False, date(2020, 8, 1)),
    ("ivan", 29, True, date(2020, 9, 1)),
    ("judy", 47, True, date(2020, 10, 1)),
    ("mallory", 33, False, date(2020, 11, 1)),
    ("niaj", 25, True, date(2020, 12, 1)),
]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    age: int
    active: bool


user_paginator: Paginator[User] = Paginator(
    User,
    sortable={"id", "name", "age", "joined"},
    filterable={"id", "name", "age", "active", "joined"},
    default_limit=5,
    max_limit=50,
    default_sort=[SortKey("id", descending=False)],
)


@pytest.fixture
def engine() -> Iterator[Engine]:
    # StaticPool keeps ONE shared in-memory connection, so the seed rows are
    # visible to the TestClient's worker thread (which uses a fresh session).
    eng = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add_all(
            User(name=n, age=a, active=act, joined=j) for n, a, act, j in SEED
        )
        s.commit()
    yield eng


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    maker = sessionmaker(bind=engine, class_=Session)
    with maker() as s:
        yield s


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    app = FastAPI()
    install_error_handler(app)
    maker = sessionmaker(bind=engine, class_=Session)

    def get_db() -> Iterator[Session]:
        with maker() as s:
            yield s

    @app.get("/users", response_model=Page[UserOut])
    def list_users(
        params: QueryParams = Depends(user_paginator),
        db: Session = Depends(get_db),
    ) -> Page[User]:
        return user_paginator.paginate(db, select(User), params)

    with TestClient(app) as c:
        yield c
