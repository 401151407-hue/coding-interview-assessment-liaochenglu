import { useMemo } from "react";

import { ApiProvider } from "./api/ApiContext";
import { createHttpApi } from "./api/client";
import { ProductDetailPage } from "./pages/ProductDetailPage";

export default function App() {
  // Requests are same-origin: Vite proxies /api in development, and in
  // production the static bundle is served by the same host as the API.
  const api = useMemo(() => createHttpApi(), []);

  return (
    <ApiProvider api={api}>
      <a className="skip-link" href="#product-title">
        Skip to product details
      </a>
      <ProductDetailPage />
    </ApiProvider>
  );
}
