"""API tests for the variant PDP backend.

Run with::

    cd app && python -m pytest backend/tests -q

Covers success, validation, idempotency and the stock race - the four areas the
brief asks for - plus the server-side trust boundary (price/stock can never come
from the client).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from backend.main import app, store

PRODUCT_ID = "aurora-merino-tee"
IN_STOCK_SKU = "aurora-merino-tee-white-m"  # stock 7
OUT_OF_STOCK_SKU = "aurora-merino-tee-black-m"  # stock 0
CHEAP_SKU = "aurora-merino-tee-black-s"  # stock 5, 2900 cents
TWO_UNIT_SKU = "aurora-merino-tee-sand-s"  # stock 2, 3300 cents


@pytest.fixture(autouse=True)
def _reset_store() -> Any:
    store.reset()
    yield
    store.reset()


@pytest.fixture
def client() -> Any:
    with TestClient(app) as test_client:
        yield test_client


def add_item(
    client: TestClient,
    sku_id: str = IN_STOCK_SKU,
    quantity: int = 1,
    key: str = "key-1",
    extra: Dict[str, Any] | None = None,
) -> Any:
    payload: Dict[str, Any] = {"skuId": sku_id, "quantity": quantity}
    if extra:
        payload.update(extra)
    headers = {"Idempotency-Key": key} if key is not None else {}
    return client.post("/api/cart/items", json=payload, headers=headers)


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
def test_get_product_returns_two_option_dimensions(client: TestClient) -> None:
    response = client.get(f"/api/products/{PRODUCT_ID}")
    assert response.status_code == HTTPStatus.OK

    body = response.json()
    assert body["id"] == PRODUCT_ID
    assert [option["id"] for option in body["options"]] == ["color", "size"]
    assert [value["id"] for value in body["options"][0]["values"]] == [
        "black",
        "white",
        "sand",
    ]
    assert all(value["swatch"] for value in body["options"][0]["values"])


def test_get_product_exposes_seven_skus_with_prices_and_images(
    client: TestClient,
) -> None:
    body = client.get(f"/api/products/{PRODUCT_ID}").json()
    skus = body["skus"]
    assert len(skus) == 7
    for sku in skus:
        assert sku["priceCents"] > 0
        assert sku["image"].startswith("data:image/svg+xml")
        assert set(sku["options"]) == {"color", "size"}
        assert sku["availableQuantity"] >= 0


def test_catalogue_contains_an_out_of_stock_sku_and_a_missing_combination(
    client: TestClient,
) -> None:
    body = client.get(f"/api/products/{PRODUCT_ID}").json()
    combinations = {
        (sku["options"]["color"], sku["options"]["size"]) for sku in body["skus"]
    }
    assert ("sand", "m") not in combinations  # unavailable combination
    assert ("black", "m") in combinations
    out_of_stock = [sku for sku in body["skus"] if sku["availableQuantity"] == 0]
    assert [sku["id"] for sku in out_of_stock] == [OUT_OF_STOCK_SKU]


def test_unknown_product_returns_structured_404(client: TestClient) -> None:
    response = client.get("/api/products/does-not-exist")
    assert response.status_code == HTTPStatus.NOT_FOUND
    error = response.json()["error"]
    assert error["code"] == "PRODUCT_NOT_FOUND"
    assert "does-not-exist" in error["message"]


def test_unknown_route_uses_the_same_error_envelope(client: TestClient) -> None:
    response = client.get("/api/definitely-not-a-route")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_add_to_cart_success(client: TestClient) -> None:
    response = add_item(client, CHEAP_SKU, 2)
    assert response.status_code == HTTPStatus.CREATED

    body = response.json()
    assert body["sku"]["id"] == CHEAP_SKU
    assert body["sku"]["availableQuantity"] == 3  # 5 - 2
    assert body["cart"]["totalQuantity"] == 2
    assert body["cart"]["totalPriceCents"] == 5800
    assert body["cart"]["items"][0]["unitPriceCents"] == 2900
    assert body["cart"]["items"][0]["lineTotalCents"] == 5800


def test_cart_is_empty_before_any_add(client: TestClient) -> None:
    assert client.get("/api/cart").json() == {
        "items": [],
        "totalQuantity": 0,
        "totalPriceCents": 0,
    }


def test_cart_accumulates_multiple_lines_and_totals(client: TestClient) -> None:
    add_item(client, CHEAP_SKU, 1, key="a")
    add_item(client, CHEAP_SKU, 1, key="b")
    add_item(client, IN_STOCK_SKU, 2, key="c")

    cart = client.get("/api/cart").json()
    assert cart["totalQuantity"] == 4
    assert cart["totalPriceCents"] == 2900 * 2 + 2900 * 2
    assert [line["skuId"] for line in cart["items"]] == sorted(
        [CHEAP_SKU, IN_STOCK_SKU]
    )
    assert all(line["name"] and line["image"] for line in cart["items"])


def test_product_stock_reflects_reserved_cart_units(client: TestClient) -> None:
    add_item(client, TWO_UNIT_SKU, 2)
    skus = client.get(f"/api/products/{PRODUCT_ID}").json()["skus"]
    remaining = {sku["id"]: sku["availableQuantity"] for sku in skus}
    assert remaining[TWO_UNIT_SKU] == 0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("quantity", [0, -1, 100, 1.5, "two", None])
def test_invalid_quantity_is_rejected(client: TestClient, quantity: Any) -> None:
    response = add_item(client, IN_STOCK_SKU, quantity)  # type: ignore[arg-type]
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert any("quantity" in field["field"] for field in error["details"]["errors"])


def test_missing_sku_id_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/cart/items",
        json={"quantity": 1},
        headers={"Idempotency-Key": "k"},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_client_supplied_price_and_stock_are_rejected_not_ignored(
    client: TestClient,
) -> None:
    # A client trying to dictate the price must fail loudly, not be silently
    # ignored, otherwise a future refactor could start trusting the field.
    response = add_item(client, CHEAP_SKU, 1, extra={"priceCents": 1, "availableQuantity": 999})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get("/api/cart").json()["totalQuantity"] == 0


def test_unknown_sku_is_rejected(client: TestClient) -> None:
    response = add_item(client, "not-a-sku", 1)
    assert response.status_code == HTTPStatus.NOT_FOUND
    error = response.json()["error"]
    assert error["code"] == "SKU_NOT_FOUND"
    assert "not-a-sku" in error["message"]
    # `details` is omitted entirely when there is nothing extra to say.
    assert "details" not in error


def test_out_of_stock_sku_is_rejected_with_details(client: TestClient) -> None:
    response = add_item(client, OUT_OF_STOCK_SKU, 1)
    assert response.status_code == HTTPStatus.CONFLICT
    error = response.json()["error"]
    assert error["code"] == "INSUFFICIENT_STOCK"
    assert error["details"] == {
        "skuId": OUT_OF_STOCK_SKU,
        "requested": 1,
        "available": 0,
    }


def test_requesting_more_than_available_is_rejected(client: TestClient) -> None:
    response = add_item(client, TWO_UNIT_SKU, 3)
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["error"]["details"]["available"] == 2
    assert client.get("/api/cart").json()["totalQuantity"] == 0


def test_missing_idempotency_key_header_is_rejected(client: TestClient) -> None:
    response = add_item(client, IN_STOCK_SKU, 1, key=None)  # type: ignore[arg-type]
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["error"]["code"] == "MISSING_IDEMPOTENCY_KEY"


def test_blank_idempotency_key_header_is_rejected(client: TestClient) -> None:
    response = add_item(client, IN_STOCK_SKU, 1, key="   ")
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["error"]["code"] == "MISSING_IDEMPOTENCY_KEY"


def test_malformed_json_body_uses_the_error_envelope(client: TestClient) -> None:
    response = client.post(
        "/api/cart/items",
        content=b"{not json",
        headers={"Content-Type": "application/json", "Idempotency-Key": "k"},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
def test_repeating_the_same_key_does_not_add_twice(client: TestClient) -> None:
    first = add_item(client, CHEAP_SKU, 2, key="dupe")
    second = add_item(client, CHEAP_SKU, 2, key="dupe")

    assert first.status_code == HTTPStatus.CREATED
    assert second.status_code == HTTPStatus.CREATED
    assert first.json() == second.json()  # byte-for-byte replay

    cart = client.get("/api/cart").json()
    assert cart["totalQuantity"] == 2
    assert cart["items"][0]["quantity"] == 2


def test_repeated_key_is_stable_under_retry_after_a_lost_response(
    client: TestClient,
) -> None:
    # Simulates a client that never saw the first response and retries.
    for _ in range(5):
        response = add_item(client, CHEAP_SKU, 1, key="retry-me")
        assert response.status_code == HTTPStatus.CREATED
    assert client.get("/api/cart").json()["totalQuantity"] == 1


def test_same_key_with_a_different_payload_is_a_conflict(client: TestClient) -> None:
    add_item(client, CHEAP_SKU, 1, key="shared")
    response = add_item(client, CHEAP_SKU, 2, key="shared")
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSE"
    assert client.get("/api/cart").json()["totalQuantity"] == 1


def test_same_key_for_a_different_sku_is_a_conflict(client: TestClient) -> None:
    add_item(client, CHEAP_SKU, 1, key="shared")
    response = add_item(client, IN_STOCK_SKU, 1, key="shared")
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSE"


def test_rejected_attempt_is_replayed_for_the_same_key(client: TestClient) -> None:
    first = add_item(client, OUT_OF_STOCK_SKU, 1, key="oom")
    second = add_item(client, OUT_OF_STOCK_SKU, 1, key="oom")
    assert first.status_code == HTTPStatus.CONFLICT
    assert second.status_code == HTTPStatus.CONFLICT
    assert first.json() == second.json()


def test_different_keys_are_independent(client: TestClient) -> None:
    add_item(client, CHEAP_SKU, 1, key="one")
    add_item(client, CHEAP_SKU, 1, key="two")
    assert client.get("/api/cart").json()["totalQuantity"] == 2


# ---------------------------------------------------------------------------
# Stock race / overselling
# ---------------------------------------------------------------------------
def test_two_concurrent_requests_cannot_oversell_the_last_units(
    client: TestClient,
) -> None:
    """`TWO_UNIT_SKU` has 2 units; two racing requests ask for 2 each."""
    barrier = threading.Barrier(2)
    statuses: List[int] = []
    lock = threading.Lock()

    def attempt(key: str) -> None:
        barrier.wait(timeout=10)
        response = client.post(
            "/api/cart/items",
            json={"skuId": TWO_UNIT_SKU, "quantity": 2},
            headers={"Idempotency-Key": key},
        )
        with lock:
            statuses.append(response.status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(attempt, ["race-a", "race-b"]))

    assert sorted(statuses) == [
        HTTPStatus.CREATED,
        HTTPStatus.CONFLICT,
    ], statuses

    cart = client.get("/api/cart").json()
    assert cart["totalQuantity"] == 2  # never more than the stock on hand


def test_concurrent_single_unit_adds_never_exceed_stock() -> None:
    """Store level race: 8 threads, 5 units, one unit each."""
    sku = CHEAP_SKU  # stock 5
    barrier = threading.Barrier(8)
    outcomes: List[int] = []
    lock = threading.Lock()

    def attempt(index: int) -> None:
        barrier.wait(timeout=10)
        try:
            status, _ = store.add_to_cart(sku, 1, f"store-race-{index}")
        except Exception as problem:  # ApiProblem
            status = getattr(problem, "status", 500)
        with lock:
            outcomes.append(status)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(attempt, range(8)))

    assert outcomes.count(201) == 5
    assert outcomes.count(409) == 3
    assert store.cart_snapshot()["totalQuantity"] == 5
    assert store.available_quantity(sku) == 0
