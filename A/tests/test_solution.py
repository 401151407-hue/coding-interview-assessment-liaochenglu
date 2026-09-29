"""Tests for Task A - Inventory Reservation Ledger.

Run with::

    python -m pytest A/tests -q
"""

from __future__ import annotations

import io
import pathlib
import random
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from solution import InventoryLedger, solve  # noqa: E402


def run(text: str) -> str:
    """Drive ``solve`` and return the produced report."""
    buffer = io.StringIO()
    solve(text, buffer)
    return buffer.getvalue()


def lines(text: str) -> list[str]:
    return run(text).strip("\n").split("\n")


# ---------------------------------------------------------------------------
# The worked example from the brief
# ---------------------------------------------------------------------------
SAMPLE_INPUT = """\
10 6
RESERVE e1 o100 4
RESERVE e2 o200 7
SHIP e3 o100 2
RELEASE e4 o100 2
RESTOCK e5 3
RESERVE e2 9999 1
"""

SAMPLE_OUTPUT = """\
OK 10 4
REJECTED 10 4
OK 8 2
OK 8 0
OK 11 0
DUPLICATE 11 0
OPEN 0
"""


def test_sample_from_brief() -> None:
    assert run(SAMPLE_INPUT) == SAMPLE_OUTPUT


def test_sample_input_file_matches_brief() -> None:
    path = pathlib.Path(__file__).resolve().parents[1] / "sample_input.txt"
    assert run(path.read_text(encoding="utf-8")) == SAMPLE_OUTPUT


# ---------------------------------------------------------------------------
# Core state transitions
# ---------------------------------------------------------------------------
def test_reserve_accumulates_per_order() -> None:
    assert lines(
        """\
20 3
RESERVE e1 o1 5
RESERVE e2 o1 7
RESERVE e3 o2 8
"""
    ) == ["OK 20 5", "OK 20 12", "OK 20 20", "OPEN 2", "o1 12", "o2 8"]


def test_reserve_at_exact_boundary_then_one_over() -> None:
    assert lines(
        """\
10 3
RESERVE e1 o1 10
RESERVE e2 o2 1
RESTOCK e3 5
"""
    ) == ["OK 10 10", "REJECTED 10 10", "OK 15 10", "OPEN 1", "o1 10"]


def test_release_reduces_hold_but_not_on_hand() -> None:
    assert lines(
        """\
10 3
RESERVE e1 o1 4
RELEASE e2 o1 3
RELEASE e3 o1 1
"""
    ) == ["OK 10 4", "OK 10 1", "OK 10 0", "OPEN 0"]


def test_release_above_hold_is_rejected_atomically() -> None:
    assert lines(
        """\
10 3
RESERVE e1 o1 4
RELEASE e2 o1 5
RELEASE e3 o1 4
"""
    ) == ["OK 10 4", "REJECTED 10 4", "OK 10 0", "OPEN 0"]


def test_ship_decrements_on_hand_and_hold() -> None:
    assert lines(
        """\
10 3
RESERVE e1 o1 6
SHIP e2 o1 4
SHIP e3 o1 3
"""
    ) == ["OK 10 6", "OK 6 2", "REJECTED 6 2", "OPEN 1", "o1 2"]


def test_operations_on_order_without_reservation_are_rejected() -> None:
    assert lines(
        """\
10 3
RELEASE e1 o9 1
SHIP e2 o9 1
RESERVE e3 o9 1
"""
    ) == ["REJECTED 10 0", "REJECTED 10 0", "OK 10 1", "OPEN 1", "o9 1"]


def test_restock_does_not_need_an_order_id() -> None:
    assert lines("0 2\nRESTOCK e1 1000000000000\nRESTOCK e2 1\n") == [
        "OK 1000000000000 0",
        "OK 1000000000001 0",
        "OPEN 0",
    ]


