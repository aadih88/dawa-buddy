"""NPPA ceiling prices (scheduled formulations).

Sources, newest first: (1) the three gazette notifications of 25.03.2026 revising ceilings w.e.f. 1.4.2026: 767 NLEM-2022,
138 NLEM-2015 and 6 NLEM-2011 formulations (scripts/parse_nppa_gazette.py); (2) the March 2026 category posters, kept only for
the 34 formulations the gazette lists lack (prices agree wherever both exist: 233 of 233 identical).
A missing ceiling therefore means 'not in our data', never 'no ceiling exists'.
The legal ceiling is excl. GST and is a maximum retail price, not a fair price.
"""
from __future__ import annotations
import csv, re
from dataclasses import dataclass
from pathlib import Path
from .benchmarks import is_modified_release, parse_form, parse_ingredients, parse_strengths

DATA = Path(__file__).resolve().parent.parent / "data"
GAZETTE_CSV = DATA / "nppa_ceiling_2026-04.csv"
POSTER_CSV = DATA / "nppa_ceiling_2026-03.csv"
DEFAULT_CSV = GAZETTE_CSV
AS_ON = "1 April 2026"


@dataclass
class Ceiling:
    category: str
    formulation: str
    dosage: str
    unit: str
    price: float
    ingredients: frozenset
    strengths: tuple
    form: str
    modified_release: bool


_IDX: list[Ceiling] | None = None


def _key(r) -> str:
    return re.sub(r"[^a-z0-9.+/]", "", (r["formulation"] + r["dosage"]).lower())


def index() -> list[Ceiling]:
    global _IDX
    if _IDX is None:
        _IDX, seen = [], set()
        for path in (GAZETTE_CSV, POSTER_CSV):
            if not path.exists():
                continue
            earlier = set(seen)      # a later file only fills gaps; rows inside one file are all kept
            with open(path, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if _key(r) in earlier:
                        continue
                    seen.add(_key(r))
                    full = f'{r["formulation"]} {r["dosage"]}'
                    _IDX.append(Ceiling(r["category"], r["formulation"], r["dosage"], r["unit"],
                                        float(r["ceiling_price"]), parse_ingredients(r["formulation"]),
                                        parse_strengths(full), parse_form(full), is_modified_release(full)))
    return _IDX


def find(ingredients: str, strengths: list[tuple[float, str]], form: str = "tablet",
         modified_release: bool = False) -> list[Ceiling]:
    want = parse_ingredients(ingredients.replace("+", " and "))
    return [c for c in index() if c.ingredients == want and c.form == form
            and c.modified_release == modified_release
            and (not strengths or sorted(strengths) == sorted(c.strengths))]
