"""Prescription <-> bill reconciliation: a second, independent evidence channel.

Questions answered, all from the two documents alone (no external data):
  * billed_more      - more units billed than the prescription needs (beyond one spare strip)
  * not_prescribed   - a medicine on the bill that the prescription does not mention
  * not_billed       - a prescribed medicine that never appears on the bill (informational)
  * different_variant - the bill has the same brand as a prescribed medicine but a different variant (Shelcal-XT vs Shelcal 500):
                       a possible wrong-medicine dispense, listed first
  * total_mismatch   - line amounts do not add up to the printed bill total
Every flag is a question to ask, never an accusation: doctors add medicines verbally and pharmacies sell full strips.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from .bill import BillLine, TAB_UNITS, STRIP_UNITS, NON_MEDICINE, resolve
from .injectables import iv_fluid
from .brand_table import lookup as brand_lookup, tokens as brand_tokens
from .knowledge import resolve_generic
from .schemas import Prescription, Medication


@dataclass
class Flag:
    kind: str
    subject: str
    note: str


def first_word(s: str) -> str:
    m = re.findall(r"[a-z]+", s.lower())
    skip = {"tab", "tablet", "cap", "capsule", "syp", "inj"}
    return next((t for t in m if t not in skip), "")


def per_day(freq: str | None) -> int | None:
    if not freq or freq == "SOS":
        return None
    d = re.findall(r"\d", freq)
    return sum(int(x) for x in d) if d else None


def billed_units(l: BillLine) -> float | None:
    u = (l.unit or "").lower()
    if u in TAB_UNITS:
        return l.qty
    if u in STRIP_UNITS and l.pack:
        return l.qty * l.pack
    return None


def _same_product(rx_text: str, bill_text: str) -> bool:
    """Same medicine whatever the brand: identical salts and strengths, or the same IV fluid and bag size."""
    ra, rb = resolve(rx_text), resolve(bill_text)
    if ra and rb and ra[0] == rb[0] and ra[1] and sorted(ra[1]) == sorted(rb[1]):
        return True
    fa, fb = iv_fluid(rx_text), iv_fluid(bill_text)
    return bool(fa and fb and fa == fb)


def _same(m: Medication, l: BillLine) -> bool:
    w = first_word(l.desc)
    if not w:
        return False
    a = [t for t in brand_tokens(l.desc) if t.isalpha()]
    b = [t for t in brand_tokens(m.name) if t.isalpha()]
    desc = _rx_desc(m, m.name)
    if a and b and a[0] == b[0]:
        # same brand word: 'Shelcal-XT' and 'Shelcal 500' are different products, so extra letters mean a different variant,
        # unless both resolve to the very same ingredients and strengths (a bill that also prints the generic name)
        return a == b or _same_product(desc, l.desc)
    if b and set(b) <= set(a):
        return True     # the bill prints the generic after its own brand ('ACYCLOTAS 500MG INJ ACYCLOVIR'): the prescribed name is in it
    if _same_product(desc, l.desc):
        return True     # a different brand of the same medicine and strength is a normal substitution
    g1, g2 = resolve_generic(w), m.generic
    return bool(g1 and g2 and g1 == g2)


def reconcile(rx: Prescription, lines: list[BillLine], printed_total: float | None = None) -> list[Flag]:
    flags: list[Flag] = []
    meds = [l for l in lines if not NON_MEDICINE.search(l.desc)]
    used = set()
    for m in rx.medications:
        match = [l for l in meds if _same(m, l)]
        used.update(id(l) for l in match)
        if not match:
            flags.append(Flag("not_billed", m.name, "Prescribed but not on this bill (maybe bought elsewhere or still to buy)."))
            continue
        pd_, days = per_day(m.frequency), m.duration_days
        units = [billed_units(l) for l in match]
        if pd_ and days and all(u is not None for u in units):
            need, got = pd_ * days, sum(units)
            spare = max((l.pack or 10) for l in match)
            if got > need + spare:
                flags.append(Flag("billed_more", m.name, f"Prescription needs about {need:g} units ({pd_}/day x {days} days) "
                                  f"but {got:g} are billed. Ask whether a longer course or extra stock was intended."))
    for l in meds:
        if id(l) not in used:
            flags.append(Flag("not_prescribed", l.desc, "On the bill but not found in the prescription you gave. "
                              "Check whether the doctor added it verbally."))
    if printed_total is not None:
        s = sum(l.amount for l in lines)
        if abs(s - printed_total) > 1.0:
            flags.append(Flag("total_mismatch", "Bill total", f"Lines add up to {s:.2f} but the bill total is {printed_total:.2f} "
                              f"(difference {printed_total - s:+.2f}; may be taxes, rounding or untranscribed lines)."))
    return _pair_variants(flags, rx, lines)


def _composition(text: str):
    """Ingredients of a brand as written, from the brand table (tries each solid/injectable form); None if unknown."""
    for form in ("tablet", "capsule", "injection", "liquid", "topical"):
        hit = brand_lookup(text, form)
        if hit:
            return hit
    return None


def _show(hit) -> str:
    return " + ".join(f"{s} {v:g} {u}" for s, (v, u) in zip(hit.salts.split("+"), hit.strengths))


def compare_variants(prescribed: str, billed: str) -> str:
    """One sentence on what actually differs between two variants of a brand, only as far as the table knows."""
    a, b = _composition(prescribed), _composition(billed)
    if not (a and b):
        who = " or ".join(n for n, h in ((prescribed, a), (billed, b)) if not h)
        return f"We could not look up the ingredients of {who}, so we cannot say how they differ."
    sa, sb = set(a.salts.split("+")), set(b.salts.split("+"))
    if sa != sb:
        parts = []
        if sb - sa:
            parts.append(f"the billed one adds {', '.join(sorted(sb - sa))}")
        if sa - sb:
            parts.append(f"the billed one lacks {', '.join(sorted(sa - sb))}")
        return f"Ingredients differ: prescribed is {_show(a)}; billed is {_show(b)} ({'; '.join(parts)})."
    if sorted(a.strengths) != sorted(b.strengths):
        return f"Same ingredients, different strength: prescribed is {_show(a)}; billed is {_show(b)}."
    if a.modified_release != b.modified_release:
        return f"Same ingredients and strength, but {'prescribed is modified-release' if a.modified_release else 'billed is modified-release'}."
    return f"Both are listed as {_show(a)}: the difference may only be the pack or brand spelling."


def _rx_desc(m: Medication | None, name: str) -> str:
    """Brand plus the strength the doctor wrote, found in the structured field or right after the name in the raw line."""
    if m is None:
        return name
    if m.strength:
        return f"{name} {m.strength}"
    hit = re.search(re.escape(name.split()[0]) + r"[\w\-. ]*?\s(\d+(?:\.\d+)?)\b", m.raw or "", re.I)
    return f"{name} {hit[1]}" if hit and name.split()[-1].lower() in (m.raw or "").lower() else name


def _pair_variants(flags: list[Flag], rx: Prescription, lines: list[BillLine]) -> list[Flag]:
    """An unmatched prescribed medicine and an unmatched billed item that share the first brand word are probably the same
    brand in different variants: say so once, with both names and what differs, instead of two unrelated flags."""
    def head(s):
        t = [x for x in brand_tokens(s) if x.isalpha()]
        return t[0] if t else ""
    meds = {m.name: m for m in rx.medications}
    bill = {l.desc: l for l in lines}
    missing = {f.subject: f for f in flags if f.kind == "not_billed"}
    extra = {f.subject: f for f in flags if f.kind == "not_prescribed"}
    out, used = [], set()
    for rname in missing:
        for bname in extra:
            if bname not in used and head(rname) and head(rname) == head(bname):
                used |= {rname, bname}
                diff = compare_variants(_rx_desc(meds.get(rname), rname), bname)
                out.append(Flag("different_variant", f"{rname} -> {bname}",
                                f"The prescription says {rname} but the bill has {bname}. Same brand name, different product. {diff} "
                                "Ask the pharmacist to check the strip against the prescription before taking it, and to exchange it "
                                "if it is the wrong one."))
                break
    return out + [f for f in flags if f.subject not in used]
