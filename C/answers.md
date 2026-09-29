# Task C - Xero Integration Review

**Scenario.** A multi-tenant service synchronises invoices between an internal order
system and Xero. Background workers hold, per connected organisation: the OAuth
tokens, the tenant/connection id, and the sync cursor.

## Reference material and stated assumptions

Pages relied on (canonical Xero developer documentation):

| Topic | Page |
| --- | --- |
| OAuth 2.0 authorisation flow, tokens, connections | <https://developer.xero.com/documentation/guides/oauth2/auth-flow/> |
| Scopes and least privilege | <https://developer.xero.com/documentation/guides/oauth2/scopes/> |
| Tenants / connections | <https://developer.xero.com/documentation/guides/oauth2/tenants/> |
| Rate limits and 429 behaviour | <https://developer.xero.com/documentation/guides/oauth2/limits/> |
| Accounting API - Invoices | <https://developer.xero.com/documentation/api/accounting/invoices> |
| Accounting API - overview, paging, `If-Modified-Since` | <https://developer.xero.com/documentation/api/accounting/overview> |
| Accounting API - errors | <https://developer.xero.com/documentation/api/accounting/errors> |

**Assumptions about SDK / API version.**

* The Accounting API surface referenced is the documented `2.0` endpoint family
  (`https://api.xero.com/api.xro/2.0/...`) reached over plain HTTPS. The design
  does not depend on any particular SDK, so an SDK upgrade cannot silently change
  the behaviour described here.
* Header names for rate limiting (`Retry-After`, `X-Rate-Limit-Problem`,
  `X-MinLimit-Remaining`, `X-DayLimit-Remaining`, `X-AppMinLimit-Remaining`) are
  treated as **capability-probed at runtime, not hard-coded**: the worker reads
  whichever of them is present and degrades to conservative defaults when a
  header is missing. This keeps the integration correct if Xero renames or adds a
  budget window.
* `UpdatedDateUTC` on invoice records is the incremental-sync watermark field and
  is always compared in UTC.
* Access tokens are short lived (order of ~30 minutes) and refresh tokens rotate
  on every refresh and eventually expire. Exact lifetimes are configuration, not
  assumptions - the code compares `expires_in`/`expires_at` rather than constants.
* "Environments" below means: Xero **demo company**, any **sandbox/trial**
  organisation, and a **production** organisation. They are separate
  organisations with separate tenant ids, separate connection records and
  separate data. There is no shared state between them.

> Note for the reviewer: `developer.xero.com` renders its content client-side, so
> the pages above were used as the authoritative entry points but their body text
> could not be captured verbatim from this environment. Where a specific number or
> header name matters, the design reads it from the response at runtime instead of
> trusting a constant.

---

## C1 - Connection verification

Goal: prove, in the smallest number of calls and before touching any invoice data,
that (a) the app can authenticate, (b) the token is usable at the API surface,
(c) the token is bound to the intended organisation, and (d) the token carries the
scopes needed to read invoices.

**Sequence**

| # | Call | What a success proves |
| --- | --- | --- |
| 0 | `POST https://identity.xero.com/connect/token` with `grant_type=refresh_token` | The client id/secret are correct, the refresh token is still valid and has not been revoked or rotated away, and the token endpoint is reachable. A `400 invalid_grant` proves the *opposite*: the connection needs re-consent. |
| 1 | `GET https://api.xero.com/connections` (`Authorization: Bearer ...`) | That the freshly issued access token is accepted by the API host - not just by the identity host - and returns the full list of organisations this token may act on. |
| 2 | Compare the stored `tenantId` against the `tenantId` values in that list | That tenant selection is still valid. The tenant id is never inferred from the organisation name. |
| 3 | `GET /api.xro/2.0/Organisation` with `Xero-tenant-id: <tenantId>` | That the **tenant header** is accepted and that the token's scopes cover `accounting.settings`. The response body also gives the organisation's name/legal name/`OrganisationID`, which is cross-checked against the tenant id we have stored for that organisation. This is the call that turns "a token works" into "this token works *for this tenant*". |
| 4 | `GET /api.xro/2.0/Invoices?page=1` (optionally `pageSize=1`) with the same headers | That the scope actually needed for the job - `accounting.transactions` / `accounting.transactions.read` - is granted, and that the response shape matches the SDK/version we parse against. |

**Why this order.** Step 0-2 are cheap, read-only and cannot mutate business data; they
isolate *credential* problems from *permission* problems. Step 3 isolates *tenant
selection* problems. Step 4 is the first call that proves the exact scope and
payload contract the sync depends on. If step 4 fails with `403` while step 3
succeeded, the tenant and token are fine and the problem is a missing invoice
scope - a distinction that saves a lot of debugging.

