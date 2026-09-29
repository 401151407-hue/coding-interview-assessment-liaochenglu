# Task A - Analysis

## State model

| Field | Meaning |
| --- | --- |
| `on_hand` | Physical units owned by the ledger. |
| `reserved` | Sum of the per-order holds. Always `<= on_hand` because `SHIP` decrements both. |
| `held_by_order : Dict[order_id, qty]` | Outstanding reservation per order; entries are removed when they reach `0`. |
| `processed_events : Set[event_id]` | Idempotency guard. |

`available` is **derived**, not stored: `available = on_hand - reserved`. Storing it
would create a second source of truth that can drift.

## State transitions

| Command | Precondition | Effect |
| --- | --- | --- |
| `RESERVE e o q` | `q <= on_hand - reserved` | `held[o] += q`, `reserved += q` |
| `RELEASE e o q` | `q <= held[o]` | `held[o] -= q`, `reserved -= q` |
| `SHIP e o q` | `q <= held[o]` | `held[o] -= q`, `reserved -= q`, `on_hand -= q` |
| `RESTOCK e q` | always | `on_hand += q` |

Invariant maintained by every transition: `0 <= reserved <= on_hand`.

* `RESERVE` never increases `reserved` beyond `available`, so `reserved <= on_hand`
  is preserved.
* `SHIP` decreases `on_hand` and `reserved` by the same amount, preserving the
  difference.
* `RESTOCK` only increases `on_hand`, loosening the invariant.

## Idempotency

`event_id` is the idempotency key. The check happens **before** any business rule
is evaluated, so a replayed event never re-executes its side effects.

The subtle requirement is that a *business* rejection also marks the event as
processed. In the sample input:

```
RESERVE e2 o200 7   -> REJECTED (only 6 available)
...
RESERVE e2 9999 1   -> DUPLICATE, not a second REJECTED
```

Implementation order inside `apply`:

1. Parse. On failure emit `REJECTED` and **do not** record the event.
2. `event_id in processed_events` -> `DUPLICATE`.
3. Execute; record the event regardless of the outcome; emit `OK` or `REJECTED`.

**Documented assumption.** A malformed line is a syntax error rather than a
business operation, so it is not registered in `processed_events` (the line may
not carry a meaningful event id at all). A well-formed command that is rejected
by a business rule *is* registered. This is the reading that keeps "a rejected
business operation is still considered processed" honest while keeping malformed
input free of side effects - including idempotency side effects.

**Documented assumption.** Whitespace-only lines are skipped and do not consume
one of the declared `N` command slots; a line that has content but is not a valid
command is reported as `REJECTED`.

## Atomicity of rejection

`_parse_command` validates the entire line - opcode, arity, ASCII identifiers and
a strictly positive integer quantity - before `_execute` is reached. There is
therefore no code path that mutates one counter and then discovers a formatting
problem. Invalid input cannot produce partial state.

## Complexity

Let `N` be the number of commands and `R` the number of distinct orders.

| Phase | Time | Space |
| --- | --- | --- |
| Per command | `O(len(line))` for splitting + `O(1)` hash operations | `O(1)` amortised |
| Total | `O(total input size)`, i.e. `O(N)` for fixed-width tokens | `O(N)` - `processed_events` and `held_by_order` both grow with input |
| Report | `O(R log R)` for the `order_id` sort | `O(R)` |

`O(N)` is the best possible here: every command must be read once. The output is
accumulated in a list and written with a single `write` call, which matters at
`N = 200,000` where per-line `print` calls dominate the runtime in CPython.

Integer size: `S`, `qty` and their sums reach `10^12` and `N * qty` can reach
`2 * 10^17`. Python integers are arbitrary precision, so no overflow handling is
required (`int64` would be *almost* enough but is not relied upon).

## Edge cases covered by the test suite

* The worked example from the brief.
* Reserve exactly at the availability boundary, then one unit over.
* `RELEASE`/`SHIP` above, equal to, and below the held quantity.
* `SHIP`/`RELEASE` for an order with no reservation.
* Replay of successful, business-rejected and malformed events.
* Non-positive, non-numeric, negative and float quantities.
* Unknown opcodes, wrong arity, extra whitespace, blank lines.
* Large input (`N = 200,000`) for a performance guard.
