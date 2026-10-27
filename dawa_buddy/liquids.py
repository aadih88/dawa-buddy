"""Per-ml / per-gm price benchmarks for oral liquids and topicals.

Tablets are compared per tablet; bottles and tubes need a different yardstick. Both price lists are reduced to
(salts, concentration, price per ml or gm):
  * NPPA ceilings for oral liquids are already quoted per 1 ML.
  * Jan Aushadhi lists a pack price and a pack size ('60 ml', '15 g tubes'), so price = MRP / content.
Concentration is compared, never the pack size: 125 mg/5 ml is the same product in a 30 ml or a 60 ml bottle.
Anything whose concentration cannot be read with certainty returns no benchmark.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from . import benchmarks as ja, ceilings as nppa

EXTRA = ja.STOP | {"paediatric", "pediatric", "gel", "cream", "ointment", "lotion", "drops", "drop", "tubes", "tube", "jar",
                   "skin", "topical", "dispersible", "dry", "syrup", "liquid", "bottle"}
MASS = {"mg": 1.0, "g": 1000.0, "mcg": 1.0, "iu": 1.0}
NOT_ORAL_OR_TOPICAL = re.compile(r"injection|eye|ear\b|ophthalmic|nasal|infusion|shampoo|soap|spray|inhal|vial|ampoule", re.I)
LIQUID_OR_TOPICAL = re.compile(r"suspension|syrup|solution|drops|gel\b|cream|ointment|lotion|oral liquid", re.I)


def salts_of(name: str) -> frozenset:
    return frozenset(w for w in ja.parse_ingredients(name.replace("-", " ").replace("+", " and ")) if w not in EXTRA)


def conc_from_text(text: str):
    """'... 125 mg per 5 ml' -> ((25.0, 'mg'),); '... 1% w/w' -> ((1.0, '%'),); None when not certain."""
    t = text.lower().replace(",", "")
    pct = re.findall(r"(\d+(?:\.\d+)?)\s*%", t)
    den = re.search(r"(?:per|/)\s*(\d+(?:\.\d+)?)\s*ml", t)
    d = float(den[1]) if den else 1.0 if re.search(r"/\s*ml\b", t) else None
    mass = re.findall(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|iu)\b", t)
    if pct and not (mass and d):
        return tuple(sorted((float(v), "%") for v in pct))
    if mass and d:
        return tuple(sorted((round(float(v) * MASS[u] / d, 6), "iu" if u == "iu" else "mcg" if u == "mcg" else "mg") for v, u in mass))
    return None


def conc_from_hit(strengths) -> tuple | None:
    """Brand-table strengths such as (125.0, 'mg/5ml') or (1.0, '%'). A bare '25mg' has no volume: refuse to guess."""
    out = []
    for v, u in strengths:
        m = re.fullmatch(r"(mg|mcg|g|iu)/(\d+(?:\.\d+)?)ml", u)
        if u == "%":
            out.append((float(v), "%"))
        elif m:
            out.append((round(v * MASS[m[1]] / float(m[2]), 6), "iu" if m[1] == "iu" else "mcg" if m[1] == "mcg" else "mg"))
        else:
            return None
    return tuple(sorted(out))


def same_conc(a, b) -> bool:
    return len(a) == len(b) and all(x[1] == y[1] and abs(x[0] - y[0]) <= 0.02 * max(x[0], y[0]) for x, y in zip(a, b))


def content(text: str):
    """'60 ml' / '15 g tubes' -> (60.0, 'ml') / (15.0, 'g')."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(ml|gm|g)\b", text.lower())
    return (float(m[1]), "ml" if m[2] == "ml" else "g") if m else None


def pack_from_desc(desc: str):
    """Pack size printed in a bill description; 'mg/5ml' is a strength, not a pack."""
    m = re.search(r"(?<![/\d.])(\d+(?:\.\d+)?)\s*(ml|gm|g)\b(?!\s*/)", desc.lower())
    return (float(m[1]), "ml" if m[2] == "ml" else "g") if m else None


@dataclass
class LiquidBench:
    name: str
    price_per_unit: float
    content: float | None          # pack size in ml/gm; None for NPPA (quoted per 1 ml)


_JA: list | None = None
_NP: list | None = None


def _ja():
    global _JA
    if _JA is None:
        _JA = []
        for r in ja.index():
            if r.available and LIQUID_OR_TOPICAL.search(r.name) and not NOT_ORAL_OR_TOPICAL.search(r.name):
                c, conc = content(r.unit_size), conc_from_text(r.name)
                if c and conc:
                    _JA.append((salts_of(r.name), conc, c, r))
    return _JA


def _nppa():
    global _NP
    if _NP is None:
        _NP = []
        for c in nppa.index():
            d = f"{c.formulation} {c.dosage}"
            if re.search(r"oral liquid|syrup|suspension", d, re.I) and not NOT_ORAL_OR_TOPICAL.search(d):
                conc = conc_from_text(c.dosage)
                if conc:
                    _NP.append((salts_of(c.formulation), conc, c))
    return _NP


def find_generic(salts: frozenset, conc, unit: str, billed_content: float | None) -> LiquidBench | None:
    """Jan Aushadhi price per ml/gm; of several pack sizes pick the one closest to what was billed."""
    hits = [(c, r) for s, k, c, r in _ja() if s == salts and same_conc(k, conc) and c[1] == unit]
    if not hits:
        return None
    target = billed_content or hits[0][0][0]
    c, r = min(hits, key=lambda h: abs(h[0][0] - target))
    return LiquidBench(r.name, r.mrp / c[0], c[0])


def find_ceiling(salts: frozenset, conc) -> LiquidBench | None:
    """NPPA ceiling per ml. If several variants match, take the highest so a doubt never becomes an accusation."""
    hits = [c for s, k, c in _nppa() if s == salts and same_conc(k, conc)]
    if not hits:
        return None
    c = max(hits, key=lambda x: x.price)
    return LiquidBench(f"{c.formulation} {c.dosage}", c.price, None)
