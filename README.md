# Full-Stack Developer Coding Interview Assessment

Take-home exercise covering algorithms (Task A, Task B), API integration reasoning
(Task C) and end-to-end product engineering (a variant PDP backed by FastAPI and
React + TypeScript).

```
.
├── A/                Python solution + tests + complexity analysis
│   ├── solution.py
│   ├── sample_input.txt
│   ├── ANALYSIS.md
│   └── tests/test_solution.py
├── B/                Python solution + tests + complexity analysis
│   ├── solution.py
│   ├── sample_input.txt
│   ├── ANALYSIS.md
│   └── tests/test_solution.py
├── C/                Written answers (Markdown)
│   └── answers.md
├── app/              FastAPI backend + React/TypeScript frontend
│   ├── backend/
│   ├── frontend/
│   ├── run-dev.sh
│   └── run-dev.ps1
└── README.md
```

---

## Prerequisites

| Tool | Version used | Notes |
| --- | --- | --- |
| Python | 3.11.5 | 3.11+ required (`tuple[...]` annotations, FastAPI on 3.11) |
| Node.js | 24.19.0 | 18+ works for Vite 5 |
| npm | 11.17.0 | |

No database server, no external service and no network access are needed at
runtime: the catalogue is seeded in memory and product images are inline SVG data
URIs.

---

## Quick start

### Task A and Task B (no dependencies beyond the standard library)

```bash
python A/solution.py A/sample_input.txt     # or: python A/solution.py < input.txt
python B/solution.py B/sample_input.txt
```

`B/solution.py` uses only the standard library (`collections.deque`). No external
optimisation solver is used.

### Backend

```bash
python -m pip install -r app/backend/requirements.txt

cd app
python -m uvicorn backend.main:app --reload --port 8000
```

* API root: <http://127.0.0.1:8000>
* Generated OpenAPI docs: <http://127.0.0.1:8000/docs>
* Health probe: <http://127.0.0.1:8000/api/health>

### Frontend

```bash
cd app/frontend
npm install
npm run dev            # http://127.0.0.1:5173
```

Vite proxies `/api` to `http://127.0.0.1:8000`, so there is no CORS negotiation in
development and no API base URL to configure. Start the backend first.

### Both at once (optional convenience)

```bash
bash app/run-dev.sh                       # macOS / Linux
powershell -ExecutionPolicy Bypass -File app/run-dev.ps1   # Windows
```

---

## Running the tests

```bash
# Task A - 44 tests
python -m pytest A/tests -q

# Task B - 27 tests (includes a differential test against exhaustive search)
python -m pytest B/tests -q

# Backend API - 31 tests
cd app && python -m pytest backend/tests -q

# Frontend - 25 tests
cd app/frontend && npm test
```

All four suites are dependency-light and run without network access.
`npm run typecheck` (and `npm run build`) run `tsc --noEmit` with `strict: true`,
`noUnusedLocals`, `noUnusedParameters` and `noImplicitReturns` enabled, and the
project contains **no `any`** - not even an implicit one.

