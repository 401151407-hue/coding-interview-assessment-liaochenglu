"""Structured error handling.

Every failure leaves the API through :class:`ApiProblem` (or one of the exception
handlers registered in ``main.py``) so clients always receive the same envelope::

    {"error": {"code": "INSUFFICIENT_STOCK",
               "message": "Only 1 unit of ... remains.",
               "details": {"skuId": "...", "requested": 2, "available": 1}}}
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class ApiProblem(Exception):
    """A client-visible failure with a stable machine readable ``code``."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details: Dict[str, Any] = details or {}

    def body(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return {"error": payload}


def error_body(
    code: str, message: str, details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return {"error": payload}


# -- reusable problems -----------------------------------------------------
def product_not_found(product_id: str) -> ApiProblem:
    return ApiProblem(
        404, "PRODUCT_NOT_FOUND", f"Unknown product '{product_id}'."
    )


def sku_not_found(sku_id: str) -> ApiProblem:
    return ApiProblem(404, "SKU_NOT_FOUND", f"Unknown SKU '{sku_id}'.")


def missing_idempotency_key() -> ApiProblem:
    return ApiProblem(
        400,
        "MISSING_IDEMPOTENCY_KEY",
        "The 'Idempotency-Key' header is required for this endpoint.",
    )


def idempotency_key_reuse(key: str) -> ApiProblem:
    return ApiProblem(
        409,
        "IDEMPOTENCY_KEY_REUSE",
        "This 'Idempotency-Key' was already used with a different payload.",
        {"idempotencyKey": key},
    )


def insufficient_stock(sku_id: str, requested: int, available: int) -> ApiProblem:
    message = (
        f"Only {available} unit(s) of '{sku_id}' remain, but {requested} were "
        "requested."
    )
    return ApiProblem(
        409,
        "INSUFFICIENT_STOCK",
        message,
        {"skuId": sku_id, "requested": requested, "available": available},
    )
