import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "../api/client";
import { useApi } from "../api/ApiContext";
import type { Cart, Product, ProductSku } from "../api/types";
import { track } from "../analytics/events";
import { CartSummary } from "../components/CartSummary";
import { Feedback, type FeedbackMessage } from "../components/Feedback";
import { OptionSelector } from "../components/OptionSelector";
import { ProductGallery } from "../components/ProductGallery";
import { QuantityStepper } from "../components/QuantityStepper";
import { StockBadge } from "../components/StockBadge";
import { describeSku, formatMoney } from "../domain/format";
import { createIdempotencyKey } from "../domain/idempotency";
import {
  applySelection,
  clampQuantity,
  createSelection,
  resolveSku,
  type Selection,
} from "../domain/variants";

export const DEFAULT_PRODUCT_ID = "aurora-merino-tee";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; product: Product }
  | { status: "error"; message: string };

function describeAddFailure(error: unknown, sku: ProductSku): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "INSUFFICIENT_STOCK": {
        const available = error.details.available;
        const remaining = typeof available === "number" ? available : 0;
        return `Sorry - only ${remaining} left in ${sku.name.split(" - ")[1] ?? "that option"}. We have refreshed the stock shown.`;
      }
      case "VALIDATION_ERROR":
        return "That quantity is not valid. Please choose between 1 and the stock shown.";
      case "SKU_NOT_FOUND":
        return "That combination is no longer available. Please choose another one.";
      case "NETWORK_ERROR":
        return error.message;
      default:
        return error.isTransient
          ? "Something went wrong on our side. Please try again."
          : error.message;
    }
  }
  return "Something went wrong. Please try again.";
}

export interface ProductDetailPageProps {
  productId?: string;
}

