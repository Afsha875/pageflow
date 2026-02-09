"""End-to-end tests through FastAPI's TestClient on the demo app."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_default_page(client: TestClient) -> None:
    r = client.get("/users")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 12
    assert body["limit"] == 5
    assert body["offset"] == 0
    assert len(body["items"]) == 5
    assert body["items"][0]["name"] == "alice"


def test_sort_and_filter_query(client: TestClient) -> None:
    r = client.get("/users", params={"sort": "age:desc", "filter": "active:eq:true"})
    assert r.status_code == 200
    body = r.json()
    ages = [u["age"] for u in body["items"]]
    assert ages == sorted(ages, reverse=True)
    assert all(u["active"] for u in body["items"])


def test_multiple_filters_repeated_param(client: TestClient) -> None:
    r = client.get("/users?filter=age:gte:25&filter=age:lte:30&limit=50")
    body = r.json()
    assert all(25 <= u["age"] <= 30 for u in body["items"])
    assert body["total"] == len(body["items"])


def test_max_limit_is_clamped(client: TestClient) -> None:
    r = client.get("/users", params={"limit": 9999})
    body = r.json()
    assert body["limit"] == 50  # clamped to max_limit


def test_unsortable_field_is_400(client: TestClient) -> None:
    r = client.get("/users", params={"sort": "password:asc"})
    assert r.status_code == 400
    assert r.json()["detail"]["field"] == "password"


def test_unfilterable_field_is_400(client: TestClient) -> None:
    r = client.get("/users", params={"filter": "password:eq:x"})
    assert r.status_code == 400


def test_bad_value_coercion_is_400(client: TestClient) -> None:
    r = client.get("/users", params={"filter": "age:gte:notanumber"})
    assert r.status_code == 400
    assert r.json()["detail"]["field"] == "age"


def test_cursor_roundtrip_via_http(client: TestClient) -> None:
    seen: list[str] = []
    params = {"sort": "id:asc", "limit": "4", "cursor": ""}
    while True:
        body = client.get("/users", params=params).json()
        seen.extend(u["name"] for u in body["items"])
        if body["next_cursor"] is None:
            break
        params["cursor"] = body["next_cursor"]
    assert len(seen) == 12
    assert len(set(seen)) == 12  # every user exactly once
    assert seen[0] == "alice"  # id:asc order preserved across cursor hops
