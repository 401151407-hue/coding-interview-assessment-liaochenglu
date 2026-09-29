import type { Product, ProductSku } from "../api/types";

const formatters = new Map<string, Intl.NumberFormat>();

export function formatMoney(cents: number, currency: string): string {
  let formatter = formatters.get(currency);
  if (formatter === undefined) {
    formatter = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
    });
    formatters.set(currency, formatter);
  }
  return formatter.format(cents / 100);
}

/** A human label for the currently selected options, e.g. `Black / M`. */
export function describeSku(product: Product, sku: ProductSku): string {
  return product.options
    .map((option) => {
      const valueId = sku.options[option.id];
      const value = option.values.find((candidate) => candidate.id === valueId);
      return value?.label ?? valueId ?? "";
    })
    .filter((part) => part.length > 0)
    .join(" / ");
}
