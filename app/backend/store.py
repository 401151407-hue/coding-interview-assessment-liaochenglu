"""In-memory data store.

Storage is intentionally in-memory (the brief allows in-memory or SQLite) but the
*behaviour* is modelled as if it were a database:

* a single ``threading.Lock`` serialises the read-modify-write of the cart, so two
  concurrent requests for the final unit cannot both succeed (no overselling);
* the client is never trusted for price or stock - both are read from the seed
  catalogue inside the critical section;
* every mutating request requires an idempotency key, and the *outcome* of the
  first attempt is replayed verbatim for a repeated key with the same payload.

``threading`` rather than ``asyncio`` is used on purpose: the endpoints are plain
``def`` functions, so FastAPI runs them in a worker thread pool and two requests
really do execute in parallel. That makes the lock load-bearing rather than
decorative, and lets the test suite reproduce the race with real OS threads.

A production system would replace the lock with a conditional
``UPDATE ... WHERE available >= :qty`` and the idempotency dict with a unique
indexed table; the external contract would not change.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from backend.catalog import Product, Sku
from backend.errors import (
    ApiProblem,
    idempotency_key_reuse,
    insufficient_stock,
    sku_not_found,
)

#: Largest quantity accepted for a single cart line.
MAX_LINE_QUANTITY = 99


@dataclass(frozen=True)
class IdempotencyRecord:
    """The memoised outcome of the first request that used a key."""

    fingerprint: str
    status: int
    body: Dict[str, Any]


class Store:
    def __init__(self, products: Sequence[Product]) -> None:
        self._products: Dict[str, Product] = {}
        self._skus: Dict[str, Sku] = {}
        self._product_of_sku: Dict[str, str] = {}
        for product in products:
            self._products[product.id] = product
            for sku in product.skus:
                if sku.id in self._skus:
                    raise ValueError(f"duplicate SKU id {sku.id!r}")
                self._skus[sku.id] = sku
                self._product_of_sku[sku.id] = product.id

        self._cart: Dict[str, int] = {}
        self._idempotency: Dict[str, IdempotencyRecord] = {}
        self._lock = threading.Lock()

    # -- test / operational helpers ---------------------------------------
    def reset(self) -> None:
        """Restore the seed state (used by tests and by a ``--reset`` admin call)."""
        with self._lock:
            self._cart.clear()
            self._idempotency.clear()

    # -- lookups -----------------------------------------------------------
    def get_product(self, product_id: str) -> Optional[Product]:
        return self._products.get(product_id)

    def get_sku(self, sku_id: str) -> Optional[Sku]:
        return self._skus.get(sku_id)

    def available_quantity(self, sku_id: str) -> int:
        """Stock not already held by the cart. Safe to call while locked."""
        sku = self._skus[sku_id]
        return max(sku.stock - self._cart.get(sku_id, 0), 0)

    # -- cart --------------------------------------------------------------
    def cart_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot()

    def _snapshot(self) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        total_quantity = 0
        total_price_cents = 0
        for sku_id, quantity in sorted(self._cart.items()):
            if quantity <= 0:
                continue
            sku = self._skus[sku_id]
            line_total = sku.price_cents * quantity
            items.append(
                {
                    "skuId": sku.id,
                    "productId": self._product_of_sku[sku.id],
                    "name": sku.name,
                    "options": dict(sku.options),
                    "image": sku.image,
                    "unitPriceCents": sku.price_cents,
                    "quantity": quantity,
                    "lineTotalCents": line_total,
                }
            )
            total_quantity += quantity
            total_price_cents += line_total
        return {
            "items": items,
            "totalQuantity": total_quantity,
            "totalPriceCents": total_price_cents,
        }

    def add_to_cart(
        self, sku_id: str, quantity: int, idempotency_key: str
    ) -> tuple[int, Dict[str, Any]]:
        """Add ``quantity`` of ``sku_id`` and return ``(status, body)``.

        Raises :class:`ApiProblem` for any rejected request. The lock is held for
        the whole check-then-write, which is what prevents overselling.
        """
        fingerprint = f"{sku_id}|{quantity}"

        with self._lock:
            record = self._idempotency.get(idempotency_key)
            if record is not None:
                if record.fingerprint != fingerprint:
                    raise idempotency_key_reuse(idempotency_key)
                # Replay the original outcome: the cart is not touched again.
                return record.status, record.body

            try:
                body = self._apply_add(sku_id, quantity)
            except ApiProblem as problem:
                # Deterministic failures are memoised too, so a retry of the same
                # key sees exactly the same answer instead of a different one.
                self._idempotency[idempotency_key] = IdempotencyRecord(
                    fingerprint, problem.status, problem.body()
                )
                raise

            self._idempotency[idempotency_key] = IdempotencyRecord(
                fingerprint, 201, body
            )
            return 201, body

    def _apply_add(self, sku_id: str, quantity: int) -> Dict[str, Any]:
        sku = self._skus.get(sku_id)
        if sku is None:
            raise sku_not_found(sku_id)

        available = self.available_quantity(sku_id)
        if quantity > available:
            raise insufficient_stock(sku_id, quantity, available)

        self._cart[sku_id] = self._cart.get(sku_id, 0) + quantity
        return {
            "cart": self._snapshot(),
            "sku": {
                "id": sku.id,
                "productId": self._product_of_sku[sku.id],
                "availableQuantity": self.available_quantity(sku_id),
            },
        }