**Failure meanings at a glance**

| Observable | Meaning |
| --- | --- |
| `invalid_grant` on `/connect/token` | Refresh token revoked, expired, or already rotated - re-consent required. |
| `401` from `/connections` with a token that step 0 just minted | Token was minted by the wrong environment/tenant-of-application, clock skew beyond tolerance, or the token is being sent to the wrong host. |
| `200` from `/connections` but an **empty array** | The token is valid, but the user has disconnected/revoked every organisation. Re-consent; do not retry. |
| `200` from `/connections`, tenant id **not** in the list | The organisation was revoked individually, or we are pointing at the wrong environment's tenant id. |
| `403` on `/Organisation` | Tenant header missing/wrong, or the `accounting.settings(.read)` scope was not granted. |
| `403` on `/Invoices` only | Invoice scope (`accounting.transactions(.read)`) missing - the token is otherwise healthy. |

---

## C2 - Failure diagnosis decision tree

Precondition: the token endpoint call *succeeds*, so credentials and the refresh
flow are working. The invoice request itself returns `401`, `403` or `404` in
different environments.

```
Invoice request failed
│
├─ 401 Unauthorized ─────────────────────────────────────────────────────────────
│   The token was not accepted at all. Check, in this order:
│   1. Was the token refreshed before the call? Is `expires_at - now < skew`?
│      → refresh proactively at ~80% of lifetime; a 401 is often just a late refresh.
│   2. Is the request hitting `api.xero.com` with a token minted by
│      `identity.xero.com`? Mixing the two hosts, or a proxy that strips the
│      `Authorization` header, produces exactly this.
│   3. Is the worker's clock skewed vs UTC? Reject/normalise tokens whose `iat`
│      is in the future.
│   4. Did refresh return `400 invalid_grant`? → refresh token dead (rotated by
│      another worker, revoked by the user, or expired). Mark the connection as
│      `NEEDS_RECONSENT`, stop retrying, raise an operator action.
│   5. Is the token from a *different environment's* app? Demo/sandbox/production
│      applications have different client ids; a demo token cannot be used
│      against a production tenant.
│   Fix: refresh, then re-consent. Never retry a 401 blindly.
│
├─ 403 Forbidden ────────────────────────────────────────────────────────────────
│   The token is valid but is not allowed to do this to this tenant.
│   1. Scope check: compare the `scope` returned by the token endpoint with the
│      operation. `GET /Invoices` needs `accounting.transactions(.read)`;
│      `POST /Invoices` needs `accounting.transactions`. A token with only
│      `.read` will succeed on reads and fail on writes - a very common
│      "works in dev, fails in prod" shape when dev only reads.
│   2. Scope-narrowing check: refresh must request a scope set that is
│      **equal to or a subset of** the scopes granted at consent time. Asking
│      for more at refresh time is a classic cause of a 403 that appears only
│      after the first refresh.
│   3. Tenant/header check: is `Xero-tenant-id` present, and does it match a
│      `tenantId` from `/connections` *for this token*? A tenant id copied from
│      another connection or another environment yields 403 (or 404), never a
│      silent cross-tenant read.
│   4. User-level permission check: the authorised Xero user may have a role that
│      cannot touch invoices. Verify by hitting the same endpoint with a known
│      user in the Xero UI.
│   5. Application-level check: whether the app has been granted the required
│      access for that product line/region.
│   Fix: re-consent with the correct scope set, or map the tenant to the right
│   connection. Do **not** retry.
│
└─ 404 Not Found ────────────────────────────────────────────────────────────────
    Auth and authorisation are fine; the *resource reference* is wrong.
    1. Path/version: is the base path the documented one
       (`/api.xro/2.0/Invoices`)? A typo in the version segment 404s everywhere.
    2. Cross-environment id: an `InvoiceID` created in demo does not exist in
       production. If ids are seeded or shared between environments this shows up
       as "401/403 fine, 404 on read".
    3. Cross-tenant id: an `InvoiceID` from organisation A requested with
       organisation B's tenant header.
    4. Identifier confusion: `InvoiceID` (GUID) vs `InvoiceNumber` (human
       reference) used in the wrong slot.
    5. The record was deleted/voided and hard-removed, or the search filter
       (`where=...`) is malformed and matches nothing - filters in particular can
       look like a 404 when the escaping of quotes is wrong.
    Fix: correct the identifier/route; re-resolve by `InvoiceNumber` within the
    correct tenant. Do **not** retry.
```