export function ProductDetailPage({
  productId = DEFAULT_PRODUCT_ID,
}: ProductDetailPageProps) {
  const api = useApi();

  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [selection, setSelection] = useState<Selection>({});
  const [quantity, setQuantity] = useState(1);
  const [stockOverrides, setStockOverrides] = useState<Partial<Record<string, number>>>({});
  const [cart, setCart] = useState<Cart | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackMessage | null>(null);
  const addInFlight = useRef(false);

  const loadProduct = useCallback(async () => {
    setLoadState({ status: "loading" });
    setFeedback(null);
    try {
      const loaded = await api.getProduct(productId);
      setLoadState({ status: "ready", product: loaded });
      setSelection(createSelection(loaded));
      setStockOverrides({});
      setQuantity(1);
      track({ name: "view_item", productId: loaded.id, currency: loaded.currency });
    } catch (error) {
      setLoadState({
        status: "error",
        message:
          error instanceof ApiError
            ? error.message
            : "We could not load this product.",
      });
    }
  }, [api, productId]);

  useEffect(() => {
    void loadProduct();
  }, [loadProduct]);

  // The cart is fetched alongside the product and is deliberately non-fatal: a
  // failure here must not block the primary task of browsing and adding.
  useEffect(() => {
    let cancelled = false;
    api.getCart().then(
      (loaded) => {
        if (!cancelled) setCart(loaded);
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [api]);

  const product = loadState.status === "ready" ? loadState.product : null;

  /**
   * Stock the server told us about *after* the initial product response - e.g.
   * the availability returned by an add-to-cart call, or the real remaining
   * quantity reported by a 409. This is how the UI converges without a reload.
   */
  const liveProduct = useMemo<Product | null>(() => {
    if (product === null) {
      return null;
    }
    return {
      ...product,
      skus: product.skus.map((sku) => {
        const override = stockOverrides[sku.id];
        return override === undefined
          ? sku
          : { ...sku, availableQuantity: override };
      }),
    };
  }, [product, stockOverrides]);

  const sku = useMemo(
    () => (liveProduct === null ? undefined : resolveSku(liveProduct, selection)),
    [liveProduct, selection],
  );

  const maxQuantity = sku?.availableQuantity ?? 1;
  const canAddToCart = sku !== undefined && sku.availableQuantity > 0 && !isAdding;

  // Keep the quantity inside the current SKU's stock, including after the
  // selected SKU changes or a stock override arrives.
  useEffect(() => {
    setQuantity((current) => clampQuantity(current, Math.max(maxQuantity, 1)));
  }, [maxQuantity]);

  const handleSelect = useCallback(
    (optionId: string, valueId: string) => {
      if (liveProduct === null) {
        return;
      }
      const next = applySelection(liveProduct, selection, optionId, valueId);
      setSelection(next);
      setFeedback(null);

      const resolved = resolveSku(liveProduct, next);
      if (resolved !== undefined) {
        track({
          name: "select_item",
          productId: liveProduct.id,
          skuId: resolved.id,
          optionId,
          valueId,
        });
      }
    },
    [liveProduct, selection],
  );

  const handleAddToCart = useCallback(async () => {
    if (liveProduct === null || sku === undefined || addInFlight.current) {
      return;
    }
    // A fresh key per attempt. Combined with the ref guard this makes a double
    // click produce exactly one request, and a genuine retry a new intent.
    addInFlight.current = true;
    setIsAdding(true);
    setFeedback(null);

    const amount = clampQuantity(quantity, Math.max(sku.availableQuantity, 1));

    try {
      const result = await api.addToCart(
        { skuId: sku.id, quantity: amount },
        createIdempotencyKey(),
      );
      setCart(result.cart);
      setStockOverrides((current) => ({
        ...current,
        [result.sku.id]: result.sku.availableQuantity,
      }));
      setFeedback({
        tone: "success",
        text: `Added ${amount} \u00d7 ${liveProduct.name} (${describeSku(liveProduct, sku)}) to your bag.`,
      });
      track({
        name: "add_to_cart",
        productId: result.sku.productId,
        skuId: sku.id,
        quantity: amount,
        valueCents: sku.priceCents * amount,
        currency: sku.currency,
      });
    } catch (error) {
      setFeedback({ tone: "error", text: describeAddFailure(error, sku) });
      if (error instanceof ApiError && error.code === "INSUFFICIENT_STOCK") {
        const available = error.details.available;
        if (typeof available === "number") {
          setStockOverrides((current) => ({ ...current, [sku.id]: available }));
        }
      }
    } finally {
      addInFlight.current = false;
      setIsAdding(false);
    }
  }, [api, liveProduct, quantity, sku]);

  const topBar = (
    <header className="topbar">
      <span className="topbar__brand">Northwind Goods</span>
      <CartSummary cart={cart} />
    </header>
  );

  if (loadState.status === "loading") {
    return (
      <>
        {topBar}
        <main className="layout">
          <div className="pdp" aria-busy="true">
            <div className="gallery gallery--loading" aria-hidden="true" />
            <div className="product-summary">
              <p className="loading-text" role="status">
                Loading product&hellip;
              </p>
              <div className="skeleton skeleton--title" aria-hidden="true" />
              <div className="skeleton skeleton--text" aria-hidden="true" />
              <div className="skeleton skeleton--text-short" aria-hidden="true" />
            </div>
          </div>
        </main>
      </>
    );
  }

  if (loadState.status === "error") {
    return (
      <>
        {topBar}
        <main className="layout">
          <div className="panel" role="alert">
            <h2 className="panel__title">We could not load this product</h2>
            <p className="panel__text">{loadState.message}</p>
            <button
              type="button"
              className="button button--primary"
              onClick={() => void loadProduct()}
            >
              Try again
            </button>
          </div>
        </main>
      </>
    );
  }

  const shown = liveProduct as Product;
  const unchosen = shown.options.filter((option) => !selection[option.id]);
  const allChosen = unchosen.length === 0;
  const isOutOfStock = sku !== undefined && sku.availableQuantity === 0;

  return (
    <>
      {topBar}
      <main className="layout">
        <div className="pdp">
          <ProductGallery product={shown} sku={sku} />

          <section className="product-summary" aria-labelledby="product-title">
            <p className="eyebrow">Merino essentials</p>
            <h1 className="product-title" id="product-title">
              {shown.name}
            </h1>
            <p className="product-description">{shown.description}</p>

            <div className="price-row">
              <p className="price" aria-live="polite">
                {sku !== undefined ? (
                  formatMoney(sku.priceCents, sku.currency)
                ) : (
                  <span className="price--pending">&mdash;</span>
                )}
              </p>

              {sku !== undefined ? (
                <StockBadge availableQuantity={sku.availableQuantity} />
              ) : (
                <p className="stock stock--pending">
                  {allChosen
                    ? "This combination is not available."
                    : `Select ${unchosen.map((option) => option.label.toLowerCase()).join(" and ")} to see price and stock.`}
                </p>
              )}
            </div>

            <div className="options">
              {shown.options.map((option) => (
                <OptionSelector
                  key={option.id}
                  product={shown}
                  option={option}
                  selection={selection}
                  groupId={shown.id}
                  onSelect={handleSelect}
                />
              ))}
            </div>

            <div className="purchase">
              <QuantityStepper
                value={quantity}
                max={maxQuantity}
                disabled={sku === undefined || isOutOfStock}
                onChange={setQuantity}
              />

              <button
                type="button"
                className="button button--primary button--add"
                data-testid="add-to-cart"
                onClick={() => void handleAddToCart()}
                disabled={!canAddToCart}
                aria-busy={isAdding}
              >
                {isAdding
                  ? "Adding\u2026"
                  : isOutOfStock
                    ? "Out of stock"
                    : sku === undefined
                      ? "Select options"
                      : "Add to bag"}
                {sku !== undefined ? (
                  <span className="sr-only">
                    {" "}
                    {describeSku(shown, sku)}, quantity {quantity}
                  </span>
                ) : null}
              </button>
            </div>

            <Feedback message={feedback} />

            {sku === undefined && allChosen ? (
              <p className="notice">
                No SKU exists for this combination. Choose a different colour or
                size.
              </p>
            ) : null}
          </section>
        </div>
      </main>
    </>
  );
}
