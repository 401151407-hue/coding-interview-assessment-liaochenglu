"""Task A - Inventory Reservation Ledger.

A deterministic, single-SKU command processor with idempotent event handling.

Command grammar (one command per line, whitespace separated):

    RESERVE <event_id> <order_id> <qty>
    RELEASE <event_id> <order_id> <qty>
    SHIP    <event_id> <order_id> <qty>
    RESTOCK <event_id> <qty>

Per command the processor emits ``OK``, ``REJECTED`` or ``DUPLICATE`` followed by
the current ``on_hand`` and ``reserved`` totals. After the last command the open
reservations are printed sorted by ``order_id``.

Design notes
------------
* ``available`` is derived (``on_hand - reserved``) and never stored; the two
  counters required by the output format are stored explicitly.
* ``event_id`` idempotency is a set lookup. A *business* rejection (not enough
  stock, over-release, ...) is still recorded as processed, therefore replaying
  it yields ``DUPLICATE`` instead of a second ``REJECTED``.
* Malformed lines are rejected atomically: parsing fails before any state
  mutation, and the event is deliberately **not** recorded as processed because
  a malformed line carries no trustworthy ``event_id``. See ``ANALYSIS.md``.
* Whitespace-only lines are skipped; they carry no command and therefore do not
  consume a slot of the declared command count.
* Everything runs in ``O(N)`` time / ``O(N)`` space over the command count, which
  keeps a 200,000 command input comfortably in budget.

Usage::

    python solution.py input.txt
    python solution.py < input.txt
"""

from __future__ import annotations

import sys
from typing import Dict, List, Optional, Set, TextIO, Tuple

#: Arity of each command including the opcode itself.
_COMMAND_ARITY: Dict[str, int] = {
    "RESERVE": 4,
    "RELEASE": 4,
    "SHIP": 4,
    "RESTOCK": 3,
}


class MalformedCommand(ValueError):
    """Raised when a line cannot be understood as a well-formed command."""


class InventoryLedger:
    """Mutable ledger for a single SKU.

    The class is intentionally side-effect free with respect to I/O so it can be
    unit tested and reused; :func:`solve` owns the streaming layer.
    """

    __slots__ = ("on_hand", "reserved", "_held_by_order", "_processed_events")

    def __init__(self, on_hand: int) -> None:
        if on_hand < 0:
            raise ValueError("initial stock must be non-negative")
        self.on_hand: int = on_hand
        self.reserved: int = 0
        self._held_by_order: Dict[str, int] = {}
        self._processed_events: Set[str] = set()

    # -- derived state ----------------------------------------------------
    @property
    def available(self) -> int:
        """Stock that may still be reserved (``on_hand`` - ``reserved``)."""
        return self.on_hand - self.reserved

    def open_reservations(self) -> List[Tuple[str, int]]:
        """Reservations still outstanding, ordered by ``order_id``."""
        return sorted(
            (order_id, qty)
            for order_id, qty in self._held_by_order.items()
            if qty > 0
        )

    # -- command handling -------------------------------------------------
    def apply(self, line: str) -> str:
        """Apply one raw command line and return its result line."""
        try:
            op, event_id, order_id, qty = _parse_command(line)
        except MalformedCommand:
            # Atomic rejection: nothing was parsed successfully so nothing can
            # have been mutated, and there is no event id worth remembering.
            return self._result("REJECTED")

        if event_id in self._processed_events:
            return self._result("DUPLICATE")

        accepted = self._execute(op, order_id, qty)
        # Accepted *and* business-rejected events are both "processed".
        self._processed_events.add(event_id)
        return self._result("OK" if accepted else "REJECTED")

    def _execute(self, op: str, order_id: Optional[str], qty: int) -> bool:
        if op == "RESTOCK":
            self.on_hand += qty
            return True

        if op == "RESERVE":
            if qty > self.available:
                return False
            self._set_held(order_id, self._held(order_id) + qty)
            self.reserved += qty
            return True

        # RELEASE / SHIP -------------------------------------------------
        held = self._held(order_id)
        if qty > held:
            return False
        self._set_held(order_id, held - qty)
        self.reserved -= qty
        if op == "SHIP":
            # Shipping consumes physical stock in addition to the reservation.
            self.on_hand -= qty
        return True

    # -- internal helpers -------------------------------------------------
    def _held(self, order_id: Optional[str]) -> int:
        return self._held_by_order.get(order_id, 0)  # type: ignore[arg-type]

    def _set_held(self, order_id: Optional[str], qty: int) -> None:
        assert order_id is not None  # guaranteed by the parser
        if qty:
            self._held_by_order[order_id] = qty
        else:
            self._held_by_order.pop(order_id, None)

    def _result(self, status: str) -> str:
        return f"{status} {self.on_hand} {self.reserved}"


def _parse_command(line: str) -> Tuple[str, str, Optional[str], int]:
    """Parse ``line`` into ``(op, event_id, order_id, qty)``.

    Raises :class:`MalformedCommand` for anything that is not a syntactically
    valid command. Quantities must be positive integers rendered in ASCII.
    """
    parts = line.split()
    if not parts:
        raise MalformedCommand("empty command line")

    op = parts[0]
    arity = _COMMAND_ARITY.get(op)
    if arity is None:
        raise MalformedCommand(f"unknown command {op!r}")
    if len(parts) != arity:
        raise MalformedCommand(
            f"{op} expects {arity - 1} operand(s), got {len(parts) - 1}"
        )

    operands = parts[1:]
    for token in operands[:-1]:
        if not token.isascii():
            raise MalformedCommand("identifiers must be non-empty ASCII tokens")

    qty_token = operands[-1]
    if not (qty_token.isascii() and qty_token.isdigit()):
        raise MalformedCommand("quantity must be a positive integer")
    qty = int(qty_token)
    if qty <= 0:
        raise MalformedCommand("quantity must be a positive integer")

    if op == "RESTOCK":
        return op, operands[0], None, qty
    return op, operands[0], operands[1], qty


def solve(text: str, out: TextIO) -> None:
    """Process ``text`` and write the report to ``out``."""
    lines = text.splitlines()
    total_lines = len(lines)

    cursor = 0
    while cursor < total_lines and not lines[cursor].strip():
        cursor += 1
    if cursor >= total_lines:
        raise ValueError("input is missing the 'S N' header line")

    header = lines[cursor].split()
    if len(header) != 2 or not all(_is_non_negative_int(t) for t in header):
        raise ValueError(f"malformed header line: {lines[cursor]!r}")
    initial_stock, command_count = int(header[0]), int(header[1])
    cursor += 1

    ledger = InventoryLedger(initial_stock)

    emitted: List[str] = []
    for _ in range(command_count):
        # Whitespace-only lines carry no command, so they are skipped without
        # consuming one of the `command_count` slots.
        while cursor < total_lines and not lines[cursor].strip():
            cursor += 1
        if cursor >= total_lines:
            break  # truncated input: stop rather than invent commands
        emitted.append(ledger.apply(lines[cursor]))
        cursor += 1

    open_rows = ledger.open_reservations()
    emitted.append(f"OPEN {len(open_rows)}")
    emitted.extend(f"{order_id} {qty}" for order_id, qty in open_rows)

    out.write("\n".join(emitted))
    out.write("\n")


def _is_non_negative_int(token: str) -> bool:
    return token.isascii() and token.isdigit()


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
