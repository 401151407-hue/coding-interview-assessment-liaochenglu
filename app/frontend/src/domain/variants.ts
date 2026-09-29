/**
 * Variant resolution - the "brain" of the PDP, kept free of React so it can be
 * unit tested directly and reused by whatever renders it.
 *
 * The important subtlety: the availability of a value is evaluated against the
 * *other* option dimensions only (`optionValueState`). If the value's own
 * selection were included, a value could never invalidate itself and a stale,
 * impossible combination could stay selectable.
 */

import type { Product, ProductSku } from "../api/types";

/** optionId -> valueId (or `undefined` while the dimension is unchosen). */
export type Selection = Record<string, string | undefined>;

export type OptionValueState = "available" | "out-of-stock" | "unavailable";

export function createSelection(product: Product): Selection {
  const selection: Selection = {};
  for (const option of product.options) {
    selection[option.id] = undefined;
  }
  return selection;
}

export function isSelectionComplete(product: Product, selection: Selection): boolean {
  return product.options.every((option) => Boolean(selection[option.id]));
}

export function countChosenOptions(product: Product, selection: Selection): number {
  return product.options.filter((option) => Boolean(selection[option.id])).length;
}

/** The single SKU matching a complete selection, or `undefined` otherwise. */
export function resolveSku(
  product: Product,
  selection: Selection,
): ProductSku | undefined {
  if (!isSelectionComplete(product, selection)) {
    return undefined;
  }
  return product.skus.find((sku) =>
    product.options.every(
      (option) => sku.options[option.id] === selection[option.id],
    ),
  );
}

/**
 * How a single value of one dimension should be presented given the current
 * selection of the *other* dimensions.
 *
 * - `unavailable`  no SKU exists for this combination -> the control is disabled
 * - `out-of-stock` a SKU exists but cannot be sold -> selectable, but not buyable
 */
export function optionValueState(
  product: Product,
  selection: Selection,
  optionId: string,
  valueId: string,
): OptionValueState {
  const otherOptions = product.options.filter((option) => option.id !== optionId);

  const candidates = product.skus.filter(
    (sku) =>
      sku.options[optionId] === valueId &&
      otherOptions.every((option) => {
        const chosen = selection[option.id];
        return chosen === undefined || sku.options[option.id] === chosen;
      }),
  );

  if (candidates.length === 0) {
    return "unavailable";
  }
  return candidates.some((sku) => sku.availableQuantity > 0)
    ? "available"
    : "out-of-stock";
}

export interface OptionValueReport {
  id: string;
  state: OptionValueState;
  selectable: boolean;
}

/** Presentation-ready report for every value of one dimension. */
export function reportOptionValues(
  product: Product,
  selection: Selection,
  optionId: string,
): OptionValueReport[] {
  const option = product.options.find((candidate) => candidate.id === optionId);
  if (option === undefined) {
    return [];
  }
  return option.values.map((value) => {
    const state = optionValueState(product, selection, optionId, value.id);
    return { id: value.id, state, selectable: state !== "unavailable" };
  });
}

/**
 * Apply a selection, dropping any choice in another dimension that the new
 * value makes impossible. The UI disables those controls, so this is a safety
 * net for programmatic changes (deep links, restored state).
 */
export function applySelection(
  product: Product,
  selection: Selection,
  optionId: string,
  valueId: string,
): Selection {
  const next: Selection = { ...selection, [optionId]: valueId };

  for (const option of product.options) {
    if (option.id === optionId) {
      continue;
    }
    const chosen = next[option.id];
    if (chosen === undefined) {
      continue;
    }
    if (optionValueState(product, next, option.id, chosen) === "unavailable") {
      next[option.id] = undefined;
    }
  }

  return next;
}

/** Keep a quantity inside `1..max`, tolerating `0`/`NaN` from number inputs. */
export function clampQuantity(quantity: number, max: number): number {
  const ceiling = Math.max(Math.floor(max), 1);
  if (!Number.isFinite(quantity)) {
    return 1;
  }
  const whole = Math.floor(quantity);
  if (whole < 1) {
    return 1;
  }
  if (whole > ceiling) {
    return ceiling;
  }
  return whole;
}
