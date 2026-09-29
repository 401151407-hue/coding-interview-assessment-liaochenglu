"""Tests for Task B - Fulfilment Split Optimiser.

Run with::

    python -m pytest B/tests -q
"""

from __future__ import annotations

import io
import itertools
import pathlib
import random
import sys
import time
from typing import List, Optional, Sequence, Tuple

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from solution import (  # noqa: E402
    Warehouse,
    format_plan,
    parse,
    plan_fulfilment,
    solve,
)


def run(text: str) -> str:
    buffer = io.StringIO()
    solve(text, buffer)
    return buffer.getvalue().strip("\n")


def wh(warehouse_id: str, stock: int, fixed: int, unit: int) -> Warehouse:
    return Warehouse(warehouse_id, stock, fixed, unit)


# ---------------------------------------------------------------------------
# The worked example from the brief
# ---------------------------------------------------------------------------
SAMPLE_INPUT = """\
3 7
AU 5 8 2
CN 7 20 1
US 4 3 4
"""
SAMPLE_OUTPUT = "1 27\nCN 7"


def test_sample_from_brief() -> None:
    assert run(SAMPLE_INPUT) == SAMPLE_OUTPUT


def test_sample_input_file_matches_brief() -> None:
    path = pathlib.Path(__file__).resolve().parents[1] / "sample_input.txt"
    assert run(path.read_text(encoding="utf-8")) == SAMPLE_OUTPUT


# ---------------------------------------------------------------------------
# Objective 1 - fewest warehouses
# ---------------------------------------------------------------------------
def test_single_warehouse_wins_even_when_it_is_not_the_cheapest_per_unit() -> None:
    # Splitting across A and B would be cheaper per unit, but the rule asks for
    # the fewest warehouses first, so C (one big warehouse) must be chosen.
    plan = plan_fulfilment(
        [
            wh("A", 5, 0, 1),
            wh("B", 5, 0, 1),
            wh("C", 10, 0, 9),
        ],
        10,
    )
    assert plan == (90, [("C", 10)])


def test_report_count_matches_allocation_length() -> None:
    plan = plan_fulfilment([wh("A", 3, 1, 1), wh("B", 3, 1, 1)], 5)
    assert plan is not None
    cost, allocation = plan
    assert len(allocation) == 2
    assert cost == 1 + 3 * 1 + 1 + 2 * 1


# ---------------------------------------------------------------------------
# Objective 2 - cheapest split for a fixed warehouse count
# ---------------------------------------------------------------------------
def test_cheapest_units_are_allocated_first() -> None:
    # Neither warehouse alone can cover 3 units, so both must be used and the
    # cheaper unit price has to be filled first.
    plan = plan_fulfilment(
        [
            wh("A", 2, 0, 1),  # cheaper units
            wh("B", 2, 0, 5),  # expensive units
        ],
        3,
    )
    assert plan == (2 * 1 + 1 * 5, [("A", 2), ("B", 1)])


def test_zero_quantity_costs_nothing_even_with_expensive_warehouses() -> None:
    assert plan_fulfilment([wh("A", 1, 10**6, 10**6)], 0) == (0, [])


def test_fixed_cost_can_outweigh_a_cheaper_unit_price() -> None:
    plan = plan_fulfilment(
        [
            wh("A", 10, 500, 1),
            wh("B", 10, 0, 40),
        ],
        5,
    )
    assert plan == (5 * 40, [("B", 5)])


# ---------------------------------------------------------------------------
# Objective 3 - lexicographically smallest allocation
# ---------------------------------------------------------------------------
def test_lexicographic_tie_break_prefers_smaller_first_quantity() -> None:
    # Both splits cost 3 and use 2 warehouses. Sorted by id the candidates are
    # [("A", 1), ("B", 2)] and [("A", 2), ("B", 1)]; the former is smaller.
    assert format_plan(
        plan_fulfilment([wh("A", 2, 0, 1), wh("B", 2, 0, 1)], 3)
    ) == "2 3\nA 1\nB 2"


