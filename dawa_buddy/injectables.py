"""Price benchmarks for injections, per container (vial / ampoule) or per ml.

Two shapes appear in the price lists:
  * per container: 'Powder for Injection 500 mg' ... '1 Vial'      (NPPA); 'Meropenem Injection IP 500 mg' | 'Vial' (Jan Aushadhi)
  * per ml:        'Injection 50mg/mL' ... '1 ML'                    (NPPA); '... 10mg per ml' | '2 ml' ampoule (Jan Aushadhi)
A bill line is compared like with like: a per-vial price against a per-vial list price; a per-ml price against a per-ml one.
Converting between the two needs the ml per container, which the user must supply (pack), never guessed. Total strength
(mg per container) and concentration (mg per ml) are kept apart for the same reason: '20 mg' and '10 mg/ml' are different claims.
"""
from __future__ import annotations
import csv, re
from dataclasses import dataclass
from pathlib import Path
from . import benchmarks as ja, ceilings as nppa, liquids

MASS = {"mg": 1.0, "g": 1000.0, "gm": 1000.0, "mcg": 1.0, "iu": 1.0}
SKIP = re.compile(r"fluid|infusion|water for|dextrose|saline|ringer|glass|polypack|million|lac\b|cartridge|catridge", re.I)
VIAL_UNIT = re.compile(r"^(1\s*vial|1vial|each vial|each pack)$", re.I)
ML_UNIT = re.compile(r"^1\s*ml$", re.I)


def _unit(u: str) -> str:
    return "mg" if u in ("g", "gm") else u


def total_from_text(text: str):
    """mg / mcg / IU per container, e.g. 'Powder for Injection 500 mg (A) + 100 mg (B)'. None if a concentration is expressed."""
    t = text.lower().replace(",", "")
    if re.search(r"/\s*\d*\.?\d*\s*ml|per\s*\d*\.?\d*\s*ml|%", t):
        return None
    m = re.findall(r"(\d+(?:\.\d+)?)\s*(mg|mcg|gm|g|iu)\b", t)
    return tuple(sorted((round(float(v) * MASS[u], 6), _unit(u)) for v, u in m)) or None


def hit_specs(strengths, content: float | None):
    """(total, conc) for a brand-table hit. A plain '500mg' is per container; '10mg/1ml' is a concentration."""
    total, conc = [], []
    for v, u in strengths:
        m = re.fullmatch(r"(mg|mcg|g|iu)(?:/(\d+(?:\.\d+)?)ml)?", u)
        if not m:
            return None, None
        if m[2]:
            conc.append((round(v * MASS[m[1]] / float(m[2]), 6), _unit(m[1])))
        else:
            total.append((round(v * MASS[m[1]], 6), _unit(m[1])))
    if total and conc:
        return None, None
    total_t, conc_t = tuple(sorted(total)) or None, tuple(sorted(conc)) or None
    if conc_t and content:        # per-ml claim + known container size -> per-container
        total_t = tuple(sorted((round(v * content, 6), u) for v, u in conc_t))
    if total_t and content and not conc_t:
        conc_t = tuple(sorted((round(v / content, 6), u) for v, u in total_t))
    return total_t, conc_t


def close(a, b) -> bool:
    return bool(a) and bool(b) and len(a) == len(b) and all(x[1] == y[1] and abs(x[0] - y[0]) <= 0.02 * max(x[0], y[0]) for x, y in zip(a, b))


@dataclass
class Bench:
    name: str
    price: float          # per container, or per ml when per_ml
    per_ml: bool


_NP = _JA = None


def _nppa():
    global _NP
    if _NP is None:
        _NP = []
        for c in nppa.index():
            d = f"{c.formulation} {c.dosage}"
            if not re.search(r"inject", d, re.I) or SKIP.search(d):
                continue
            unit = re.sub(r"\s+", " ", c.unit.strip())
            if ML_UNIT.match(unit):
                conc = liquids.conc_from_text(c.dosage)
                if conc:
                    _NP.append((liquids.salts_of(c.formulation), None, conc, c.price, True, d))
            elif VIAL_UNIT.match(unit):
                total = total_from_text(c.dosage)
                if total:
                    _NP.append((liquids.salts_of(c.formulation), total, None, c.price, False, d))
    return _NP


