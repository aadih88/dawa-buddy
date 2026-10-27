"""Brand -> composition lookup built from a public brand table (see scripts/build_brand_index.py).

Brand names are matched whole: only trailing STRENGTH numbers may be dropped ('telma 40' -> 'telma'), never a
letter token, because 'pan d' (pantoprazole + domperidone) is a different product from 'pan'. Anything ambiguous
returns None so the caller falls back to asking the user.
"""
from __future__ import annotations
import json, re
from dataclasses import dataclass
from pathlib import Path

INDEX_PATH = Path(__file__).resolve().parent.parent / "data" / "brand_index.json"
OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "brand_overrides.json"
# Hand-checked entries replace the table's. The source table stores at most TWO actives per product, so 3-active brands
# (Zerodol-SP...) would otherwise look like 2-active ones. See _sources in the file.

SALT_SUFFIX = {"hydrochloride", "hcl", "sodium", "potassium", "calcium", "magnesium", "fumarate", "maleate",
               "besylate", "succinate", "tartrate", "mesylate", "sulphate", "sulfate", "acetate", "citrate", "oxalate",
               "medoxomil", "cilexetil", "mofetil", "pivoxil", "proxetil", "axetil", "trometamol", "tromethamine", "besilate",
               "hydrobromide", "dihydrate", "monohydrate", "trihydrate", "anhydrous", "hemihydrate"}
SALT_ALIAS = {"frusemide": "furosemide", "acetaminophen": "paracetamol", "levothyroxine": "thyroxine",
              "amoxycillin": "amoxicillin"}
NOISE = {"tablet", "tablets", "tab", "tabs", "capsule", "capsules", "cap", "caps", "injection", "inj", "syrup", "strip",
         "mg", "mcg", "ml", "gm", "g", "iu", "nos", "no", "of", "the", "ip", "bp",
         "suspension", "solution", "drops", "drop", "gel", "cream", "ointment", "lotion", "syp", "susp", "oint", "sol",
         "oral", "dry", "expectorant", "bottle", "tube"}
MR_SUFFIXES = ("mr", "sr", "xr", "er", "cr", "pr", "xl")    # bills often drop these; the table keeps them in the name
FORMS = ("tablet", "capsule", "injection", "liquid", "topical")
STRENGTH_RE = re.compile(r"(\d+(?:\.\d+)?)(mg|mcg|g|iu|%)(?:/(\d+(?:\.\d+)?(?:ml|g)))?")


@dataclass
class BrandHit:
    salts: str                  # 'telmisartan+hydrochlorothiazide'
    strengths: list             # [(40.0, 'mg'), (12.5, 'mg')] in the same order; liquids/topicals: (125.0, 'mg/5ml'), (1.0, '%')
    form: str
    modified_release: bool
    mr_guess: bool = False      # found only under an SR/XR/MR spelling the bill did not print: release type is a guess
    pack: int | None = None     # units per pack from the table (a suggestion to confirm on the strip), None if unknown or ambiguous


def tokens(s: str, bare_g_is_pack: bool = False) -> list[str]:
    s = s.lower()
    # '60ML' / '15GM' on a bill is a pack size, not part of the brand or its strength ('125mg/5ml' keeps its '/')
    s = re.sub(r"(?<![/\d.])\d+(?:\.\d+)?\s*(?:ml|gm" + ("|g" if bare_g_is_pack else "") + r")\b(?!\s*/)", " ", s)
    s = re.sub(r"\b\d+\s*'s\b|\b\d+s\b", " ", s)               # pack counts: 10's, 15s
    s = re.sub(r"(\d)\s*(mg|mcg|ml|gm|g|iu)\b", r"\1", s)       # 650mg -> 650
    return [t for t in re.findall(r"[a-z]+|\d+(?:\.\d+)?", s) if t not in NOISE]


def norm_salt(name: str) -> str:
    words = [SALT_ALIAS.get(w, w) for w in re.findall(r"[a-z]+", name.lower()) if w not in SALT_SUFFIX]
    return " ".join(words)


_IDX: dict | None = None


def _index() -> dict:
    global _IDX
    if _IDX is None:
        _IDX = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
        if OVERRIDES_PATH.exists():
            for key, forms in json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")).items():
                if not key.startswith("_"):
                    _IDX.setdefault(key, {}).update(forms)
    return _IDX


def _decode(comp: str, form: str, mr: int, pack: int = 0) -> BrandHit:
    salts, strengths = [], []
    for part in comp.split(";"):
        name, st = part.rsplit(":", 1)
        m = STRENGTH_RE.fullmatch(st)
        salts.append(name)
        strengths.append((float(m[1]), m[2] + (f"/{m[3]}" if m[3] else "")))
    return BrandHit("+".join(salts), strengths, form, bool(mr), pack=pack or None)


def lookup(desc: str, form: str = "tablet") -> BrandHit | None:
    toks = tokens(desc, bare_g_is_pack=form in ("liquid", "topical"))
    nums = {float(t) for t in toks if t[0].isdigit()}
    dropped: set[float] = set()
    guessed = False
    while toks:
        guessed = False
        base = " ".join(toks)
        entry = _index().get(base, {}).get(form)
        if not entry:   # 'VELTAM 0.4' vs table 'veltam 0.4 mr': accept a modified-release spelling only if exactly one exists
            alts = [e for x in MR_SUFFIXES if (e := _index().get(f"{base} {x}", {}).get(form))]
            entry = alts[0] if len(alts) == 1 else None
            guessed = entry is not None
        if entry:
            if len(entry) > 1:      # several products share this name: the strength printed on the bill must pick one
                entry = [e for e in entry if nums & {float(STRENGTH_RE.match(x.rsplit(":", 1)[1])[1]) for x in e[0].split(";")}]
            if len(entry) == 1:
                hit = _decode(entry[0][0], form, entry[0][1], entry[0][2] if len(entry[0]) > 2 else 0)
                hit.mr_guess = guessed
                # A number we dropped must be a real strength of the product found ('TAXIM-O 50' must not become the
                # 25 mg Taxim-O); otherwise it named some other product that the table does not list.
                return hit if dropped <= {v for v, _ in hit.strengths} else None
            return None
        if not toks[-1][0].isdigit():
            return None
        dropped.add(float(toks[-1]))
        toks = toks[:-1]
    return None
