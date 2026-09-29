"""Task B - Fulfilment Split Optimiser.

Given ``W`` warehouses and a demand of ``Q`` units, pick the allocation that is
best under a strict, three level objective:

1. minimise the number of warehouses used,
2. then minimise total shipping cost
   (``sum(fixed_cost + allocated_qty * unit_cost)`` over used warehouses),
3. then pick the lexicographically smallest allocation list when the used
   warehouses are sorted by ``warehouse_id``.

Output: ``-1`` when the order cannot be fulfilled, otherwise
``<warehouse count> <total cost>`` followed by ``<warehouse_id> <qty>`` rows
sorted by ``warehouse_id``.

Approach
--------
A subset search is exponential (``C(30, 15)`` is ~1.5e8) and would not pass the
largest cases, so the problem is solved with a dynamic program over
``(suffix of warehouses, warehouses used, units allocated)``.

For a warehouse ``i`` the transition is

    use(i, used, q) = fixed_i + q * unit_i + min_{q' in [q - stock_i, q - 1]} (g[q'] - q' * unit_i)

which is a *sliding window minimum* and can be evaluated for every ``q`` in
``O(Q)`` with a monotonic deque. Total time is ``O(W * K * Q)`` and memory is
``O(W * K * Q)``, which is what makes ``W = 30, Q = 2000`` tractable.

Only standard library modules are used - no external optimisation solver.
"""

from __future__ import annotations

import sys
from collections import deque
from typing import Dict, List, NamedTuple, Optional, Sequence, TextIO, Tuple

#: Sentinel larger than any reachable cost. Max cost is bounded by
#: ``30 * 10^6 + 2000 * 10^6 = 2.03e9`` so 2^60 is comfortably out of reach.
INF: int = 1 << 60


class Warehouse(NamedTuple):
    id: str
    stock: int
    fixed_cost: int
    unit_cost: int


Allocation = List[Tuple[str, int]]
Plan = Tuple[int, Allocation]  # (total cost, allocation list)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def plan_fulfilment(
    warehouses: Sequence[Warehouse], quantity: int
) -> Optional[Plan]:
    """Return ``(total_cost, allocation)`` for the optimal split, or ``None``.

    The returned allocation is sorted by ``warehouse_id`` and only contains
    strictly positive quantities, so its length is the number of warehouses
    used.
    """
    if quantity < 0:
        raise ValueError("quantity must be non-negative")

    ordered = sorted(warehouses, key=lambda w: w.id)
    if quantity == 0:
        return 0, []

    if sum(w.stock for w in ordered) < quantity:
        return None

    # ---- Objective 1: fewest warehouses ---------------------------------
    # The most a set of `k` warehouses can hold is the sum of the `k` largest
    # stocks, so the minimum feasible `k` is found by a greedy prefix sum.
    max_warehouses = _minimum_warehouse_count(
        [w.stock for w in ordered], quantity
    )

    # ---- Objective 2: minimum cost with exactly `max_warehouses` used ----
    layers = _build_cost_layers(ordered, quantity, max_warehouses)
    total_cost = layers[0][max_warehouses][quantity]
    if total_cost >= INF:
        return None

    # ---- Objective 3: lexicographically smallest allocation --------------
    allocation = _reconstruct_lexicographic(
        ordered, layers, max_warehouses, quantity, total_cost
    )
    return total_cost, allocation


def format_plan(plan: Optional[Plan]) -> str:
    """Render a plan using the output format from the brief."""
    if plan is None:
        return "-1"
    total_cost, allocation = plan
    rows = [f"{len(allocation)} {total_cost}"]
    rows.extend(f"{warehouse_id} {qty}" for warehouse_id, qty in allocation)
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Objective helpers
# ---------------------------------------------------------------------------
def _minimum_warehouse_count(stocks: Sequence[int], quantity: int) -> int:
    covered = 0
    for count, stock in enumerate(sorted(stocks, reverse=True), start=1):
        covered += stock
        if covered >= quantity:
            return count
    raise ValueError("demand exceeds total stock")  # guarded by the caller