def _ja():
    global _JA
    if _JA is None:
        _JA = []
        for r in ja.index():
            if not (r.available and re.search(r"inject", r.name, re.I)) or SKIP.search(r.name) or SKIP.search(r.unit_size):
                continue
            ml = re.search(r"(\d+(?:\.\d+)?)\s*ml", r.unit_size, re.I)
            content = float(ml[1]) if ml else None
            conc = liquids.conc_from_text(r.name)
            total = total_from_text(r.name)
            if conc and content and not total:
                total = tuple(sorted((round(v * content, 6), u) for v, u in conc))
            if total or conc:
                _JA.append((liquids.salts_of(r.name), total, conc, content, r.mrp, r.name))
    return _JA


def find_ceiling(salts, total, conc, billed_per_container: bool) -> Bench | None:
    """Per-container ceilings need a per-container bill price and a total; per-ml ceilings need a concentration."""
    for s, t, k, price, per_ml, label in _nppa():
        if s != salts:
            continue
        if not per_ml and billed_per_container and close(t, total):
            return Bench(label, price, False)
        if per_ml and close(k, conc):
            return Bench(label, price, True)
    return None


def find_generic(salts, total, conc, billed_per_container: bool, content: float | None) -> Bench | None:
    for s, t, k, c, mrp, label in _ja():
        if s != salts:
            continue
        if billed_per_container and close(t, total):
            return Bench(label, mrp, False)
        if content is None and not billed_per_container and close(k, conc) and c:
            return Bench(label, mrp / c, True)
    return None


def has_per_ml_benchmark(salts) -> bool:
    """True if this medicine is listed per ml somewhere: then the ml per vial would unlock a comparison."""
    return any(s == salts and per_ml for s, _t, _k, _p, per_ml, _l in _nppa()) or any(s == salts and k for s, _t, k, _c, _m, _l in _ja())


# ---- IV fluids: priced per bag by fluid and volume; glass and non-glass containers have different ceilings ----
FLUID_WORDS = [("dns", r"\b(dns|dextrose\s+normal\s+saline|dextrose\s+saline|glucose\s*\+\s*sodium\s+chloride)\b"),
               ("d25", r"\b(d25|(dextrose|glucose)\s*25\s*%|25\s*%\s*(dextrose|glucose))"),
               ("d5", r"\b(d5|(dextrose|glucose)\s*5\s*%|5\s*%\s*(dextrose|glucose))"),
               ("mannitol", r"\bmannitol\b"),
               ("metro", r"\b(metronidazole|metrogyl|flagyl)\b.*\b(iv|inj|infusion)\b|\b(iv|inj|infusion)\b.*\b(metronidazole|metrogyl|flagyl)\b"),
               ("cipro", r"\b(ciprofloxacin|ciplox|cifran)\b.*\b(iv|inj|infusion)\b|\b(iv|inj|infusion)\b.*\b(ciprofloxacin|ciplox|cifran)\b"),
               ("rl", r"\b(rl|ringers?\s+lactate|ringer'?s\s+lactate)\b"),
               ("ns", r"\b(ns|normal\s+saline|sodium\s+chloride|0\.9\s*%\s*(?:nacl|sodium|saline))\b")]
FLUID_NAMES = {"ns": "sodium chloride 0.9%", "rl": "ringer lactate", "dns": "glucose 5% + sodium chloride 0.9%", "d5": "glucose 5%",
               "d25": "glucose 25%", "mannitol": "mannitol 20%", "metro": "metronidazole 0.5% IV", "cipro": "ciprofloxacin 200 mg/100 ml IV"}
DATA = Path(__file__).resolve().parent.parent / "data"
SPECIAL_CSV = DATA / "nppa_ivfluids_special_2026-04.csv"
MAKERS_CSV = DATA / "nppa_special_makers_2026-04.csv"
_FLUID_ROWS: dict | None = None


