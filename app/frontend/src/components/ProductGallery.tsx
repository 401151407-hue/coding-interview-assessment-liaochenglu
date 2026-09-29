import type { Product, ProductSku } from "../api/types";
import { describeSku } from "../domain/format";

/**
 * The image always comes from the *resolved* SKU, so switching options can never
 * leave a stale picture on screen.
 */
export function ProductGallery({
  product,
  sku,
}: {
  product: Product;
  sku: ProductSku | undefined;
}) {
  if (sku === undefined) {
    return (
      <figure className="gallery">
        <div className="gallery__placeholder" aria-hidden="true">
          <span>Select your options</span>
        </div>
      </figure>
    );
  }

  return (
    <figure className="gallery">
      <img
        className="gallery__image"
        src={sku.image}
        alt={`${product.name} in ${describeSku(product, sku)}`}
        width={720}
        height={720}
        decoding="async"
      />
    </figure>
  );
}