> If `python -m pytest app/backend/tests` fails at import time with
> `trio/_path.py ... assert wrapped.__doc__ is not None`, that is a broken `trio`
> install in the interpreter (it is imported unconditionally by `httpcore`, which
> `httpx` - and therefore Starlette's `TestClient` - depends on). It is unrelated
> to this repository. Fix it with
> `python -m pip install --upgrade --force-reinstall trio`, or remove `trio` if
> nothing else uses it.

---

## Task A - Inventory Reservation Ledger

A deterministic single-SKU command processor with idempotent events.

**State:** `on_hand`, `reserved`, per-order holds, and a set of processed
`event_id`s. `available = on_hand - reserved` is derived, never stored.

**Key behaviours**

* `RESERVE` succeeds only when `qty <= available`; `RELEASE`/`SHIP` cannot exceed
  the order's current hold; `SHIP` decrements `on_hand` *and* the hold together,
  preserving `0 <= reserved <= on_hand` at every step.
* Every `event_id` is idempotent. Both **accepted** and **business-rejected**
  events are recorded as processed, so a replay returns `DUPLICATE`.
* Malformed lines are rejected atomically - parsing happens before any mutation -
  and are **not** recorded, because a malformed line is a syntax error rather than
  a business operation and may not carry a usable event id.
* Whitespace-only lines are skipped and do not consume one of the declared `N`
  command slots.
* Output is buffered and written with a single `write`, which is what keeps
  `N = 200,000` fast in CPython (measured well under a second).

**Complexity:** `O(N)` time, `O(N)` space, plus `O(R log R)` to sort the open
reservations by `order_id`.

Full details, including the reasoning behind each state transition and a list of
the covered edge cases, are in [`A/ANALYSIS.md`](A/ANALYSIS.md).

**Output format assumption.** The final block is

```
OPEN <number of open reservations>
<order_id> <qty>
...
```

The brief's example only exercises the empty case (`OPEN 0`), so the row format is
a documented reading of "print open reservations ordered by order_id".

---

## Task B - Fulfilment Split Optimiser

Three objectives, satisfied strictly in order: fewest warehouses, then lowest
total cost, then the lexicographically smallest allocation list sorted by
`warehouse_id`.

**Approach**

1. The minimum warehouse count `K` is closed-form: the sum of the `K` largest
   stocks is the most any `K` warehouses can hold, so `K` is the first prefix sum
   (descending) that reaches `Q`.
2. A suffix DP `layers[i][used][q] = minimum cost to allocate q units using
   exactly `used` of `warehouses[i:]``, where the "use this warehouse" transition
   is a **sliding-window minimum** evaluated in `O(Q)` with a monotonic deque:
   `fixed_i + q * unit_i + min_{q' in [q-stock_i, q-1]} (g[q'] - q' * unit_i)`.
3. Reconstruction walks forwards in `warehouse_id` order and repeatedly takes the
   smallest reachable id, then the smallest feasible quantity for that id. That is
   what produces the lexicographic minimum rather than merely *an* optimum.

**Complexity:** `O(W log W + W * K * Q)` time, `O(W * K * Q)` space. At the
constraint ceiling (`W = 30`, `K = 30`, `Q = 2000`) that is ~1.8M DP cells and
runs in well under a second - versus ~155 million subsets for a brute force over
fixed-size subsets.

**Correctness evidence:** `B/tests/test_solution.py` includes a differential test
that compares the DP against an exhaustive search over every subset *and* every
allocation for 400 random small cases, plus hand-picked lexicographic traps.

Full reasoning, state representation and tie-breaking strategy:
[`B/ANALYSIS.md`](B/ANALYSIS.md).

**Assumptions.** `warehouse_id` values are unique and compared as plain strings;
"lexicographically smallest allocation list" is a tuple comparison over
`(warehouse_id, qty)` pairs (every optimal solution uses the same number of
warehouses, so the compared lists have equal length); `Q = 0` is accepted and
yields `0 0` even though the stated constraint is `Q >= 1`.

---

## Task C - Xero Integration Review

See [`C/answers.md`](C/answers.md) for the full written answers:

| Section | Topic |
| --- | --- |
| C1 | Minimum call sequence that proves OAuth, token audience, tenant selection and invoice scope |
| C2 | Diagnostic decision tree for 401 / 403 / 404, including scope narrowing and environment mixing |
| C3 | Resumable incremental invoice sync: cursors, lookback windows, paging, duplicates, partial failure |
| C4 | HTTP 429: `Retry-After`, full-jitter backoff, adaptive budgets, retry/no-retry matrix |
| C5 | Duplicate-invoice prevention and reconciliation when a write's result is unknown |
| C6 | Logs, metrics, alerts, correlation ids, redaction, secret storage and rotation |

The document states its SDK/API assumptions and links the Xero developer
documentation pages relied on. Because `developer.xero.com` renders client-side,
those pages are used as authoritative entry points, and anything version-sensitive
(headers, limits) is designed to be **read from the response at runtime** rather
than hard-coded.

---

## The app - Variant PDP

One product with two option dimensions, seven SKUs, an unavailable combination
(`Sand / M` has no SKU) and an out-of-stock SKU (`Black / M` is at 0).

### Architecture

```
app/frontend                        app/backend
┌──────────────────────────┐        ┌───────────────────────────────────┐
│ pages/ProductDetailPage  │  HTTP  │ main.py       routes + handlers    │
│   ↕ hooks & local state  │ ─────▶ │ serializers.py wire format         │
│ domain/variants.ts       │        │ store.py      cart + idempotency   │
│   pure variant resolution│        │ catalog.py    seed data (7 SKUs)   │
│ api/client.ts  (PdpApi)  │        │ errors.py     structured envelope  │
│   injected via context   │        └───────────────────────────────────┘
└──────────────────────────┘
```

Concerns are separated on both sides:

* **API layer** - `api/client.ts` is the only module that calls `fetch`, and it
  exposes a `PdpApi` interface. Components receive it through React context, so
  tests inject an in-memory fake instead of stubbing globals.
* **Domain layer** - `domain/variants.ts` is pure TypeScript with no React import:
  variant resolution, option-value availability and quantity clamping are unit
  tested directly.
* **UI layer** - components render props and raise events; they hold no business
  rules.
* On the backend the same split is `catalog` (data) / `store` (behaviour) /
  `serializers` (wire format) / `main` (transport).

### API contract

Base URL in development: `http://127.0.0.1:8000` (proxied by Vite at `/api`).
All money values are integer **cents**; `availableQuantity` is always computed
server-side and reflects units already held by the cart.

#### `GET /api/products/{id}`

Returns the product, its option dimensions and every SKU.

`200 OK`

```json
{
  "id": "aurora-merino-tee",
  "name": "Aurora Merino Tee",
  "description": "A lightweight 180 gsm merino tee ...",
  "currency": "USD",
  "options": [
    {
      "id": "color",
      "label": "Colour",
      "values": [
        { "id": "black", "label": "Black", "swatch": "#1f2937" },
        { "id": "white", "label": "White", "swatch": "#e5e7eb" },
        { "id": "sand",  "label": "Sand",  "swatch": "#d9c4a3" }
      ]
    },
    {
      "id": "size",
      "label": "Size",
      "values": [
        { "id": "s", "label": "S", "swatch": "#94a3b8" },
        { "id": "m", "label": "M", "swatch": "#94a3b8" },
        { "id": "l", "label": "L", "swatch": "#94a3b8" }
      ]
    }
  ],
  "skus": [
    {
      "id": "aurora-merino-tee-black-m",
      "name": "Aurora Merino Tee - Black / M",
      "options": { "color": "black", "size": "m" },
      "priceCents": 2900,
      "currency": "USD",
      "availableQuantity": 0,
      "image": "data:image/svg+xml;charset=utf-8,..."
    }
  ]
}
```

`404` - `PRODUCT_NOT_FOUND`.

#### `POST /api/cart/items`

Adds units of one SKU. **Requires an `Idempotency-Key` header.** Price and stock
are read from the server catalogue; anything the client sends about price or stock
is rejected by validation rather than ignored.

Request headers: `Content-Type: application/json`, `Idempotency-Key: <opaque>`

```json
{ "skuId": "aurora-merino-tee-black-s", "quantity": 2 }
```

`201 Created`

```json
{
  "cart": {
    "items": [
      {
        "skuId": "aurora-merino-tee-black-s",
        "productId": "aurora-merino-tee",
        "name": "Aurora Merino Tee - Black / S",
        "options": { "color": "black", "size": "s" },
        "image": "data:image/svg+xml;charset=utf-8,...",
        "unitPriceCents": 2900,
        "quantity": 2,
        "lineTotalCents": 5800
      }
    ],
    "totalQuantity": 2,
    "totalPriceCents": 5800
  },
  "sku": {
    "id": "aurora-merino-tee-black-s",
    "productId": "aurora-merino-tee",
    "availableQuantity": 3
  }
}
```

The nested `sku.availableQuantity` is what lets the UI converge on the true stock
without refetching the product.

#### `GET /api/cart`

`200 OK`

```json
{
  "items": [
    {
      "skuId": "aurora-merino-tee-black-s",
      "productId": "aurora-merino-tee",
      "name": "Aurora Merino Tee - Black / S",
      "options": { "color": "black", "size": "s" },
      "image": "data:image/svg+xml;charset=utf-8,...",
      "unitPriceCents": 2900,
      "quantity": 2,
      "lineTotalCents": 5800
    }
  ],
  "totalQuantity": 2,
  "totalPriceCents": 5800
}
```

#### Error envelope

Every failure - including framework-generated ones such as 404/405 and payload
validation - uses the same shape:

```json
{
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "Only 1 unit(s) of 'aurora-merino-tee-black-s' remain, but 2 were requested.",
    "details": { "skuId": "aurora-merino-tee-black-s", "requested": 2, "available": 1 }
  }
}
```

#### Status code summary

| Status | `code` | When |
| --- | --- | --- |
| `200` | - | `GET /api/products/{id}`, `GET /api/cart` |
| `201` | - | Item added. Also returned on an idempotent **replay** of the original request. |
| `400` | `MISSING_IDEMPOTENCY_KEY` | Header missing or blank |
| `404` | `PRODUCT_NOT_FOUND` | Unknown product id |
| `404` | `SKU_NOT_FOUND` | Unknown SKU id |
| `404` | `NOT_FOUND` | Unknown route |
| `409` | `INSUFFICIENT_STOCK` | Quantity exceeds the current server-side stock |
| `409` | `IDEMPOTENCY_KEY_REUSE` | Same key, different payload (`skuId` or `quantity`) |
| `422` | `VALIDATION_ERROR` | Malformed body, wrong types, `quantity` outside `1..99`, unknown fields |
| `500` | `INTERNAL_ERROR` | Unexpected server failure (details logged, never returned) |

#### Idempotency semantics

* The first request with a key is executed; its status and body are memoised.
* A repeat with the **same** key and the **same** payload replays that exact
  response and does not touch the cart again.
* A repeat with the same key and a **different** payload is `409`.
* Deterministic failures (including `409 INSUFFICIENT_STOCK`) are memoised too, so
  the same key always yields the same answer. The frontend therefore generates a
  **new key per attempt**, not per session.
* Keys are not persisted across restarts; a restart clears the cart. See
  *Known limitations*.

#### Concurrency / no overselling

`Store.add_to_cart` performs the whole check-then-write under one
`threading.Lock`. Two requests racing for the last units **cannot** both succeed;
one gets `201` and the other `409`. Two tests reproduce this with real OS threads
(one through HTTP, one directly against the store).

---

## Frontend behaviour

### Variant resolution

`domain/variants.ts` answers three questions, each unit tested:

* `resolveSku(product, selection)` - the single SKU for a **complete** selection.
* `optionValueState(product, selection, optionId, valueId)` -
  `available` / `out-of-stock` / `unavailable`, evaluated against the *other*
  dimensions only. Judging a value against its own dimension would make an
  impossible combination look valid.
* `applySelection(...)` - records a choice and clears any choice in another
  dimension that the new value makes impossible.

Presentation rules that follow from that:

* **`unavailable`** (no SKU exists, e.g. Sand + M) - the radio is disabled and
  announced as "not available with the current selection".
* **`out-of-stock`** (a SKU exists but is at 0, e.g. Black + M) - the radio stays
  **selectable** so the sold-out state is reachable and explainable, is labelled
  "Sold out", and add-to-bag is disabled.

### Required states

| State | How it is expressed |
| --- | --- |
| Initial loading | Skeleton + `role="status"` "Loading product…" |
| Retryable load error | `role="alert"` panel with a **Try again** button that refetches |
| Incomplete selection | "Select colour and size to see price and stock", price shows `—`, button says "Select options" |
| Invalid combination | Radio disabled; if a selection is nonetheless incomplete/invalid, an inline notice explains it |
| Out-of-stock SKU | `Out of stock` badge, add-to-bag and quantity disabled |
| Add in progress | Button disabled + `aria-busy="true"` + label "Adding…" |
| Success | Polite `role="status"` region: "Added 2 × … to your bag", cart badge updates |
| Validation failure | Assertive `role="alert"` with the mapped message |
| Insufficient stock | Assertive alert + `availableQuantity` refreshed from the error's `details` |
| Server / network error | Assertive alert, UI stays usable and the selection is preserved |

### Resilient async behaviour

* **No stale UI.** Price, image, stock and the quantity clamp are all derived from
  the *resolved* SKU on every render.
* **No duplicate submission.** A `useRef` guard closes the window between the click
  and the re-render that disables the button, so two clicks in one tick produce
  exactly one request. A test fires two synchronous clicks and asserts one call.
* **Recovers without a page refresh.** A successful add carries the SKU's new
  availability; a `409` carries the real remaining quantity, which is applied as a
  local override. A load failure is recoverable via the retry button.
* **Bounded requests.** Every `fetch` has an `AbortController` timeout (8s) and a
  transport failure is surfaced as a retryable `NETWORK_ERROR`.

### Accessibility

* Native `<input type="radio">` inside `<fieldset>`/`<legend>` gives grouping,
  label association and arrow-key roving focus for free.
* The visible focus ring follows the *label* (`:focus-visible` on the hidden input
  styles the sibling label), so keyboard users can see where they are.
* Success/error feedback lives in live regions that are mounted from the start -
  AT only reliably announces changes inside a region that already existed.
* The add button's accessible name includes the resolved variant and quantity
  ("Add to bag Black / S, quantity 2").
* A skip link, semantic landmarks (`header`/`main`), `aria-busy` on the in-flight
  button, and `prefers-reduced-motion` support.
* Responsive from ~375px (single column, full-width button) to 1280px+ (two
  columns).

### Frontend tests (25)

`src/domain/variants.test.ts` (15) covers resolution, per-value availability in
both selection orders, `applySelection` clean-up and quantity clamping.

`src/pages/ProductDetailPage.test.tsx` (10) covers loading, SKU resolution without
stale values, disabled impossible combinations, sold-out-but-selectable SKUs,
quantity bounding, **duplicate-click suppression**, `409` handling with stock
refresh, transport failures, retryable load errors and per-attempt idempotency
keys.

### Analytics (optional extension)

`analytics/events.ts` defines a typed `view_item` / `select_item` / `add_to_cart`
event union and an injectable sink. The contract is documented in the file: only
shopping data, never identifiers, tokens or free text.

### Deliberate non-goals

Authentication, checkout, payment and production deployment are out of scope, as
is optimistic UI. The cart badge updates from the server response rather than
optimistically, because the server is the only authority on stock: "apply, then
roll back if it fails" would show a quantity the server never accepted. The
documented trade-off is one extra round trip for guaranteed consistency.

---

## Assumptions (all parts)

1. **Task A output rows.** `OPEN <count>` followed by one `<order_id> <qty>` line
   per open reservation; the brief only shows the empty case.
2. **Task A malformed input.** A syntax error is not "a rejected business
   operation", so it is neither applied nor recorded for idempotency.
3. **Task A blank lines.** Whitespace-only lines are skipped and do not consume a
   command slot.
4. **Task B ordering.** `warehouse_id` is compared as a plain string, and the
   allocation list is compared as a tuple sequence of `(id, qty)` pairs.
5. **Task C.** Token/limit header names and lifetimes are treated as
   runtime-probed configuration, not constants; the linked Xero documentation
   pages are the authoritative reference and their version assumptions are stated
   in `C/answers.md`.
6. **App cart model.** A single, session-less cart, matching "return current cart
   and total item count" in the brief. Storage is in memory.
7. **App idempotency.** `Idempotency-Key` is required (not merely accepted), since
   optional idempotency cannot guarantee "repeating the same request key must not
   add the item twice".
8. **App SKU ids.** A SKU id is globally unique and is carried to the client, so
   `POST /api/cart/items` needs no product id.
9. **Money.** Integer cents everywhere; formatting happens only in the UI.

---

## Known limitations

* **Storage is in memory.** Restarting the API resets the cart, the reserved
  quantities and the idempotency keys. The store's interface is written to be
  swapped for a database (conditional `UPDATE ... WHERE available >= :qty`, unique
  index on the idempotency key) without changing the HTTP contract.
* **The lock is process-local.** It prevents overselling within one process. Two
  API processes would need the database-level conditional update described above.
* **The idempotency table is unbounded.** There is no TTL/eviction, which would be
  required in production to stop the keys growing without limit.
* **A single cart, no sessions or users.** Adding a cart id is a mechanical change
  to `store.py` and the routes; nothing about the variant logic depends on it.
* **No pagination or search.** The catalogue is one product with seven SKUs.
* **Task C is a written design review, not a working Xero integration** - there are
  no credentials, no tokens and no live calls in this repository.
* **Task B's DP is tuned to the stated constraints.** `K` and `Q` bounds are 30 and
  2000; the memory footprint grows linearly with both.
* **Frontend bundle is un-split.** ~155 kB raw / ~50 kB gzipped, which is fine for
  one page but would want route-level code splitting in a larger app.

---

## AI assistance disclosure

In line with the assessment's AI policy, this disclosure covers how AI-assisted
tooling was used. Every file was reviewed, executed and is explainable, and the
test suites were run locally (see *Running the tests*).

**Where AI assistance was used**

* **Boilerplate and scaffolding** - repository layout, `package.json`/`tsconfig`
  defaults, and the CSS stylesheet.
* **Drafting prose** - the README and `C/answers.md` were drafted with assistance,
  then edited for accuracy against the design that is actually implemented.

**Where AI assistance was *not* trusted blindly**

* **Task A**: the transition table, the atomicity argument and the idempotency
  ordering (including the "a rejected business operation is still processed"
  rule) were derived from the brief, then pinned down by 44 tests including a
  200,000-command performance guard and a randomised invariant test.
* **Task B**: the sliding-window-minimum DP and the forward lexicographic
  reconstruction were derived and then **falsified against an exhaustive search**
  over every subset and every allocation for 400 random cases plus hand-picked
  tie-break traps. Several hand-written test expectations were themselves wrong
  and were corrected by the implementation, which is the point of that test.
* **Task C**: the answers are reasoned from the failure modes of the described
  system. Because the Xero documentation site is client-rendered, page bodies
  could not be quoted verbatim; the design therefore avoids hard-coding anything
  version-sensitive and states its assumptions explicitly instead.
* **Backend**: the structured error envelope, the idempotency semantics and the
  no-overselling lock were specified deliberately, and are verified by fault
  injection (duplicate keys, conflicting payloads, 404/409/422 paths) and by two
  real-thread race tests.
* **Frontend**: the domain rules live in a pure, dependency-free module that is
  unit tested independently of React, so the tricky "which values are disabled
  given the *other* dimensions" logic is verified by direct tests rather than by
  eyeballing rendered output.

No code was submitted that could not be explained, modified or debugged live.

---

## Submission checklist

- [x] Repository access verified - all four suites run from the documented commands
- [x] Setup commands tested against a real server (`uvicorn` smoke test: `GET`
      product → 200, `POST` cart → 201, `GET` cart totals)
- [x] Automated tests pass: A (44), B (27), backend (31), frontend (25)
- [x] `tsc --noEmit` clean under `strict`; no `any` in the codebase
- [x] Assumptions documented (this file, `A/ANALYSIS.md`, `B/ANALYSIS.md`,
      `C/answers.md`)
- [x] AI assistance disclosed (above)
- [x] No secrets, tokens, credentials or real customer data committed
