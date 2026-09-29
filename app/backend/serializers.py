"""Domain -> JSON serialisation.

Kept separate from the routes so the wire format can be tested without spinning up
HTTP, and so the frontend's TypeScript types have exactly one source of truth.
"""

from __future__ import annotations

from typing import Any, Dict

from backend.catalog import Product
from backend.store import Store


def serialize_product(product: Product, store: Store) -> Dict[str, Any]:
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "currency": product.currency,
        "options": [
            {
                "id": option.id,
                "label": option.label,
                "values": [
                    {"id": value.id, "label": value.label, "swatch": value.swatch}
                    for value in option.values
                ],
            }
            for option in product.options
        ],
        "skus": [
            {
                "id": sku.id,
                "name": sku.name,
                "options": dict(sku.options),
                "priceCents": sku.price_cents,
                "currency": product.currency,
                "availableQuantity": store.available_quantity(sku.id),
                "image": sku.image,
            }
            for sku in product.skus
        ],
    }
