"""Parse NPPA gazette notifications of ceiling prices for IV fluids in packs 'with special features' (Eurohead bottles,
multi-port bags...). Each PDF has Table A (prices) and Table B (manufacturers/brands entitled to them).

  python3 -I scripts/parse_nppa_ivfluids.py data/nppa_ivfluids_special_2026-04.csv data/nppa_special_makers_2026-04.csv \
      "1 April 2026 (WPI-revised)" rl=my_data/ringer_lactate.pdf six=my_data/6-special-features.pdf eight=my_data/8-special-features.pdf

Checked, not trusted: serials in each table must run 1..N, every price numeric, every row mapped to a known fluid and a volume.
"""
import csv, re, sys
import pdfplumber

KEYS = [("rl", r"ringer"), ("dns", r"glucose.*sodium chloride"), ("ns", r"sodium chloride"), ("metro", r"metronidazole"),
        ("mannitol", r"mannitol"), ("d25", r"(dextrose|glucose).*25\s*%|25\s*%"), ("d5", r"(dextrose|glucose)"),
        ("cipro", r"ciprofloxacin")]


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def key_of(name, dosage):
    t = f"{name} {dosage}".lower()
    for k, pat in KEYS:
        if re.search(pat, t):
            return k
    return None


def parse_pdf(path):
    prices, makers = [], []
    with pdfplumber.open(path) as pdf:
        for pno, pg in enumerate(pdf.pages, 1):
            for table in pg.extract_tables():
                for r in table:
                    r = [clean(c) for c in r]
                    if not r or not re.fullmatch(r"\d+\.?", r[0]):
                        continue
                    serial = int(r[0].rstrip("."))
                    if len(r) >= 5 and re.fullmatch(r"\d+(?:\.\d+)?", r[4]):
                        name, dosage, unit, price = r[1], r[2], r[3], float(r[4])
                        k = key_of(name, dosage)
                        if k is None:
                            raise SystemExit(f"{path} serial {serial}: unknown fluid {name!r} {dosage!r}")
                        per_ml = unit.lower().startswith("per ml")
                        vm = re.search(r"in\s+(\d+)\s*ml\s+pack", dosage, re.I) if per_ml else re.search(r"(\d+)\s*ml", unit + " " + dosage, re.I)
                        if not vm:
                            raise SystemExit(f"{path} serial {serial}: no pack volume in {unit!r} / {dosage!r}")
                        vol = int(vm[1])
                        prices.append({"serial": serial, "key": k, "formulation": name, "dosage": dosage, "unit": unit, "volume_ml": vol,
                                       "per_ml": int(per_ml), "ceiling_price": price, "bag_price": round(price * vol, 2) if per_ml else price})
                    elif len(r) >= 3 and r[1]:
                        notes = "".join(re.findall(r"Note\s*\(([a-z])\)", r[1]))
                        makers.append({"serial": serial, "manufacturer": clean(re.sub(r"\[?\(?Note[^\]\)]*\)?\]?\s*(below\)?\]?)?", "", r[1])),
                                       "brand": r[2], "notes": notes})
    for name, rows in (("prices", prices), ("makers", makers)):
        s = [x["serial"] for x in rows]
        if s != list(range(1, len(s) + 1)):
            raise SystemExit(f"{path}: {name} serials are not 1..N: {s}")
    return prices, makers


if __name__ == "__main__":
    dp, dm, as_on, specs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    P, M = [], []
    for spec in specs:
        label, path = spec.split("=", 1)
        pr, mk = parse_pdf(path)
        print(f"{label}: {len(pr)} price rows, {len(mk)} manufacturers")
        P += [{"set": label, **x} for x in pr]
        M += [{"set": label, **x} for x in mk]
    with open(dp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["set", "serial", "key", "formulation", "dosage", "unit", "volume_ml", "per_ml", "ceiling_price", "bag_price", "as_on"])
        w.writeheader(); [w.writerow({**x, "as_on": as_on}) for x in P]
    with open(dm, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["set", "serial", "manufacturer", "brand", "notes"])
        w.writeheader(); w.writerows(M)
    print(f"{len(P)} price rows -> {dp}; {len(M)} manufacturers -> {dm}")