def test_huge_quantity_within_constraints() -> None:
    # S and qty up to 10^12; on_hand - reserved must stay exact.
    assert lines(
        """\
1000000000000 3
RESERVE e1 o1 1000000000000
RESERVE e2 o2 1
RESTOCK e3 1000000000000
"""
    ) == [
        "OK 1000000000000 1000000000000",
        "REJECTED 1000000000000 1000000000000",
        "OK 2000000000000 1000000000000",
        "OPEN 1",
        "o1 1000000000000",
    ]


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
def test_replaying_a_successful_event_is_duplicate_and_has_no_effect() -> None:
    assert lines(
        """\
10 3
RESERVE e1 o1 4
RESERVE e1 o2 4
RESERVE e1 o1 4
"""
    ) == ["OK 10 4", "DUPLICATE 10 4", "DUPLICATE 10 4", "OPEN 1", "o1 4"]


def test_replaying_a_business_rejection_is_duplicate() -> None:
    assert lines(
        """\
1 4
RESERVE e1 o1 5
RESERVE e1 o1 5
RESTOCK e2 100
RESERVE e1 o1 5
"""
    ) == [
        "REJECTED 1 0",
        "DUPLICATE 1 0",
        "OK 101 0",
        # Still a DUPLICATE even though the reservation would now succeed.
        "DUPLICATE 101 0",
        "OPEN 0",
    ]


def test_replaying_a_ship_is_duplicate() -> None:
    assert lines(
        """\
10 3
RESERVE e1 o1 5
SHIP e2 o1 2
SHIP e2 o1 2
"""
    ) == ["OK 10 5", "OK 8 3", "DUPLICATE 8 3", "OPEN 1", "o1 3"]


def test_event_ids_are_globally_unique_across_commands() -> None:
    # The same event id reused with a different opcode is still a duplicate.
    assert lines(
        """\
10 2
RESERVE e1 o1 4
RESTOCK e1 5
"""
    ) == ["OK 10 4", "DUPLICATE 10 4", "OPEN 1", "o1 4"]


def test_malformed_events_are_not_registered_as_processed() -> None:
    # A syntax error is not a business operation, so it is not remembered and a
    # later good line with the same event id still executes.
    assert lines(
        """\
10 3
RESERVE e1 o1 0
RESTOCK e1 5
RESTOCK e1 5
"""
    ) == ["REJECTED 10 0", "OK 15 0", "DUPLICATE 15 0", "OPEN 0"]


# ---------------------------------------------------------------------------
# Malformed input
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "command",
    [
        "RESERVE e1 o1",  # missing qty
        "RESERVE e1 o1 1 2",  # extra operand
        "RESTOCK e1",  # missing qty
        "CANCEL e1 o1 1",  # unknown opcode
        "reserve e1 o1 1",  # opcode is case sensitive
        "RESERVE e1 o1 -1",  # negative
        "RESERVE e1 o1 0",  # zero is not positive
        "RESERVE e1 o1 1.5",  # not an integer
        "RESERVE e1 o1 abc",  # not a number
        "RESERVE e1 o1 +1",  # signed form is not accepted
        "RESERVE  o1 1",  # missing event id shifts arity
        "RESERVE e1 o1 1#",  # trailing junk on the quantity token
        "RESERVE e\u00e91 o1 1",  # non-ASCII identifier
    ],
)
def test_malformed_command_is_rejected_without_state_change(command: str) -> None:
    report = lines(f"10 1\n{command}\n")
    assert report == ["REJECTED 10 0", "OPEN 0"]


def test_malformed_line_does_not_disturb_surrounding_commands() -> None:
    assert lines(
        """\
10 4
RESERVE e1 o1 4
BOGUS e2 o1 1
RESERVE e3 o1 2
RESERVE e4 o1
"""
    ) == ["OK 10 4", "REJECTED 10 4", "OK 10 6", "REJECTED 10 6", "OPEN 1", "o1 6"]


def test_blank_lines_and_extra_whitespace_are_tolerated() -> None:
    # Whitespace-only lines are skipped and do not consume a command slot.
    assert lines("10 2\n\n   RESERVE   e1\t o1    4  \nRESERVE e2 o1 1\n\n") == [
        "OK 10 4",
        "OK 10 5",
        "OPEN 1",
        "o1 5",
    ]