def test_lexicographic_tie_break_prefers_smaller_warehouse_id_first() -> None:
    # Two one-warehouse solutions with identical cost: pick the smaller id.
    assert format_plan(
        plan_fulfilment([wh("ZZ", 4, 0, 7), wh("AA", 4, 0, 7)], 4)
    ) == "1 28\nAA 4"


def test_lexicographic_tie_break_spreads_over_three_warehouses() -> None:
    warehouses = [wh("A", 3, 0, 1), wh("B", 3, 0, 1), wh("C", 3, 0, 1)]
    # 3 warehouses are required for 7 units; the flat cost is 7 whatever the
    # split, so the lexicographically smallest list wins.
    assert format_plan(plan_fulfilment(warehouses, 7)) == "3 7\nA 1\nB 3\nC 3"


# ---------------------------------------------------------------------------
# Impossible orders and degenerate inputs
# ---------------------------------------------------------------------------
def test_impossible_order_prints_minus_one() -> None:
    assert run("2 10\nA 3 0 1\nB 3 0 1\n") == "-1"


def test_zero_stock_warehouses_are_never_used() -> None:
    assert format_plan(
        plan_fulfilment([wh("A", 0, 0, 0), wh("B", 5, 2, 3)], 5)
    ) == "1 17\nB 5"


def test_all_stock_zero_is_impossible() -> None:
    assert plan_fulfilment([wh("A", 0, 1, 1), wh("B", 0, 1, 1)], 1) is None


def test_zero_demand_uses_no_warehouse() -> None:
    assert format_plan(plan_fulfilment([wh("A", 5, 9, 9)], 0)) == "0 0"


def test_exact_fit_single_warehouse() -> None:
    assert format_plan(plan_fulfilment([wh("A", 2000, 999, 1)], 2000)) == (
        "1 2999\nA 2000"
    )


def test_large_costs_stay_exact() -> None:
    plan = plan_fulfilment([wh("A", 2000, 10**6, 10**6)], 2000)
    assert plan == (10**6 + 2000 * 10**6, [("A", 2000)])


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def test_parse_reads_header_and_rows() -> None:
    warehouses, quantity = parse("2 9\nA 1 2 3\nB 4 5 6\n")
    assert quantity == 9
    assert warehouses == [wh("A", 1, 2, 3), wh("B", 4, 5, 6)]


@pytest.mark.parametrize(
    "text",
    [
        "",
        "2\nA 1 1 1\nB 1 1 1\n",  # header needs two values
        "2 5\nA 1 1 1\n",  # missing row
        "1 5\nA 1 1\n",  # row needs four values
        "2 5\nA 1 1 1\nA 1 1 1\n",  # duplicate id
        "0 5\n",  # W must be >= 1
    ],
)
def test_parse_rejects_bad_input(text: str) -> None:
    with pytest.raises(ValueError):
        parse(text)


# ---------------------------------------------------------------------------
# Differential test against an exhaustive search
# ---------------------------------------------------------------------------
def _brute_force(
    warehouses: Sequence[Warehouse], quantity: int
) -> Optional[Tuple[int, int, Tuple[Tuple[str, int], ...]]]:
    """Exhaustive optimum as ``(count, cost, sorted allocation)``."""
    ordered = sorted(warehouses, key=lambda w: w.id)
    best = None
    for size in range(0, len(ordered) + 1):
        for subset in itertools.combinations(ordered, size):
            if sum(w.stock for w in subset) < quantity:
                continue
            for allocation in _all_allocations(list(subset), quantity):
                cost = sum(
                    w.fixed_cost + take * w.unit_cost
                    for w, take in allocation
                )
                key = (
                    len(subset),
                    cost,
                    tuple((w.id, take) for w, take in allocation),
                )
                if best is None or key < best:
                    best = key
    return best