**Environment configuration as a first-class cause.** Because demo, sandbox and
production are different organisations, the pair
`(client_id, client_secret, refresh_token, tenantId)` must be stored **and resolved
together, per environment**. The most common cross-environment failure is a worker
that reads the *token* from environment A's secret and the *tenant id* from
environment B's database row. The mitigation is to treat environment as part of
the connection's primary key and to fail fast at startup if a connection's stored
tenant id is not returned by `/connections` for its own token.

---

## C3 - Incremental synchronisation for a large organisation

### Cursor model

One cursor row per `(tenantId, resource)` - never a global cursor:

```
sync_cursor(
  tenant_id, resource,            -- PK
  watermark_utc,                  -- last fully-applied UpdatedDateUTC
  page,                           -- in-flight page for resumability
  run_id,                         -- current/advisory lock holder
  last_success_at, last_error
)
```

### First run (backfill)

No watermark yet: ignore `If-Modified-Since` and walk from page 1. When the walk
completes, set `watermark_utc = run_started_at` - **the time the run started, not
the time it finished**. Using the finish time would silently skip every record
modified while the backfill was running.

### Steady state

* Request `GET /Invoices` with `If-Modified-Since: <watermark - lookback>` (or an
  equivalent `where=UpdatedDateUTC > DateTime(...)` filter if the endpoint/plan
  requires it) and paginate until a short/empty page.
* **Overlap window:** subtract a lookback (e.g. 15 minutes) from the watermark on
  every request. Xero timestamps are second-granular and a write can commit just
  before a read; the lookback trades a few redundant rows for correctness.
* **Cursor advance is part of the commit, not part of the read.** A page's rows
  are upserted and `watermark/page` moved in the *same database transaction*.
  If the process dies mid-page, the cursor still points at that page and the rerun
  re-reads it - which is safe because the write is an idempotent upsert.
* `watermark_utc` advances to the maximum `UpdatedDateUTC` actually observed
  (never to "now"), so a record that arrives late but carries an older timestamp
  is still picked up by the lookback rather than skipped forever.

### Pagination and large organisations

* Page sequentially (documented `page` parameter, 100 records per page); never
  fan out parallel page requests, because paging is a window over a mutating
  collection and parallelising it produces duplicates and gaps.
* Rate limiting is shared with other tenants (see C4), so a large backfill is
  scheduled as a low-priority queue with a per-page budget rather than a tight
  loop.
* Shard the *work*, not the *cursor*: multiple workers may not advance the same
  tenant's cursor concurrently. Enforce that with an advisory lock or a
  compare-and-set on `run_id`.

### Duplicates

* Upsert keyed on Xero's stable `InvoiceID` (GUID). `InvoiceNumber` is unique per
  tenant but is a human identifier and is used only as a secondary lookup key.
* Guard with the timestamp: if the local copy's `updated_date_utc >= incoming`,
  skip the write. This makes re-reading an overlapping window a no-op.
* Key everything by `(tenant_id, invoice_id)`. The same `InvoiceNumber` in two
  organisations is two different invoices.

### Change windows vs deletions

Xero does not emit delete events for invoices. A record that disappears from the
modified window has **not** necessarily been deleted, so absence must never be
interpreted as deletion. Voided/deleted documents remain visible with a
`Status` of `VOIDED`/`DELETED`; reconciliation is driven by status plus a
periodic (e.g. weekly, out-of-band) full-key comparison rather than by diffing the
incremental stream.

### Partial failure and safe replay

* Failure semantics: abort the run, do **not** advance the cursor, surface the
  error with the `run_id` and the failed page number. The next run resumes from
  the persisted page.
* Replay safety comes from idempotent upserts + the timestamp guard, so "at least
  once" delivery is enough and no distributed transaction is needed.
* Long backfills are checkpointed per page so a restart never begins from zero.

---

## C4 - Rate limits

**Headers to read.** `429 Too Many Requests` is accompanied by a `Retry-After`
value and indicators of which budget was exhausted (minute/day/app-minute).
The worker's rate-limit module:

1. Parses `Retry-After` (seconds or HTTP-date) as the authoritative *when may I
   try again* signal.
2. Parses whichever remaining-budget headers are present and updates an adaptive
   token bucket for that tenant. If no header is present, it falls back to a
   conservative default rate rather than bursting.

**Backoff and jitter.**

```
delay = max(Retry-After, base * 2**attempt)   # base ~ 0.5s
sleep = random.uniform(0, delay)              # full jitter
```

Full jitter (not fixed backoff) matters because the limiter is shared: without it,
every worker that received a 429 wakes at the same instant and re-triggers the
limit. `Retry-After` is treated as a floor, never as something to shorten.

