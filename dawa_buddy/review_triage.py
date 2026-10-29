"""Which bill lines need a person, and which can simply be approved.

The review screen draws this decision; it does not make it, so it can be tested without a browser. A line is
  ok      quantity x price equals the value, nothing was guessed and the unit is known: shown collapsed, approved with one tap
  check   the numbers multiply out but something was chosen for the user (hard-to-read digits, numbers picked among candidates, unit unknown): shown open
  fix     quantity x price does not equal the value, or a number is missing: shown open, and the bill total points at it
The patient still approves every number; this only decides where their eyes have to go.
"""
from __future__ import annotations

OK, CHECK, FIX = "ok", "check", "fix"
# notes from the reader that mean "we chose between numbers": the patient should compare with the paper. Others (MRP per tablet) are information only.
CHOSEN = ("picked from the printed numbers", "before tax was on the bill", "worked out as the line value")


def _has(v) -> bool:
    return v is not None and v == v and v != 0


def multiplies_out(qty, rate, amount) -> bool:
    return all(_has(x) for x in (qty, rate, amount)) and abs(qty * rate - amount) <= max(0.51, 0.005 * amount)


def line_status(qty, rate, amount, unit, unsure=False, notes=()) -> tuple[str, str]:
    """(status, one-sentence reason). The reason is what the card says; empty for ok."""
    if not multiplies_out(qty, rate, amount):
        return FIX, "Quantity × price does not equal the value. Compare with your paper."
    if unsure:
        return CHECK, "This line was hard to read in the photo. Compare it with your paper."
    if any(c in n for n in notes for c in CHOSEN):
        return CHECK, "We chose these numbers so they multiply out. Compare them with your paper."
    if not unit:
        return CHECK, "Choose how it was sold, so the price can be compared."
    return OK, ""


def bill_tie(amounts, total) -> tuple[str, float]:
    """('match' | 'mismatch' | 'none', lines sum). The sum of the lines against the total printed on the bill."""
    s = round(sum(a for a in amounts if _has(a)), 2)
    if not _has(total):
        return "none", s
    return ("match" if abs(s - total) <= max(1.0, 0.005 * total) else "mismatch"), s


def summary(statuses: list[str]) -> dict:
    return {"lines": len(statuses), OK: statuses.count(OK), CHECK: statuses.count(CHECK), FIX: statuses.count(FIX)}