def test_open_reservations_sorted_by_order_id() -> None:
    assert lines(
        """\
30 4
RESERVE e1 zeta 1
RESERVE e2 alpha 2
RESERVE e3 Mike 3
RESERVE e4 beta 4
"""
    ) == [
        "OK 30 1",
        "OK 30 3",
        "OK 30 6",
        "OK 30 10",
        "OPEN 4",
        "Mike 3",
        "alpha 2",
        "beta 4",
        "zeta 1",
    ]


def test_fully_released_order_is_no_longer_open() -> None:
    assert lines(
        """\
10 4
RESERVE e1 o1 4
RESERVE e2 o2 4
RELEASE e3 o1 4
SHIP e4 o2 4
"""
    ) == ["OK 10 4", "OK 10 8", "OK 10 4", "OK 6 0", "OPEN 0"]


def test_zero_commands() -> None:
    assert lines("5 0\n") == ["OPEN 0"]


def test_header_only_zero_stock() -> None:
    assert lines(
        """\
0 2
RESERVE e1 o1 1
RESTOCK e2 1
"""
    ) == ["REJECTED 0 0", "OK 1 0", "OPEN 0"]


@pytest.mark.parametrize("header", ["10", "10 2 3", "x 2", "-1 2", "10 -2", ""])
def test_bad_header_raises(header: str) -> None:
    with pytest.raises(ValueError):
        run(f"{header}\n")


def test_truncated_input_is_processed_up_to_the_available_lines() -> None:
    assert lines("10 5\nRESERVE e1 o1 1\n") == ["OK 10 1", "OPEN 1", "o1 1"]


# ---------------------------------------------------------------------------
# Ledger used directly (no I/O)
# ---------------------------------------------------------------------------
def test_ledger_available_tracks_reservations() -> None:
    ledger = InventoryLedger(10)
    ledger.apply("RESERVE e1 o1 6")
    assert ledger.available == 4
    ledger.apply("SHIP e2 o1 4")
    assert (ledger.on_hand, ledger.reserved, ledger.available) == (6, 2, 4)
    ledger.apply("RESTOCK e3 4")
    assert ledger.available == 8


def test_ledger_never_goes_negative_under_random_commands() -> None:
    rng = random.Random(20260929)
    ledger = InventoryLedger(50)
    orders = ["o1", "o2", "o3"]
    for step in range(5_000):
        op = rng.choice(["RESERVE", "RELEASE", "SHIP", "RESTOCK"])
        qty = rng.randint(1, 12)
        order = rng.choice(orders)
        if op == "RESTOCK":
            ledger.apply(f"RESTOCK e{step} {qty}")
        else:
            ledger.apply(f"{op} e{step} {order} {qty}")
        assert ledger.on_hand >= 0
        assert ledger.reserved >= 0
        assert ledger.reserved <= ledger.on_hand


# ---------------------------------------------------------------------------
# Performance guard for the stated 200,000 command bound
# ---------------------------------------------------------------------------
def test_two_hundred_thousand_commands_complete_quickly() -> None:
    n = 200_000
    orders = [f"o{i:06d}" for i in range(1_000)]
    payload = ["1000000000000 " + str(n)]
    for i in range(n):
        order = orders[i % len(orders)]
        op = ("RESERVE", "RELEASE", "SHIP", "RESTOCK")[i % 4]
        if op == "RESTOCK":
            payload.append(f"RESTOCK e{i} 12345")
        else:
            payload.append(f"{op} e{i} {order} 7")
    text = "\n".join(payload) + "\n"

    started = time.perf_counter()
    report = run(text)
    elapsed = time.perf_counter() - started

    emitted = report.splitlines()
    # `n` per-command result lines, then the OPEN summary and its rows.
    assert emitted[0] == "OK 1000000000000 7"
    assert emitted[n].startswith("OPEN ")
    assert len(emitted) > n + 1
    assert elapsed < 10.0, f"O(N) processor took {elapsed:.2f}s for N={n}"
