/**
 * A scriptable in-memory implementation of `PdpApi`.
 *
 * Tests inject this through `<ApiProvider>` instead of stubbing `fetch`, so they
 * exercise the real component logic and the real error shapes.
 */

import { ApiError, type AddToCartInput, type PdpApi } from "../api/client";
import type { AddToCartResult, Cart, Product } from "../api/types";

/** Mirrors `app/backend/catalog.py`: 7 SKUs, `sand`/`m` missing, `black`/`m` at 0. */
export function createProductFixture(): Product {
  const image = (label: string) =>
    `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg">${label}</svg>`;

  return {
    id: "aurora-merino-tee",
    name: "Aurora Merino Tee",
    description: "A lightweight 180 gsm merino tee.",
    currency: "USD",
    options: [
      {
        id: "color",
        label: "Colour",
        values: [
          { id: "black", label: "Black", swatch: "#1f2937" },
          { id: "white", label: "White", swatch: "#e5e7eb" },
          { id: "sand", label: "Sand", swatch: "#d9c4a3" },
        ],
      },
      {
        id: "size",
        label: "Size",
        values: [
          { id: "s", label: "S", swatch: "#94a3b8" },
          { id: "m", label: "M", swatch: "#94a3b8" },
          { id: "l", label: "L", swatch: "#94a3b8" },
        ],
      },
    ],
    skus: [
      {
        id: "sku-black-s",
        name: "Aurora Merino Tee - Black / S",
        options: { color: "black", size: "s" },
        priceCents: 2900,
        currency: "USD",
        availableQuantity: 5,
        image: image("Black / S"),
      },
      {
        id: "sku-black-m",
        name: "Aurora Merino Tee - Black / M",
        options: { color: "black", size: "m" },
        priceCents: 2900,
        currency: "USD",
        availableQuantity: 0,
        image: image("Black / M"),
      },
      {
        id: "sku-black-l",
        name: "Aurora Merino Tee - Black / L",
        options: { color: "black", size: "l" },
        priceCents: 3100,
        currency: "USD",
        availableQuantity: 3,
        image: image("Black / L"),
      },
      {
        id: "sku-white-s",
        name: "Aurora Merino Tee - White / S",
        options: { color: "white", size: "s" },
        priceCents: 2900,
        currency: "USD",
        availableQuantity: 4,
        image: image("White / S"),
      },
      {
        id: "sku-white-m",
        name: "Aurora Merino Tee - White / M",
        options: { color: "white", size: "m" },
        priceCents: 2900,
        currency: "USD",
        availableQuantity: 7,
        image: image("White / M"),
      },
      {
        id: "sku-sand-s",
        name: "Aurora Merino Tee - Sand / S",
        options: { color: "sand", size: "s" },
        priceCents: 3300,
        currency: "USD",
        availableQuantity: 2,
        image: image("Sand / S"),
      },
      {
        id: "sku-sand-l",
        name: "Aurora Merino Tee - Sand / L",
        options: { color: "sand", size: "l" },
        priceCents: 3300,
        currency: "USD",
        availableQuantity: 6,
        image: image("Sand / L"),
      },
    ],
  };
}

export type AddHandler = (
  input: AddToCartInput,
  idempotencyKey: string,
) => AddToCartResult | Promise<AddToCartResult>;

export interface FakeApi {
  api: PdpApi;
  /** Every add-to-cart request the page made, in order. */
  addCalls: Array<{ input: AddToCartInput; idempotencyKey: string }>;
  getProductCalls: () => number;
  /** Make the next `times` product requests fail (default: a 500). */
  failNextProductRequests: (times: number, error?: ApiError) => void;
  /** Replace the add-to-cart behaviour (409s, delays, ...). */
  setAddHandler: (handler: AddHandler | null) => void;
}

export function createFakeApi(product: Product = createProductFixture()): FakeApi {
  const stock = new Map(product.skus.map((sku) => [sku.id, sku.availableQuantity]));
  const cart = new Map<string, number>();
  const addCalls: Array<{ input: AddToCartInput; idempotencyKey: string }> = [];

  let productCalls = 0;
  let productFailures = 0;
  let productFailure: ApiError | null = null;
  let addHandler: AddHandler | null = null;

  const buildCart = (): Cart => {
    const items = [...cart.entries()]
      .filter(([, quantity]) => quantity > 0)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([skuId, quantity]) => {
        const sku = product.skus.find((candidate) => candidate.id === skuId);
        if (sku === undefined) {
          throw new Error(`fake cart references unknown sku ${skuId}`);
        }
        return {
          skuId,
          productId: product.id,
          name: sku.name,
          options: sku.options,
          image: sku.image,
          unitPriceCents: sku.priceCents,
          quantity,
          lineTotalCents: sku.priceCents * quantity,
        };
      });

    return {
      items,
      totalQuantity: items.reduce((total, item) => total + item.quantity, 0),
      totalPriceCents: items.reduce((total, item) => total + item.lineTotalCents, 0),
    };
  };

  const api: PdpApi = {
    getProduct() {
      productCalls += 1;
      if (productFailures > 0) {
        productFailures -= 1;
        throw (
          productFailure ??
          new ApiError(500, {
            code: "INTERNAL_ERROR",
            message: "The store is having a moment.",
          })
        );
      }
      return Promise.resolve(product);
    },

    getCart() {
      return Promise.resolve(buildCart());
    },

    async addToCart(input, idempotencyKey) {
      addCalls.push({ input, idempotencyKey });

      if (addHandler !== null) {
        return addHandler(input, idempotencyKey);
      }

      const sku = product.skus.find((candidate) => candidate.id === input.skuId);
      if (sku === undefined) {
        throw new ApiError(404, {
          code: "SKU_NOT_FOUND",
          message: `Unknown SKU '${input.skuId}'.`,
        });
      }

      const held = cart.get(sku.id) ?? 0;
      const available = (stock.get(sku.id) ?? 0) - held;
      if (input.quantity > available) {
        throw new ApiError(409, {
          code: "INSUFFICIENT_STOCK",
          message: `Only ${available} unit(s) remain.`,
          details: { skuId: sku.id, requested: input.quantity, available },
        });
      }

      cart.set(sku.id, held + input.quantity);
      return {
        cart: buildCart(),
        sku: {
          id: sku.id,
          productId: product.id,
          availableQuantity: available - input.quantity,
        },
      };
    },
  };

  return {
    api,
    addCalls,
    getProductCalls: () => productCalls,
    failNextProductRequests(times, error) {
      productFailures = times;
      productFailure = error ?? null;
    },
    setAddHandler(handler) {
      addHandler = handler;
    },
  };
}
