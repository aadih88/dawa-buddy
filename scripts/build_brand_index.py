"""Build data/brand_index.json from a public brand table CSV.

  python scripts/build_brand_index.py path/to/indian_medicine_data.csv

Source used: github.com/junioralive/Indian-Medicine-Dataset (MIT licence; ~254k allopathic brands, prices as of 2022).
Only brand -> composition (and the usual units per pack, when unambiguous) is kept. Its prices are years old and are NOT used for any judgement.
Keeps tablets, capsules, injections, oral liquids and topicals whose every strength parses. Eye/ear/nasal products,
infusions, shampoos and soaps are skipped. Liquids/topicals resolve to a composition only: they have no per-unit benchmark yet.
"""
import csv, json, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from dawa_buddy.brand_table import INDEX_PATH, norm_salt, tokens

MR = re.compile(r"\b(sr|xr|cr|er|mr|retard|prolonged|modified)\b", re.I)


SKIP = re.compile(r"eye|ear\b|ophthalmic|nasal|infusion|shampoo|soap|spray|inhal|respule|powder for")
COMP = re.compile(r"(.+?)\s*\(\s*(\d+(?:\.\d+)?)\s*(mg|mcg|gm|g|iu|%)\s*(?:/\s*(\d+(?:\.\d+)?)?\s*(ml|gm|g))?\s*(?:w/w|w/v|v/v)?\s*\)", re.I)


def form_of(pack: str) -> str | None:
    p = pack.lower()
    if SKIP.search(p):
        return None
    for form, words in (("injection", ("injection",)), ("tablet", ("tablet",)), ("capsule", ("capsule",)),
                        ("liquid", ("syrup", "suspension", "oral solution", "oral drops", "expectorant")),
                        ("topical", ("cream", "ointment", "gel", "lotion"))):
        if any(w in p for w in words):
            return form
    return None


def pack_of(label: str) -> int:
    """Units per pack from 'strip of 15 tablets' / 'strip of 10 capsule sr'; 0 when the label gives no count."""
    m = re.match(r"(?:strip|bottle) of (\d+)\s*(?:tablet|capsule|soft)", label.lower())
    return int(m[1]) if m else 0


def composition(r) -> str | None:
    parts = []
    for c in (r["short_composition1"], r["short_composition2"]):
        c = (c or "").strip()
        if not c:
            continue
        m = COMP.fullmatch(c)
        if not m:
            return None
        unit = "g" if m[3].lower() == "gm" else m[3].lower()
        den = f"/{float(m[4] or 1):g}{m[5].lower().replace('gm', 'g')}" if m[5] else ""
        parts.append(f"{norm_salt(m[1])}:{float(m[2]):g}{unit}{den}")
    return ";".join(parts) or None


def main(path):
    idx: dict = {}
    n = skipped = 0
    for r in csv.DictReader(open(path, encoding="utf-8")):
        form, comp = form_of(r["pack_size_label"]), composition(r)
        key = " ".join(tokens(r["name"]))
        if not (form and comp and key):
            skipped += 1
            continue
        entry = [comp, int(bool(MR.search(r["name"]))), pack_of(r["pack_size_label"])]
        slot = idx.setdefault(key, {}).setdefault(form, [])
        same = next((e for e in slot if e[:2] == entry[:2]), None)
        if same is None:
            slot.append(entry)
        elif same[2] != entry[2]:
            same[2] = 0          # the same product is sold in different pack sizes: do not suggest one
        n += 1
    INDEX_PATH.write_text(json.dumps(idx, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    amb = sum(1 for v in idx.values() for f in v.values() if len(f) > 1)
    print(f"{n} rows indexed under {len(idx)} names ({amb} ambiguous), {skipped} skipped -> {INDEX_PATH}")


main(sys.argv[1])
