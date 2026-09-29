# Task B - Analysis

## Why a subset search is not enough

`W <= 30` looks small, but the number of subsets is `2^30`; even fixing the size
to the minimum `K` gives `C(30, K)`, whose maximum (`K = 15`) is ~155 million
subsets. For each subset you would still have to solve the inner allocation, so a
brute force is out by orders of magnitude. The brief says as much explicitly.

## Reducing the three objectives to one DP

**Objective 1 (fewest warehouses) is solvable in closed form.** A set of `k`
warehouses can hold at most the sum of the `k` largest stocks, so the minimum
feasible `K` is found by sorting stocks descending and taking a prefix sum until
it reaches `Q`. No search is required, and it costs `O(W log W)`.

**Objective 2 (minimum cost with exactly `K` used)** is the real optimisation:

```
minimise  sum over used i of (fixed_i + x_i * unit_i)
subject to  sum x_i = Q,  1 <= x_i <= stock_i,  exactly K warehouses have x_i > 0
```

Note the "exactly `K`" part is what stops the naive greedy ("take the cheapest
units") from being correct: using a warehouse at all costs its fixed cost, and
the number of warehouses used is a *hard* constraint, not a soft penalty.

**Objective 3 (lexicographic tie-break)** cannot be folded into the cost (many
different allocations have the same minimal cost), so it is handled during
reconstruction - see below.

## State representation

```
layers[i][used][q] = minimum cost to allocate exactly q units
                     using exactly `used` of warehouses[i:]
```

* `used` ranges over `0..K`.
* `q` ranges over `0..Q`.
* `INF` marks unreachable states.
* Base case: `layers[W][0][0] = 0`, everything else `INF`.

## Transition and the sliding-window trick

For warehouse `i` you either skip it or use it with some `x >= 1`:

```
layers[i][used][q] = min(
    layers[i+1][used][q],                                  # skip
    fixed_i + min_{q' in [q - stock_i, q - 1]} (            # use
        layers[i+1][used-1][q'] + (q - q') * unit_i
    )
)
```

The naive inner loop is `O(stock_i)` per state, giving
`O(W * K * Q * max_stock)` = 30 x 30 x 2000 x 2000, far too slow.

Rewriting the inner term as

```
fixed_i + q * unit_i + (layers[i+1][used-1][q'] - q' * unit_i)
```

shows that the minimisation is over a **sliding window of fixed width
`stock_i`** on the quantity `layers[i+1][used-1][q'] - q' * unit_i`. A monotonic
deque evaluates every window minimum in amortised `O(1)`, so one `(i, used)`
pair costs `O(Q)`.

## Tie-breaking strategy

All three objectives are satisfied in sequence:

1. `K` from the closed-form prefix sum.
2. `C = layers[0][K][Q]` - the cost optimum for exactly `K` warehouses.
3. Reconstruction walks *forward* through the warehouses in ascending
   `warehouse_id`:

   * pick the **smallest** index `i` (larger than the previous choice) for which
     some quantity `x` can still complete a `K`-warehouse, cost-`C` solution.
     Choosing the smallest possible next id is what makes the sorted allocation
     list lexicographically smallest - any solution that skipped `i` would have a
     larger id at this position.
   * then pick the **smallest** feasible `x`, because within the same id a smaller
     quantity makes the entry `(id, x)` lexicographically smaller.

   Feasibility of "use `i` with `x`" is exactly
   `spent + fixed_i + x * unit_i + layers[i+1][K-1-...][Q-...] == C`, which is
   `O(1)` per candidate thanks to the suffix DP.

This is why the algorithm returns the lexicographic minimum rather than merely
*some* optimal split - verified by the exhaustive differential test in
`tests/test_solution.py` (400 random cases plus hand-picked lexicographic traps).

## Complexity

| Quantity | Value |
| --- | --- |
| Time | `O(W log W + W * K * Q)` |
| Space | `O(W * K * Q)` |
| Worst case (`W = 30, K = 30, Q = 2000`) | ~1.8M DP cells, ~31 MB of Python ints |

The measured runtime for the largest input shape (`W = 30`, `Q = 2000`, all 30
warehouses required) is well under a second on a laptop, versus the "will not
pass" brute force.

Memory could be halved by keeping only the two most recent layers during the
forward pass, but reconstruction needs every layer, so the full table is kept.
`array('q')` (64-bit) would cut it further; plain lists were chosen for clarity
and are comfortably within budget.

## Assumptions and decisions

* `warehouse_id` values are unique and compared as plain strings, so ordering is
  byte-lexicographic (`"AU" < "CN" < "US"`). The brief's `order_id`-style sort
  semantics are the same as Python's default string ordering.
* "Allocation list ... sorted by warehouse_id" is interpreted as a tuple
  comparison over `(warehouse_id, quantity)` pairs. Since every optimal solution
  uses the same number of warehouses, the lists being compared always have equal
  length, so tuple comparison is well defined.
* A warehouse with `allocated_qty = 0` is not "used" and contributes no fixed
  cost; `stock = 0` warehouses can therefore never appear in a solution.
* `Q = 0` is accepted and produces `0 0` (no warehouses, no cost). The brief's
  constraint is `Q >= 1`, but the degenerate case is handled rather than
  crashing.
* Costs fit comfortably in `int64` (`<= 2.03e9`), but plain Python integers are
  used so overflow is not a concern.

## Test coverage

* The worked example, plus execution from `sample_input.txt`.
* Each objective in isolation, including a case where the fewest-warehouse rule
  beats a cheaper-per-unit split.
* Three separate lexicographic tie-break scenarios (first quantity, first id,
  three-way spread).
* Impossible orders (`-1`), zero-stock warehouses, `Q = 0`, exact fits and
  maximum magnitudes.
* Parser rejection of malformed headers, missing/extruded rows and duplicate ids.
* **Differential testing**: 400 randomised small cases compared against an
  exhaustive search that enumerates every subset *and* every allocation, plus
  five hand-picked lexicographic traps.
* Scale guards at the constraint boundary (`W = 30, Q = 2000`).
