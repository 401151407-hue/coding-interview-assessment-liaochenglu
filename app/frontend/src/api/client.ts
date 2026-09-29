/**
 * HTTP client for the PDP API.
 *
 * Everything remote lives behind the `PdpApi` interface so the UI never touches
 * `fetch` directly, and so tests can inject a fake implementation instead of
 * monkey-patching globals.
 */

import type {
  AddToCartResult,
  ApiErrorEnvelope,
  ApiErrorPayload,
  Cart,
  Product,
} from "./types";

export interface AddToCartInput {
  skuId: string;
  quantity: number;
}

export interface PdpApi {
  getProduct(productId: string): Promise<Product>;
  getCart(): Promise<Cart>;
  addToCart(input: AddToCartInput, idempotencyKey: string): Promise<AddToCartResult>;
}

/** A structured failure from the API (or from the network layer). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message);
    this.name = "ApiError";
    this.status = status;
    this.code = payload.code;
    this.details = payload.details ?? {};
  }

  /** True when retrying the same request could plausibly succeed. */
  get isTransient(): boolean {
    return this.status === 0 || this.status >= 500 || this.status === 429;
  }
}

const DEFAULT_TIMEOUT_MS = 8000;

function isApiErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (typeof value !== "object" || value === null) return false;
  const candidate = (value as { error?: unknown }).error;
  return (
    typeof candidate === "object" &&
    candidate !== null &&
    typeof (candidate as { code?: unknown }).code === "string" &&
    typeof (candidate as { message?: unknown }).message === "string"
  );
}

function toErrorPayload(payload: unknown, status: number): ApiErrorPayload {
  if (isApiErrorEnvelope(payload)) {
    const { code, message, details } = payload.error;
    return { code, message, details };
  }
  return {
    code: `HTTP_${status}`,
    message: "The store returned an unexpected response. Please try again.",
  };
}

export interface HttpApiOptions {
  baseUrl?: string;
  timeoutMs?: number;
}

export function createHttpApi(options: HttpApiOptions = {}): PdpApi {
  const baseUrl = options.baseUrl ?? "";
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    let response: Response;
    try {
      response = await fetch(`${baseUrl}${path}`, {
        ...init,
        headers: { Accept: "application/json", ...(init.headers ?? {}) },
        signal: controller.signal,
      });
    } catch (cause) {
      // Aborts and transport failures are indistinguishable to the caller, and
      // both are retryable from the user's point of view.
      throw new ApiError(0, {
        code: "NETWORK_ERROR",
        message:
          cause instanceof DOMException && cause.name === "AbortError"
            ? "The store took too long to respond. Please try again."
            : "We could not reach the store. Check your connection and try again.",
      });
    } finally {
      clearTimeout(timer);
    }

    const payload: unknown = await response.json().catch(() => null);

    if (!response.ok) {
      throw new ApiError(response.status, toErrorPayload(payload, response.status));
    }
    return payload as T;
  }

  return {
    getProduct(productId) {
      return request<Product>(`/api/products/${encodeURIComponent(productId)}`);
    },

    getCart() {
      return request<Cart>("/api/cart");
    },

    addToCart(input, idempotencyKey) {
      return request<AddToCartResult>("/api/cart/items", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify({ skuId: input.skuId, quantity: input.quantity }),
      });
    },
  };
}