def _fluid_key(formulation: str, dosage: str):
    f = formulation.lower()
    if "ringer" in f:
        return "rl"
    if "glucose" in f and "sodium chloride" in f:
        return "dns"
    if f.strip() == "sodium chloride" and "0.9" in dosage:
        return "ns"
    return None


def _fluid_rows() -> dict:
    global _FLUID_ROWS
    if _FLUID_ROWS is None:
        _FLUID_ROWS = {}
        for c in nppa.index():
            key = _fluid_key(c.formulation, c.dosage)
            if not key:
                continue
            unit = c.unit.strip()
            sized = re.match(r"^(\d+)\s*ml\s*(glass|non-?\s*glass)$", unit, re.I)      # '100ml Glass' / '100ml Non- Glass'
            if sized:
                vol, kind = int(sized[1]), ("glass" if sized[2].lower() == "glass" else "non-glass")
            elif re.match(r"^each pack$", unit, re.I) and (v := re.search(r"(\d+)\s*ml", c.dosage, re.I)):
                vol, kind = int(v[1]), "any"                                              # Ringer lactate: 'Injection 100ml', 'Each Pack'
            else:
                continue
            _FLUID_ROWS.setdefault((key, vol), []).append((kind, c.price))
    return _FLUID_ROWS


def iv_fluid(desc: str):
    """(fluid, volume_ml) for 'NS ... 0.9% 100ML' / 'RL 500ML' / 'DNS 500 ML', else None."""
    d = desc.lower()
    if re.search(r"\b(set|syringe|cannula)\b", d):
        return None
    vol = re.search(r"(\d+)\s*ml\b", d)
    if not vol:
        return None
    for key, pat in FLUID_WORDS:
        if re.search(pat, d):
            return key, int(vol[1])
    return None


def fluid_ceilings(fluid: str, volume: int):
    """[(container, ceiling per bag)] from the NPPA list, or []."""
    return _fluid_rows().get((fluid, volume), [])


# ---- 'special features' packs (Eurohead bottles, multi-port bags): separate, higher ceilings for listed manufacturers ----
_SPECIAL: dict | None = None
_MAKER_TOKENS: set | None = None
_MAKER_STOP = {"pvt", "ltd", "private", "limited", "healthcare", "pharma", "pharmaceuticals", "pharmaceutical", "laboratories", "lifescience",
               "lifesciences", "life", "sciences", "parenteral", "parenterals", "india", "indian", "medical", "note", "below", "manufacturer",
               "marketer", "drugs", "injectables", "biotech", "therapeutics", "infusion", "tech", "chem", "lab", "labs", "bottle", "bottles",
               "plastic", "with", "head", "euro", "cap", "port", "dual", "double", "glass", "special", "features", "brand", "name", "technology",
               "bags", "container", "propylene", "twin", "non", "safe", "dewdrip", "aqua", "drip"}


def special_ceiling(key: str, volume: int):
    """Per-bag ceiling for a special-features pack, or None."""
    global _SPECIAL
    if _SPECIAL is None:
        _SPECIAL = {}
        if SPECIAL_CSV.exists():
            with open(SPECIAL_CSV, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    _SPECIAL[(r["key"], int(r["volume_ml"]))] = float(r["bag_price"])
    return _SPECIAL.get((key, volume))


def special_pack_mentioned(desc: str) -> bool:
    """Does the bill line name a manufacturer or brand that NPPA lists as entitled to the special-features ceiling?"""
    global _MAKER_TOKENS
    if _MAKER_TOKENS is None:
        _MAKER_TOKENS = set()
        if MAKERS_CSV.exists():
            with open(MAKERS_CSV, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    for w in re.findall(r"[a-z]{4,}", f'{r["manufacturer"]} {r["brand"]}'.lower()):
                        if w not in _MAKER_STOP:
                            _MAKER_TOKENS.add(w)
    d = desc.lower()
    return bool(re.search(r"euro\s*head|special\s*features|\bffs\b|\bbfs\b", d)) or any(re.search(rf"\b{w}\b", d) for w in _MAKER_TOKENS)


def has_fluid_benchmark(fluid: str, volume: int) -> bool:
    return bool(fluid_ceilings(fluid, volume)) or special_ceiling(fluid, volume) is not None
