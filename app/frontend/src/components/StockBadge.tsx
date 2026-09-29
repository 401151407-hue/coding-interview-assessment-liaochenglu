export type StockLevel = "in-stock" | "low-stock" | "out-of-stock";

export function stockLevel(availableQuantity: number): StockLevel {
  if (availableQuantity <= 0) return "out-of-stock";
  if (availableQuantity <= 3) return "low-stock";
  return "in-stock";
}

const LOW_STOCK_THRESHOLD_LABEL = "Only a few left";

export function StockBadge({
  availableQuantity,
}: {
  availableQuantity: number;
}) {
  const level = stockLevel(availableQuantity);

  const text =
    level === "out-of-stock"
      ? "Out of stock"
      : level === "low-stock"
        ? `${LOW_STOCK_THRESHOLD_LABEL} (${availableQuantity})`
        : `In stock (${availableQuantity})`;

  return <p className={`stock stock--${level}`}>{text}</p>;
}