def _all_allocations(
    subset: List[Warehouse], quantity: int
) -> List[List[Tuple[Warehouse, int]]]:
    """Every distribution of ``quantity`` over ``subset`` with 1 <= take <= stock."""
    results: List[List[Tuple[Warehouse, int]]] = []
    tail_stock = [0] * (len(subset) + 1)
    for i in range(len(subset) - 1, -1, -1):
        tail_stock[i] = tail_stock[i + 1] + subset[i].stock

    def walk(index: int, remaining: int, acc: List[Tuple[Warehouse, int]]) -> None:
        if index == len(subset):
            if remaining == 0:
                results.append(list(acc))
            return
        low = max(1, remaining - tail_stock[index + 1])
        high = min(subset[index].stock, remaining - (len(subset) - index - 1))
        for take in range(low, high + 1):
            acc.append((subset[index], take))
            walk(index + 1, remaining - take, acc)
            acc.pop()

    if quantity == 0:
        return [[]]
    walk(0, quantity, [])
    return results


def test_matches_exhaustive_search_on_random_small_cases() -> None:
    rng = random.Random(20260929)
    checked = 0
    for _ in range(400):
        count = rng.randint(1, 6)
        warehouses = [
            wh(
                f"W{i}",
                rng.randint(0, 5),
                rng.randint(0, 3),
                rng.randint(0, 3),
            )
            for i in range(count)
        ]
        quantity = rng.randint(0, 8)

        expected = _brute_force(warehouses, quantity)
        plan = plan_fulfilment(warehouses, quantity)

        if expected is None:
            assert plan is None, (warehouses, quantity, plan)
        else:
            assert plan is not None, (warehouses, quantity, expected)
            cost, allocation = plan
            assert (len(allocation), cost, tuple(allocation)) == expected, (
                warehouses,
                quantity,
                plan,
                expected,
            )
        checked += 1
    assert checked == 400


def test_matches_exhaustive_search_on_named_lexicographic_traps() -> None:
    cases = [
        ([wh("B", 2, 0, 1), wh("A", 2, 0, 1)], 3),
        ([wh("C", 3, 1, 2), wh("A", 3, 1, 2), wh("B", 3, 1, 2)], 7),
        ([wh("A", 1, 0, 0), wh("B", 1, 0, 0), wh("C", 8, 5, 9)], 8),
        ([wh("A", 4, 2, 1), wh("B", 4, 2, 1), wh("C", 1, 100, 0)], 5),
        ([wh("Z", 5, 0, 2), wh("A", 5, 0, 2), wh("M", 5, 0, 2)], 10),
    ]
    for warehouses, quantity in cases:
        expected = _brute_force(warehouses, quantity)
        plan = plan_fulfilment(warehouses, quantity)
        assert plan is not None
        cost, allocation = plan
        assert (len(allocation), cost, tuple(allocation)) == expected


# ---------------------------------------------------------------------------
# Scale guard: W = 30, Q = 2000 must be tractable
# ---------------------------------------------------------------------------
def test_largest_input_shape_is_tractable() -> None:
    # 30 warehouses of 67 units each: 2000 units therefore forces all 30
    # warehouses, i.e. the widest DP table the constraints allow.
    warehouses = [
        wh(f"W{i:02d}", 67, 7 * i, 3 + (i % 5)) for i in range(30)
    ]
    started = time.perf_counter()
    plan = plan_fulfilment(warehouses, 2000)
    elapsed = time.perf_counter() - started

    assert plan is not None
    cost, allocation = plan
    by_id = {w.id: w for w in warehouses}
    assert len(allocation) == 30
    assert sum(take for _, take in allocation) == 2000
    assert cost == sum(
        by_id[wid].fixed_cost + take * by_id[wid].unit_cost
        for wid, take in allocation
    )
    assert elapsed < 30.0, f"DP took {elapsed:.2f}s"


def test_dp_scales_when_one_warehouse_alone_is_enough() -> None:
    warehouses = [wh(f"W{i:02d}", 2000, 10**6, 10**6) for i in range(30)]
    started = time.perf_counter()
    plan = plan_fulfilment(warehouses, 2000)
    elapsed = time.perf_counter() - started
    assert plan is not None
    assert len(plan[1]) == 1
    assert elapsed < 30.0, f"DP took {elapsed:.2f}s"