def _build_cost_layers(
    warehouses: Sequence[Warehouse], quantity: int, max_used: int
) -> List[List[List[int]]]:
    """Suffix DP.

    ``layers[i][used][q]`` is the cheapest way to allocate exactly ``q`` units
    using exactly ``used`` of ``warehouses[i:]`` (``INF`` when impossible).
    """
    count = len(warehouses)
    layers: List[List[List[int]]] = [None] * (count + 1)  # type: ignore[list-item]

    base: List[List[int]] = [
        [INF] * (quantity + 1) for _ in range(max_used + 1)
    ]
    base[0][0] = 0  # no warehouses left, nothing used, nothing allocated
    layers[count] = base

    for i in range(count - 1, -1, -1):
        _, stock, fixed_cost, unit_cost = warehouses[i]
        nxt = layers[i + 1]
        # Option "skip this warehouse" is the starting point for every state.
        cur = [row[:] for row in nxt]

        for used in range(1, max_used + 1):
            previous = nxt[used - 1]
            target = cur[used]
            window: "deque[Tuple[int, int]]" = deque()

            for q in range(quantity + 1):
                # Candidate predecessor quantities: q' in [q - stock, q - 1].
                q_prev = q - 1
                if q_prev >= 0:
                    base_cost = previous[q_prev]
                    if base_cost < INF:
                        score = base_cost - q_prev * unit_cost
                        while window and window[-1][1] >= score:
                            window.pop()
                        window.append((q_prev, score))

                lower_bound = q - stock
                while window and window[0][0] < lower_bound:
                    window.popleft()

                if window:
                    candidate = fixed_cost + q * unit_cost + window[0][1]
                    if candidate < target[q]:
                        target[q] = candidate

        layers[i] = cur

    return layers


def _reconstruct_lexicographic(
    warehouses: Sequence[Warehouse],
    layers: List[List[List[int]]],
    used_total: int,
    quantity: int,
    total_cost: int,
) -> Allocation:
    """Walk the DP forward, always taking the smallest possible next entry."""
    count = len(warehouses)
    allocation: Allocation = []
    remaining_used = used_total
    remaining_qty = quantity
    spent = 0
    previous_index = -1

    while remaining_used > 0:
        chosen: Optional[Tuple[int, Warehouse, int]] = None

        for i in range(previous_index + 1, count):
            # Not enough warehouses left after `i` to reach the required count.
            if count - i - 1 < remaining_used - 1:
                break

            warehouse = warehouses[i]
            tail = layers[i + 1][remaining_used - 1]
            max_take = min(warehouse.stock, remaining_qty)

            # Smallest feasible quantity first: it makes this entry - the
            # current position of the sorted allocation list - lex-smallest.
            for take in range(1, max_take + 1):
                rest = tail[remaining_qty - take]
                if rest >= INF:
                    continue
                if (
                    spent
                    + warehouse.fixed_cost
                    + take * warehouse.unit_cost
                    + rest
                    == total_cost
                ):
                    chosen = (i, warehouse, take)
                    break

            if chosen is not None:
                break

        if chosen is None:  # pragma: no cover - guarded by the DP invariant
            raise RuntimeError("failed to reconstruct an optimal allocation")

        index, warehouse, take = chosen
        allocation.append((warehouse.id, take))
        spent += warehouse.fixed_cost + take * warehouse.unit_cost
        remaining_qty -= take
        remaining_used -= 1
        previous_index = index

    return allocation


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
def parse(text: str) -> Tuple[List[Warehouse], int]:
    """Parse the ``W Q`` header plus ``W`` warehouse rows."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("empty input: missing the 'W Q' header line")

    header = lines[0].split()
    if len(header) != 2:
        raise ValueError(f"malformed header line: {lines[0]!r}")
    warehouse_count, quantity = int(header[0]), int(header[1])
    if warehouse_count < 1 or quantity < 0:
        raise ValueError("W must be >= 1 and Q must be >= 0")

    rows = lines[1 : 1 + warehouse_count]
    if len(rows) != warehouse_count:
        raise ValueError(
            f"expected {warehouse_count} warehouse rows, got {len(rows)}"
        )

    warehouses: List[Warehouse] = []
    seen: Dict[str, int] = {}
    for row in rows:
        parts = row.split()
        if len(parts) != 4:
            raise ValueError(f"malformed warehouse row: {row!r}")
        warehouse_id = parts[0]
        if warehouse_id in seen:
            raise ValueError(f"duplicate warehouse_id {warehouse_id!r}")
        seen[warehouse_id] = 1
        warehouses.append(
            Warehouse(
                id=warehouse_id,
                stock=int(parts[1]),
                fixed_cost=int(parts[2]),
                unit_cost=int(parts[3]),
            )
        )
    return warehouses, quantity


def solve(text: str, out: TextIO) -> None:
    warehouses, quantity = parse(text)
    out.write(format_plan(plan_fulfilment(warehouses, quantity)))
    out.write("\n")


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        with open(args[0], "r", encoding="utf-8") as handle:
            text = handle.read()
    else:
        text = sys.stdin.read()
    solve(text, sys.stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI shell
    raise SystemExit(main())
