import { describe, expect, it } from "vitest";

import { createProductFixture } from "../test/fakeApi";
import {
  applySelection,
  clampQuantity,
  createSelection,
  isSelectionComplete,
  optionValueState,
  reportOptionValues,
  resolveSku,
  type Selection,
} from "./variants";

const product = createProductFixture();

function select(entries: Record<string, string>): Selection {
  return { ...createSelection(product), ...entries };
}

describe("resolveSku", () => {
  it("returns undefined until every dimension is chosen", () => {
    expect(resolveSku(product, createSelection(product))).toBeUndefined();
    expect(resolveSku(product, select({ color: "black" }))).toBeUndefined();
    expect(isSelectionComplete(product, select({ color: "black" }))).toBe(false);
  });

  it("resolves the SKU for a complete selection", () => {
    const sku = resolveSku(product, select({ color: "black", size: "l" }));
    expect(sku?.id).toBe("sku-black-l");
    expect(sku?.priceCents).toBe(3100);
    expect(sku?.availableQuantity).toBe(3);
  });

  it("returns undefined for a combination with no SKU", () => {
    expect(resolveSku(product, select({ color: "sand", size: "m" }))).toBeUndefined();
  });

  it("still resolves an out-of-stock SKU", () => {
    const sku = resolveSku(product, select({ color: "black", size: "m" }));
    expect(sku?.id).toBe("sku-black-m");
    expect(sku?.availableQuantity).toBe(0);
  });
});

describe("optionValueState", () => {
  it("marks a value with no SKU at all as unavailable", () => {
    // `sand` + `m` has no SKU in either selection order.
    expect(optionValueState(product, select({}), "size", "m")).toBe("available");
    const withSand = select({ color: "sand" });
    expect(optionValueState(product, withSand, "size", "m")).toBe("unavailable");
    const withM = select({ size: "m" });
    expect(optionValueState(product, withM, "color", "sand")).toBe("unavailable");
  });

  it("marks a value whose only SKU is sold out as out-of-stock, not unavailable", () => {
    const withBlack = select({ color: "black" });
    expect(optionValueState(product, withBlack, "size", "m")).toBe("out-of-stock");
    expect(optionValueState(product, withBlack, "size", "l")).toBe("available");
  });

  it("ignores the value's own dimension when judging availability", () => {
    // Even with `size: "m"` selected, the colour options are judged only against
    // the *other* dimensions, so `sand` is correctly reported as unavailable.
    const selection = select({ size: "m" });
    expect(optionValueState(product, selection, "color", "sand")).toBe("unavailable");
    expect(optionValueState(product, selection, "color", "white")).toBe("available");
  });

  it("reports every value of a dimension in one pass", () => {
    const reports = reportOptionValues(product, select({ color: "black" }), "size");
    expect(reports.map((report) => [report.id, report.state])).toEqual([
      ["s", "available"],
      ["m", "out-of-stock"],
      ["l", "available"],
    ]);
    expect(reports.find((report) => report.id === "m")?.selectable).toBe(true);
  });

  it("marks unavailable values as not selectable", () => {
    const reports = reportOptionValues(product, select({ color: "sand" }), "size");
    expect(reports.find((report) => report.id === "m")?.selectable).toBe(false);
  });
});

describe("applySelection", () => {
  it("records the chosen value", () => {
    const next = applySelection(product, createSelection(product), "color", "white");
    expect(next.color).toBe("white");
  });

  it("clears another dimension when the new value makes it impossible", () => {
    const before = select({ size: "m" });
    const after = applySelection(product, before, "color", "sand");
    expect(after.color).toBe("sand");
    expect(after.size).toBeUndefined();
  });

  it("keeps a still-possible choice in the other dimension", () => {
    const before = select({ size: "l" });
    const after = applySelection(product, before, "color", "sand");
    expect(after).toEqual({ color: "sand", size: "l" });
  });
});

describe("clampQuantity", () => {
  it("keeps the value inside 1..max", () => {
    expect(clampQuantity(0, 5)).toBe(1);
    expect(clampQuantity(-3, 5)).toBe(1);
    expect(clampQuantity(3, 5)).toBe(3);
    expect(clampQuantity(9, 5)).toBe(5);
  });

  it("tolerates NaN and fractional input", () => {
    expect(clampQuantity(Number.NaN, 5)).toBe(1);
    expect(clampQuantity(2.7, 5)).toBe(2);
  });

  it("never returns less than 1, even when nothing is in stock", () => {
    expect(clampQuantity(4, 0)).toBe(1);
  });
});