**Concurrency limits.**

* A per-tenant semaphore plus the adaptive token bucket, so one large organisation
  cannot consume the application-wide budget.
* The bucket is *derived from the remaining headers*: if only 20% of the minute
  budget is left and the window is 30 seconds old, the worker's rate is scaled
  down for the rest of that window instead of being rediscovered via 429s.
* Workers hold no in-process state that matters, so horizontal scaling does not
  multiply the budget accidentally - the bucket lives in the shared store.

**Retry budgets and job scheduling.**

* Per call: at most ~5 attempts and a total wall-clock cap (e.g. 2 minutes).
* Per run: a retry budget so a systematically throttled tenant cannot starve the
  queue; when exhausted, the job is rescheduled rather than retried inline.
* Do **not** sleep inside a request handler. On 429, requeue the job with
  `run_at = now + Retry-After` and release the worker. This keeps throughput on
  other tenants unaffected.
* A per-tenant circuit breaker opens after a sustained 429 rate and pauses that
  tenant's queue (with an alert) instead of burning the shared budget.
* Batching (up to the documented per-request record limit on writes) reduces the
  number of calls in the first place, which is the cheapest rate-limit strategy.

**Errors that must NOT be retried**

| Status | Why |
| --- | --- |
| `400` | Malformed request/payload - deterministic, will fail again. |
| `401` after a successful refresh | Credentials/token genuinely bad; retrying hammers the identity server. Escalate to re-consent. |
| `403` | Missing scope/permission - a *configuration* fix, not a transient one. |
| `404` | Wrong resource/tenant/identifier. |
| `409` / business-validation errors | Deterministic conflict (e.g. duplicate invoice number) - needs reconciliation, not repetition. |

**Errors that ARE retried:** `429`, `500`/`502`/`503`/`504`, connection resets and
read timeouts - the latter only for requests that are safe to repeat, i.e. reads,
or writes carrying an idempotency/reference key (C5).

---

## C5 - Data integrity: retries that create invoices

The dangerous case is a write whose **result is unknown**: the request timed out,
but Xero may have committed it. Blindly retrying produces duplicate invoices.

### Preventing duplicates

1. **Deterministic idempotency key.** For each internal order, derive
   `idempotency_key = sha256("xero:invoice:" + tenant_id + ":" + order_id)`. It is
   stable across retries and across workers.
2. **Claim before you call.** Insert a row
   `invoice_attempt(tenant_id, order_id, idempotency_key, state='IN_FLIGHT',
   invoice_number, xero_invoice_id, created_at, updated_at)` **and commit**, before
   the HTTP request. A unique constraint on
   `(tenant_id, idempotency_key)` means exactly one worker can be in flight per
   order; a second worker fails the insert and defers instead of sending.
3. **Deterministic `InvoiceNumber`.** Generate the invoice number from the internal
   order id and send it on every attempt. Xero rejects a duplicate invoice number
   within a tenant, which is the server-side second line of defence - the retry
   cannot create a second document even if our own state is lost.
4. **Carry a searchable correlation value.** Put the internal order id in
   `Reference` (and/or a reference in `LineItem`), so the document can always be
   found again by a field we control.
5. **Never auto-retry an unknown write immediately.** `IN_FLIGHT` + timeout moves
   the attempt to `UNKNOWN` and hands it to the reconciler below, rather than
   sending a second POST.

### Reconciling "request succeeded but the response was lost"

```
attempt is UNKNOWN
  │
  ├─ GET /Invoices?where=InvoiceNumber=="<number>"   (or by Reference)
  │     └─ found  → state = SUCCEEDED, store xero_invoice_id   ✔ no duplicate
  │
  ├─ not found, and the attempt is older than the read-after-write window
  │     └─ re-POST **the same InvoiceNumber** with the same idempotency key
  │          ├─ 200 → SUCCEEDED
  │          └─ duplicate-number error → re-resolve by number → SUCCEEDED
  │
  └─ not found, still inside the window
        └─ wait and re-check (bounded, with backoff); never escalate to a
           different InvoiceNumber
```

Key points:

* The reconciliation query is keyed on values **we** generated, so it does not
  depend on having captured Xero's GUID.
* Voided/deleted invoices are excluded from "found" only after checking `Status`,
  and a voided invoice is treated as a business exception requiring operator
  attention - not as permission to create a fresh one.
* A sweeper job runs every few minutes over `state IN ('IN_FLIGHT','UNKNOWN')`
  older than a threshold, so a worker crash cannot leave an order permanently
  ambiguous.
