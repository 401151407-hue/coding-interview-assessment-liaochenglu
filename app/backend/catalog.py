"""Seed catalogue for the variant PDP.

The domain model is deliberately explicit:

* one product with **two** option dimensions (colour, size),
* **seven** SKUs, including an *unavailable combination* (sand / M has no SKU at
  all) and an *out-of-stock* SKU (black / M has stock 0),
* each SKU carries its own id, price, stock, image and option values.

Images are inline SVG data URIs so the app renders identically offline and no
external asset host is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple
from urllib.parse import quote

CURRENCY = "USD"


@dataclass(frozen=True)
class OptionValue:
    id: str
    label: str
    swatch: str


@dataclass(frozen=True)
class ProductOption:
    id: str
    label: str
    values: Tuple[OptionValue, ...]


@dataclass(frozen=True)
class Sku:
    id: str
    name: str
    options: Dict[str, str]
    price_cents: int
    stock: int
    image: str


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    description: str
    currency: str
    options: Tuple[ProductOption, ...]
    skus: Tuple[Sku, ...]


def _image(label: str, colour: str, size: str) -> str:
    """A small inline SVG used as the SKU image."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="720" '
        'viewBox="0 0 720 720" role="img">'
        f'<rect width="720" height="720" fill="{colour}"/>'
        '<path d="M250 190 L470 190 L540 320 L472 348 L472 566 L248 566 L248 348 '
        'L180 320 Z" fill="rgba(255,255,255,0.35)" '
        'stroke="rgba(15,23,42,0.35)" stroke-width="8" stroke-linejoin="round"/>'
        '<text x="360" y="120" font-family="Segoe UI,Helvetica,Arial" font-size="34" '
        f'text-anchor="middle" fill="#0f172a">{size}</text>'
        '<text x="360" y="660" font-family="Segoe UI,Helvetica,Arial" font-size="34" '
        f'font-weight="600" text-anchor="middle" fill="#0f172a">{label}</text>'
        "</svg>"
    )
    return "data:image/svg+xml;charset=utf-8," + quote(svg, safe="")


_COLOUR_BLACK = "#1f2937"
_COLOUR_WHITE = "#e5e7eb"
_COLOUR_SAND = "#d9c4a3"

_PRODUCT = Product(
    id="aurora-merino-tee",
    name="Aurora Merino Tee",
    description=(
        "A lightweight 180 gsm merino tee with a straight hem and a slightly "
        "relaxed shoulder. Naturally temperature regulating and odour "
        "resistant, made in a small mill in Portugal."
    ),
    currency=CURRENCY,
    options=(
        ProductOption(
            id="color",
            label="Colour",
            values=(
                OptionValue(id="black", label="Black", swatch=_COLOUR_BLACK),
                OptionValue(id="white", label="White", swatch=_COLOUR_WHITE),
                OptionValue(id="sand", label="Sand", swatch=_COLOUR_SAND),
            ),
        ),
        ProductOption(
            id="size",
            label="Size",
            values=(
                OptionValue(id="s", label="S", swatch="#94a3b8"),
                OptionValue(id="m", label="M", swatch="#94a3b8"),
                OptionValue(id="l", label="L", swatch="#94a3b8"),
            ),
        ),
    ),
    skus=(
        Sku(
            id="aurora-merino-tee-black-s",
            name="Aurora Merino Tee - Black / S",
            options={"color": "black", "size": "s"},
            price_cents=2900,
            stock=5,
            image=_image("Black / S", _COLOUR_BLACK, "S"),
        ),
        # Out-of-stock SKU: the combination exists but cannot be bought today.
        Sku(
            id="aurora-merino-tee-black-m",
            name="Aurora Merino Tee - Black / M",
            options={"color": "black", "size": "m"},
            price_cents=2900,
            stock=0,
            image=_image("Black / M", _COLOUR_BLACK, "M"),
        ),
        Sku(
            id="aurora-merino-tee-black-l",
            name="Aurora Merino Tee - Black / L",
            options={"color": "black", "size": "l"},
            price_cents=3100,
            stock=3,
            image=_image("Black / L", _COLOUR_BLACK, "L"),
        ),
        Sku(
            id="aurora-merino-tee-white-s",
            name="Aurora Merino Tee - White / S",
            options={"color": "white", "size": "s"},
            price_cents=2900,
            stock=4,
            image=_image("White / S", _COLOUR_WHITE, "S"),
        ),
        Sku(
            id="aurora-merino-tee-white-m",
            name="Aurora Merino Tee - White / M",
            options={"color": "white", "size": "m"},
            price_cents=2900,
            stock=7,
            image=_image("White / M", _COLOUR_WHITE, "M"),
        ),
        Sku(
            id="aurora-merino-tee-sand-s",
            name="Aurora Merino Tee - Sand / S",
            options={"color": "sand", "size": "s"},
            price_cents=3300,
            stock=2,
            image=_image("Sand / S", _COLOUR_SAND, "S"),
        ),
        # NOTE: sand / M deliberately has no SKU at all -> unavailable combination.
        Sku(
            id="aurora-merino-tee-sand-l",
            name="Aurora Merino Tee - Sand / L",
            options={"color": "sand", "size": "l"},
            price_cents=3300,
            stock=6,
            image=_image("Sand / L", _COLOUR_SAND, "L"),
        ),
    ),
)

PRODUCTS: Tuple[Product, ...] = (_PRODUCT,)
