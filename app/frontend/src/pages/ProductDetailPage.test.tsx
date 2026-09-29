import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ApiProvider } from "../api/ApiContext";
import { ApiError } from "../api/client";
import type { AddToCartResult } from "../api/types";
import { createFakeApi, type FakeApi } from "../test/fakeApi";
import { ProductDetailPage } from "./ProductDetailPage";

function renderPage(fake: FakeApi) {
  return render(
    <ApiProvider api={fake.api}>
      <ProductDetailPage />
    </ApiProvider>,
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function resultFor(skuId: string, quantity: number, remaining: number): AddToCartResult {
  return {
    cart: {
      items: [],
      totalQuantity: quantity,
      totalPriceCents: 2900 * quantity,
    },
    sku: { id: skuId, productId: "aurora-merino-tee", availableQuantity: remaining },
  };
}

/** The add button's label changes with state, so it is located by test id. Its
 *  accessible name is asserted separately in the first test. */
const addToBag = () => screen.getByTestId("add-to-cart");
const quantityInput = () => screen.getByRole("spinbutton", { name: /quantity/i });

describe("ProductDetailPage", () => {
  it("loads the product and starts with an incomplete, non-purchasable selection", async () => {
    renderPage(createFakeApi());

    expect(
      await screen.findByRole("heading", { name: "Aurora Merino Tee" }),
    ).toBeInTheDocument();

    expect(screen.getByText(/select colour and size to see price and stock/i)).toBeInTheDocument();
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /select options/i })).toBeDisabled();
    expect(screen.getByTestId("cart-count")).toHaveTextContent("0");
  });

  it("resolves the SKU on selection and keeps price, image and stock in sync", async () => {
    const user = userEvent.setup();
    renderPage(createFakeApi());
    await screen.findByRole("heading", { name: "Aurora Merino Tee" });

    await user.click(screen.getByRole("radio", { name: "Black" }));
    await user.click(screen.getByRole("radio", { name: "S" }));

    expect(screen.getByText("$29.00")).toBeInTheDocument();
    expect(screen.getByText("In stock (5)")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /black \/ s/i })).toHaveAttribute(
      "src",
      expect.stringContaining("Black / S"),
    );

    // Switching size must replace every derived value, never leave the old one.
    await user.click(screen.getByRole("radio", { name: "L" }));

    expect(screen.getByText("$31.00")).toBeInTheDocument();
    expect(screen.getByText("Only a few left (3)")).toBeInTheDocument();
    expect(screen.queryByText("$29.00")).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: /black \/ l/i })).toBeInTheDocument();
    // The control is announced with the resolved variant and quantity.
    expect(addToBag()).toHaveAccessibleName(
      /add to bag\s+Black \/ L, quantity 1/i,
    );
  });

  it("disables a combination that has no SKU at all", async () => {
    const user = userEvent.setup();
    renderPage(createFakeApi());
    await screen.findByRole("heading", { name: "Aurora Merino Tee" });

    const sizeM = screen.getByRole("radio", { name: /^M/ });
    expect(sizeM).toBeEnabled();

    await user.click(screen.getByRole("radio", { name: "Sand" }));

    expect(screen.getByRole("radio", { name: /^M/ })).toBeDisabled();
  });

  it("keeps a sold-out combination selectable but not purchasable", async () => {
    const user = userEvent.setup();
    renderPage(createFakeApi());
    await screen.findByRole("heading", { name: "Aurora Merino Tee" });

    await user.click(screen.getByRole("radio", { name: "Black" }));
    expect(screen.getByRole("radio", { name: /^M/ })).toBeEnabled();

    await user.click(screen.getByRole("radio", { name: /^M/ }));

    expect(screen.getByText("Out of stock", { selector: ".stock" })).toBeInTheDocument();
    expect(addToBag()).toBeDisabled();
    expect(quantityInput()).toBeDisabled();
  });

  it("bounds the quantity by the selected SKU's stock and re-clamps on SKU change", async () => {
    const user = userEvent.setup();
    renderPage(createFakeApi());
    await screen.findByRole("heading", { name: "Aurora Merino Tee" });

    await user.click(screen.getByRole("radio", { name: "Sand" }));
    await user.click(screen.getByRole("radio", { name: "S" })); // 2 in stock

    await user.click(screen.getByRole("button", { name: /increase quantity/i }));
    expect(quantityInput()).toHaveValue(2);
    expect(screen.getByRole("button", { name: /increase quantity/i })).toBeDisabled();

    await user.type(quantityInput(), "9");
    expect(quantityInput()).toHaveValue(2);

    // Switching to a bigger SKU must not carry an out-of-range quantity over.
    await user.click(screen.getByRole("button", { name: /increase quantity/i }));
    expect(quantityInput()).toHaveValue(2);
  });

  it("adds to the bag exactly once when the button is clicked twice in one tick", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi();
    const gate = deferred<void>();

    fake.setAddHandler(async (input) => {
      await gate.promise;
      return resultFor(input.skuId, input.quantity, 4);
    });

    renderPage(fake);
    await screen.findByRole("heading", { name: "Aurora Merino Tee" });
    await user.click(screen.getByRole("radio", { name: "Black" }));
    await user.click(screen.getByRole("radio", { name: "S" }));

    const button = addToBag();
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });

    expect(fake.addCalls).toHaveLength(1);
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText(/adding/i)).toBeInTheDocument();

    await act(async () => {
      gate.resolve();
      await gate.promise;
    });

    expect(await screen.findByText(/Added 1/)).toBeInTheDocument();
    expect(screen.getByTestId("cart-count")).toHaveTextContent("1");
    expect(addToBag()).toBeEnabled();
  });

  it("reports a server-side stock conflict and refreshes the stock shown", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi();
    fake.setAddHandler(() => {
      throw new ApiError(409, {
        code: "INSUFFICIENT_STOCK",
        message: "Only 1 unit(s) remain.",
        details: { skuId: "sku-black-s", requested: 2, available: 1 },
      });
    });

    renderPage(fake);
    await screen.findByRole("heading", { name: "Aurora Merino Tee" });
    await user.click(screen.getByRole("radio", { name: "Black" }));
    await user.click(screen.getByRole("radio", { name: "S" }));

    await user.click(addToBag());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/only 1 left/i);
    expect(screen.getByText("Only a few left (1)", { selector: ".stock" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /increase quantity/i })).toBeDisabled();
    expect(screen.getByTestId("cart-count")).toHaveTextContent("0");
  });

  it("surfaces a transport failure without losing the current selection", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi();
    fake.setAddHandler(() => {
      throw new ApiError(0, {
        code: "NETWORK_ERROR",
        message: "We could not reach the store. Check your connection and try again.",
      });
    });

    renderPage(fake);
    await screen.findByRole("heading", { name: "Aurora Merino Tee" });
    await user.click(screen.getByRole("radio", { name: "Black" }));
    await user.click(screen.getByRole("radio", { name: "S" }));

    await user.click(addToBag());

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach the store/i);
    expect(screen.getByText("$29.00")).toBeInTheDocument();
    expect(addToBag()).toBeEnabled();
  });

  it("offers a retry when the product fails to load", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi();
    fake.failNextProductRequests(1);

    renderPage(fake);

    const panel = await screen.findByRole("alert");
    expect(panel).toHaveTextContent(/could not load this product/i);
    expect(fake.getProductCalls()).toBe(1);

    await user.click(screen.getByRole("button", { name: /try again/i }));

    expect(
      await screen.findByRole("heading", { name: "Aurora Merino Tee" }),
    ).toBeInTheDocument();
    expect(fake.getProductCalls()).toBe(2);
  });

  it("sends a distinct idempotency key per add attempt", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi();

    renderPage(fake);
    await screen.findByRole("heading", { name: "Aurora Merino Tee" });
    await user.click(screen.getByRole("radio", { name: "White" }));
    await user.click(screen.getByRole("radio", { name: "S" }));

    await user.click(addToBag());
    await screen.findByText(/Added 1/);
    await user.click(addToBag());
    await screen.findByText(/Added 1/);

    expect(fake.addCalls).toHaveLength(2);
    const [first, second] = fake.addCalls;
    expect(first?.idempotencyKey).toBeTruthy();
    expect(second?.idempotencyKey).toBeTruthy();
    expect(first?.idempotencyKey).not.toBe(second?.idempotencyKey);
  });
});
