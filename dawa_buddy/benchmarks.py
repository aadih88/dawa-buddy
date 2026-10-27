"""Jan Aushadhi (PMBJP) price benchmark loader and matcher.

Source: official product list CSV downloaded from janaushadhi.gov.in (snapshot date in filename).
Key rules learned from the data:
  * 343 of 2,439 rows have MRP 0: that means "no price listed / not available", NOT free.
  * Pack sizes vary ("10's", "15's", "100's in Bottle"); always compare per unit, never per strip.
  * Spelling differs from brand-world usage ("amoxycillin", "thyroxine").
"""
from __future__ import annotations
import csv, re
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
DEFAULT_CSV = DATA / "janaushadhi_2026-10-21.csv"

SYNONYMS = {"frusemide": "furosemide", "torasemide": "torsemide", "acetylsalicylic acid": "aspirin", "amoxycillin": "amoxicillin", "levothyroxine": "thyroxine", "levo-thyroxine": "thyroxine",
            "paracetamol": "paracetamol", "acetaminophen": "paracetamol", "potassium clavulanate": "clavulanic acid",
            "clavulanate": "clavulanic acid", "sodium": "", "hydrochloride": "", "gastro-resistant": "",
            "gastro": "", "resistant": "", "resistance": ""}
FORM_WORDS = [("tablet", "tablet"), ("capsule", "capsule"), ("injection", "injection"), ("syrup", "liquid"),
              ("suspension", "liquid"), ("solution", "liquid"), ("drops", "drops"), ("gel", "topical"),
              ("cream", "topical"), ("ointment", "topical"), ("lotion", "topical"), ("inhaler", "inhaler")]
STOP = {"tablets", "tablet", "capsules", "capsule", "ip", "bp", "usp", "and", "per", "with", "of", "for",
        "oral", "injection", "syrup", "suspension", "solution", "prolonged-release", "sustained", "release",
        "extended", "modified", "film", "coated", "enteric", "dispersible", "chewable", "w/v", "w/w", "i", "v"}


@dataclass
class JARecord:
    code: str
    name: str
    unit_size: str
    mrp: float
    group: str
    form: str
    ingredients: frozenset
    strengths: tuple
    pack_units: int | None
    modified_release: bool = False
    available: bool = field(init=False)

    def __post_init__(self):
        self.available = self.mrp > 0

    @property
    def price_per_unit(self) -> float | None:
        if self.available and self.pack_units:
            return round(self.mrp / self.pack_units, 4)
        return None


def _norm_text(s: str) -> str:
    s = s.lower()
    for k, v in sorted(SYNONYMS.items(), key=lambda kv: -len(kv[0])):
        s = s.replace(k, v) if v != k else s
    return s


def parse_ingredients(name: str) -> frozenset:
    s = _norm_text(name)
    s = re.sub(r"\(.*?\)", " ", s)
    words = re.findall(r"[a-z][a-z\-]+", re.sub(r"\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|%)", " ", s))
    return frozenset(w for w in words if w not in STOP and len(w) > 2)


def parse_strengths(name: str) -> tuple:
    return tuple((float(v), u) for v, u in re.findall(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|iu)\b", name.lower()))


def parse_form(name: str) -> str:
    n = name.lower()
    for key, form in FORM_WORDS:
        if key in n:
            return form
    return "other"


def is_modified_release(name: str) -> bool:
    return bool(re.search(r"modified|prolonged|sustained|extended|controlled|\bsr\b|\bxr\b|\bcr\b|\ber\b", name.lower()))


def parse_pack(unit: str) -> int | None:
    m = re.match(r"\s*(\d+)\s*'?s", unit)
    return int(m.group(1)) if m else None


def load(path: Path = DEFAULT_CSV) -> list[JARecord]:
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            name = r["Generic Name"].strip()
            out.append(JARecord(code=r["Drug Code"], name=name, unit_size=r["Unit Size"].strip(),
                                mrp=float(r["MRP"]), group=r["Group Name"], form=parse_form(name),
                                ingredients=parse_ingredients(name), strengths=parse_strengths(name),
                                pack_units=parse_pack(r["Unit Size"]), modified_release=is_modified_release(name)))
    return out


_INDEX: list[JARecord] | None = None


def index() -> list[JARecord]:
    global _INDEX
    if _INDEX is None:
        _INDEX = load()
    return _INDEX


def find(ingredients: str, strengths: list[tuple[float, str]], form: str = "tablet",
         modified_release: bool = False) -> list[JARecord]:
    """Exact-salt, exact-strength match. `ingredients` like 'amoxicillin+clavulanic acid'."""
    want = parse_ingredients(ingredients.replace("+", " and "))
    hits = [r for r in index() if r.ingredients == want and r.form == form
            and r.modified_release == modified_release
            and (not strengths or sorted(strengths) == sorted(r.strengths))]
    return sorted(hits, key=lambda r: (not r.available, r.mrp))
