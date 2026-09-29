import { createContext, useContext, type ReactNode } from "react";

import type { PdpApi } from "./client";

const ApiContext = createContext<PdpApi | null>(null);

export function ApiProvider({
  api,
  children,
}: {
  api: PdpApi;
  children: ReactNode;
}) {
  return <ApiContext.Provider value={api}>{children}</ApiContext.Provider>;
}

/** Access the injected API. Throws rather than returning a default so a missing
 *  provider fails loudly in development instead of silently hitting the network. */
export function useApi(): PdpApi {
  const api = useContext(ApiContext);
  if (api === null) {
    throw new Error("useApi() must be called inside an <ApiProvider>");
  }
  return api;
}