* A nightly reconciliation compares internal orders that should be invoiced
  against Xero by `InvoiceNumber` and reports mismatches (missing, duplicated,
  amount/quantity drift) - this is the safety net that catches whatever the
  per-attempt logic misses.

---

## C6 - Observability and security

### Structured logs (JSON, one event per line)

Every line carries `trace_id`, `tenant_id` (or a pseudonymous hash),
`sync_run_id`, `event_id`, `attempt`, and where relevant `xero_invoice_id`.
Logged fields:

* `xero.http.request` - endpoint template (no query string with filters),
  method, `status`, Xero error `code`/`message`, duration, `attempt`,
  `retry_after`, remaining-budget headers.
* `xero.sync.page` - resource, page number, records returned, cursor before/after.
* `xero.sync.run` - outcome, records processed, duration, cursor lag at start/end.
* `xero.auth.refresh` - outcome only, plus new token `expires_at` (never the token).
* `xero.invoice.attempt` - internal order id, state transition, resulting invoice
  number; **not** the response body.

### Metrics

| Metric | Type | Purpose |
| --- | --- | --- |
| `xero_http_requests_total{endpoint,status}` | counter | detect 4xx/5xx shifts |
| `xero_http_request_duration_seconds{endpoint}` | histogram | latency, timeouts |
| `xero_rate_limit_remaining{tenant,window}` | gauge | headroom before 429s |
| `xero_429_total{tenant}` | counter | throttling pressure |
| `xero_retry_attempts_total{endpoint,outcome}` | counter | retry storms |
| `sync_runs_total{tenant,outcome}` | counter | success/failure ratio |
| `sync_cursor_lag_seconds{tenant,resource}` | gauge | freshness / staleness |
| `invoice_attempts_unknown{tenant}` | gauge | duplicate-invoice risk |
| `invoice_reconciliation_mismatches` | gauge | integrity drift |

### Alerts

* `401`/`403` spike or any `invalid_grant` → **page** (revenue-impacting, and it
  never self-heals).
* `sync_cursor_lag_seconds` above the tenant's SLO → page/ticket by tier.
* Circuit breaker open / sustained 429 for one tenant → ticket (fairness problem).
* `invoice_attempts_unknown > 0` older than the reconciliation threshold → page
  (possible duplicate invoices).
* Any reconciliation mismatch > 0 → ticket with a per-order drill-down.
* `Retry-After` climbing while 429 counts fall (i.e. we are self-throttling) →
  informational, avoids alert fatigue.

### Correlation identifiers

`trace_id` (one per run, propagated to Xero via a custom request header and stored
on every local record touched), `sync_run_id`, `event_id` (idempotency key),
`tenant_id`, and the Xero `InvoiceID`. Together these let one internal order be
traced from the internal event through every Xero call and back.

### What must never be logged

* Access tokens, refresh tokens, `Authorization` headers, client secrets.
* Token-endpoint request/response bodies (they contain tokens by definition).
* Full Xero request/response bodies, because invoice payloads contain customer
  PII - names, addresses, emails, phone numbers, bank account numbers, tax ids.
* Signed URLs, session cookies, OAuth `code` and `state` values.
* Free-text fields that operators might paste secrets into.

Where an identifier must appear for tracing, log a truncated or hashed form
(e.g. `sha256(tenant_id)[:12]`), and add a redaction layer in the HTTP client so a
header or body can never reach a logger by accident.

### Secret storage and rotation

* **At rest:** refresh tokens (and any per-tenant credential) are encrypted with
  envelope encryption - a KMS/HSM data key per tenant, ciphertext in the database,
  key material never in the database. Client secrets live in a managed secret
  manager, injected at runtime; never in Git, never in images, never in plaintext
  columns or backups.
* **In transit:** tokens only ever sent to `identity.xero.com` / `api.xero.com`
  over TLS, with certificate validation enabled.
* **Access:** least privilege - only the sync service's identity can decrypt; every
  decrypt is audited; no secret is ever returned by an API or rendered in admin UI.
* **Refresh-token rotation:** Xero rotates the refresh token on every refresh, so
  the flow is *persist-then-use*: write the new token durably before making any
  call with it, under a per-tenant lock so concurrent workers cannot both refresh
  and invalidate each other. A lost write here is what turns into `invalid_grant`.
* **Revocation/rotation of client secrets:** support overlapping validity, rotate on
  a schedule and on suspicion, and keep a runbook for the "revoked by customer"
  path (mark the connection `NEEDS_RECONSENT`, stop retrying, notify the account
  owner).
* **Blast radius:** each environment (demo/sandbox/production) has its own app
  credentials and its own tenant ids, so a leaked demo secret cannot touch real
  books.
