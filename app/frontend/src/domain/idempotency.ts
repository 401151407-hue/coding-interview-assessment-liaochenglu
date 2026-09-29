/**
 * Client generated idempotency keys.
 *
 * A fresh key per *attempt* is what lets the server tell "the user clicked twice"
 * apart from "my response was lost and I am retrying the same intent".
 */

export function createIdempotencyKey(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi !== undefined && typeof cryptoApi.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }
  // Fallback for older browsers / non-secure contexts. The key only has to be
  // unique per client, not cryptographically strong.
  return `pdp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
