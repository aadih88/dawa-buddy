"""The reference numbers behind each verdict, in words a patient can check. Built only from the audit result: the rules decide, this only shows what they used.

Honesty points shown here on purpose: where the ingredient came from, that a missing ceiling means "none applies" (most medicines have none), and that the NPPA ceilings
are the list in force from 1 April 2026, so an older bill may have been priced under an earlier one.
"""
from __future__ import annotations
from . import bill as b

CEILING_NOTE = ("These are reference prices to ask about, not a finding. NPPA ceilings are the list in force from 1 April 2026; "
                "a bill from before then may have been priced under an earlier list.")
PER = {"tablet": "tablet", "ml": "ml", "gm": "gm", "vial": "vial", "bag": "bag"}


def reference(f: b.Finding, fmt, billed_word=lambda u: "unit") -> tuple[list[tuple[str, str]], str]:
    """(rows, foot). `fmt` formats rupees. Rows are (label, value); foot is the one caution, only when a ceiling is mentioned."""
    rows: list[tuple[str, str]] = []
    per = PER.get(f.basis, "unit")
    if f.ingredients:
        rows.append(("Identified as", f"{f.ingredients} {f.strength}".strip()))
        if f.source:
            rows.append(("Taken from", f.source))
    if f.unit_price:
        rows.append((f"You were charged (per {per})", fmt(f.unit_price)))
    elif f.mrp_unit:             # a printed-MRP finding has no per-unit price of its own: the rate on the bill is what was charged
        rows.append((f"You were charged (per {billed_word(f.line.unit)})", fmt(f.line.rate)))
    covered = f.tier not in (b.TIER_NOT_MEDICINE, b.TIER_UNIT_UNCLEAR, b.TIER_NEEDS_CONFIRM) and (f.ingredients or f.tier == b.TIER_SUPPLEMENT)
    shown_ceiling = False
    if f.ceiling:
        rows.append(("NPPA ceiling", f"{fmt(f.ceiling)} ({fmt(f.ceiling * b.GST_ALLOWANCE)} with GST)"))
        shown_ceiling = True
    elif covered:
        rows.append(("NPPA ceiling", "none: not price-controlled" if f.tier == b.TIER_SUPPLEMENT else "none applies"))
        shown_ceiling = True
    if f.generic_unit:
        rows.append(("Jan Aushadhi generic", fmt(f.generic_unit)))
    if f.mrp_unit:
        rows.append((f"MRP on your bill (per {billed_word(f.line.unit)})", fmt(f.mrp_unit)))
    return rows, (CEILING_NOTE if shown_ceiling else "")
