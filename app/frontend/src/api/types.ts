/**
 * Wire types for the PDP API.
 *
 * These mirror `app/backend/serializers.py` one-for-one. They are the only
 * types that describe remote data; the UI works with them directly rather than
 * re-declaring view models, so a change to the API surfaces as a type error.
 */

export interface OptionValue {
  id: string;
  label: string;
  swatch: string;
}

export interface ProductOption {
  id: string;
  label: string;
  values: OptionValue[];
}

export interface ProductSku {
  id: string;
  name: string;
  /** optionId -> valueId, e.g. `{ color: "black", size: "m" }`. */
  options: Record<string, string>;
  priceCents: number;
  currency: string;
  /** Units the server is willing to sell right now. */
  availableQuantity: number;
  /** Inline SVG data URI, so the page renders offline. */
  image: string;
}

export interface Product {
  id: string;
  name: string;
  description: string;
  currency: string;
  options: ProductOption[];
  skus: ProductSku[];
}

export interface CartLine {
  skuId: string;
  productId: string;
  name: string;
  options: Record<string, string>;
  image: string;
  unitPriceCents: number;
  quantity: number;
  lineTotalCents: number;
}

export interface Cart {
  items: CartLine[];
  totalQuantity: number;
  totalPriceCents: number;
}

export interface AddToCartResult {
  cart: Cart;
  sku: {
    id: string;
    productId: string;
    availableQuantity: number;
  };
}

export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ApiErrorEnvelope {
  error: ApiErrorPayload;
}
