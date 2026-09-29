/**
 * Analytics event design (optional extension).
 *
 * Contract: events carry *shopping* data only. No customer identifiers, no cart
 * contents from other sessions, no tokens, no free-text the user typed. The sink
 * is injectable so production can point it at a collector and tests can assert
 * on the payload.
 */

export interface ViewItemEvent {
  name: "view_item";
  productId: string;
  currency: string;
}

export interface SelectItemEvent {
  name: "select_item";
  productId: string;
  skuId: string;
  optionId: string;
  valueId: string;
}

export interface AddToCartEvent {
  name: "add_to_cart";
  productId: string;
  skuId: string;
  quantity: number;
  valueCents: number;
  currency: string;
}

export type AnalyticsEvent = ViewItemEvent | SelectItemEvent | AddToCartEvent;

export type AnalyticsSink = (event: AnalyticsEvent) => void;

const consoleSink: AnalyticsSink = (event) => {
  // eslint-disable-next-line no-console -- the default sink is intentionally a log
  console.info("[analytics]", event);
};

let sink: AnalyticsSink = consoleSink;

export function setAnalyticsSink(next: AnalyticsSink): void {
  sink = next;
}

export function track(event: AnalyticsEvent): void {
  sink(event);
}
