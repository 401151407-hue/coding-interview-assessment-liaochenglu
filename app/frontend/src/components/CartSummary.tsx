import type { Cart } from "../api/types";

export function CartSummary({ cart }: { cart: Cart | null }) {
  const count = cart?.totalQuantity ?? 0;

  return (
    <div className="cart-summary">
      <span className="cart-summary__label">Bag</span>
      <span className="cart-summary__count" data-testid="cart-count">
        {count}
      </span>
      <span className="sr-only">
        {count === 1 ? "1 item in your bag" : `${count} items in your bag`}
      </span>
    </div>
  );
}
