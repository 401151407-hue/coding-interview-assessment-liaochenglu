"""FastAPI application for the variant PDP.

Endpoints
---------
``GET  /api/products/{id}``  product, option dimensions and SKU data
``POST /api/cart/items``     add a SKU + quantity (requires Idempotency-Key)
``GET  /api/cart``           current cart and totals
``GET  /api/health``         liveness probe

Run locally (from the ``app`` directory)::

    python -m uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.catalog import PRODUCTS
from backend.errors import ApiProblem, error_body, missing_idempotency_key, product_not_found
from backend.serializers import serialize_product
from backend.store import MAX_LINE_QUANTITY, Store

logger = logging.getLogger("pdp.api")

app = FastAPI(
    title="Variant PDP API",
    version="1.0.0",
    description=(
        "Product detail page API for a single configurable product. All price "
        "and stock decisions are made server-side; the client is never trusted "
        "for either."
    ),
)

# The Vite dev server runs on a different origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key"],
    max_age=600,
)

store = Store(PRODUCTS)

_HTTP_ERROR_CODES = {
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    415: "UNSUPPORTED_MEDIA_TYPE",
    500: "INTERNAL_ERROR",
}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class AddToCartRequest(BaseModel):
    """Body of ``POST /api/cart/items``.

    ``extra="forbid"`` turns typos and smuggled fields (for example an injected
    ``priceCents``) into a 422 instead of silently ignoring them.
    """

    model_config = ConfigDict(extra="forbid")

    sku_id: str = Field(alias="skuId", min_length=1, max_length=128)
    quantity: int = Field(ge=1, le=MAX_LINE_QUANTITY)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health", tags=["ops"])
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/products/{product_id}", tags=["catalogue"])
def get_product(product_id: str) -> Dict[str, Any]:
    product = store.get_product(product_id)
    if product is None:
        raise product_not_found(product_id)
    return serialize_product(product, store)


@app.get("/api/cart", tags=["cart"])
def get_cart() -> Dict[str, Any]:
    return store.cart_snapshot()


@app.post(
    "/api/cart/items",
    tags=["cart"],
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Item added (or the original result replayed)."},
        400: {"description": "Missing Idempotency-Key header."},
        404: {"description": "Unknown SKU."},
        409: {"description": "Insufficient stock or idempotency key reuse."},
        422: {"description": "Payload validation failed."},
    },
)
def add_cart_item(
    payload: AddToCartRequest,
    idempotency_key: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=200,
        description="Client generated key. Repeating a key must not add twice.",
    ),
) -> JSONResponse:
    if idempotency_key is None or not idempotency_key.strip():
        raise missing_idempotency_key()

    status_code, body = store.add_to_cart(
        payload.sku_id, payload.quantity, idempotency_key.strip()
    )
    # The store decides the status so an idempotent replay returns the original
    # status code and body byte for byte.
    return JSONResponse(status_code=status_code, content=body)


# ---------------------------------------------------------------------------
# Exception handlers: every failure uses the same structured envelope
# ---------------------------------------------------------------------------
@app.exception_handler(ApiProblem)
async def handle_api_problem(_request: Request, exc: ApiProblem) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=exc.body())


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    details: List[Dict[str, Any]] = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "message": error.get("msg", "invalid value"),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_body(
            "VALIDATION_ERROR", "The request payload failed validation.", {"errors": details}
        ),
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code = _HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, str(exc.detail)),
    )


@app.exception_handler(Exception)
async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
    # Log the detail server-side, return none of it to the client.
    logger.exception("unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content=error_body(
            "INTERNAL_ERROR", "An unexpected error occurred. Please try again."
        ),
    )
