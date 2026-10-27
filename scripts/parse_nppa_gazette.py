"""Parse an NPPA gazette notification of revised ceiling prices (PDF table) into the CSV the app loads.

  python3 -I scripts/parse_nppa_gazette.py data/nppa_ceiling_2026-04.csv "1 April 2026 (WPI-revised)" \\
      nlem2022=my_data/NPPA-ceilings.pdf nlem2015=my_data/138-drug-revision.pdf nlem2011=my_data/six-drug-revision.pdf

Columns: Sl. No. | Medicines | Dosage form and strength | Unit | Ceiling price | Existing S.O. no. | date.
The parse is checked, not trusted: in each file serials must run 1..N without gaps and every price must be a number, else it aborts.
Each PDF's rows get its label (nlem2022, nlem2015, nlem2011) as `category`.
"""
import csv, re, sys
import pdfplumber

HEAD = ("Sl.", "(1)")


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def parse(path):
    rows = []
    with pdfplumber.open(path) as pdf:
        for pno, pg in enumerate(pdf.pages, 1):
            for table in pg.extract_tables():
                for r in table:
                    r = [clean(c) for c in r]
                    if not r or not r[0].isdigit() or len(r) < 5:
                        continue
                    price = r[4].replace(",", "")
                    if not re.fullmatch(r"\d+(?:\.\d+)?", price):
                        raise SystemExit(f"page {pno}: serial {r[0]} has a non-numeric price {r[4]!r}")
                    rows.append({"serial": int(r[0]), "page": pno, "formulation": r[1], "dosage": r[2], "unit": r[3],
                                 "ceiling_price": float(price), "so": " ".join(x for x in r[5:] if x)})
    # Rows with merged cells (e.g. 'Condoms 11.65' with no dosage/unit) escape table extraction: recover them from the text lines.
    have = {r["serial"] for r in rows}
    with pdfplumber.open(path) as pdf:
        for pno, pg in enumerate(pdf.pages, 1):
            for ln in (pg.extract_text() or "").splitlines():
                m = re.match(r"^(\d+) (.+?) (\d+\.\d+) (\d+\(E\)) (\d\d-\d\d-\d{4})$", ln.strip())
                if m and int(m[1]) not in have and int(m[1]) <= max(have | {0}) + 5:
                    have.add(int(m[1]))
                    rows.append({"serial": int(m[1]), "page": pno, "formulation": clean(m[2]), "dosage": "", "unit": "",
                                 "ceiling_price": float(m[3]), "so": f"{m[4]} {m[5]}"})
    rows.sort(key=lambda r: r["serial"])
    serials = [r["serial"] for r in rows]
    if serials != list(range(1, len(serials) + 1)):
        gaps = sorted(set(range(1, max(serials) + 1)) - set(serials))
        raise SystemExit(f"serials are not 1..N: {len(serials)} rows, missing {gaps[:20]}")
    return rows


if __name__ == "__main__":
    dest, as_on, specs = sys.argv[1], sys.argv[2], sys.argv[3:]
    out = []
    for spec in specs:
        label, path = spec.split("=", 1)
        rows = parse(path)
        print(f"{label}: {len(rows)} rows from {path}")
        out += [(label, r) for r in rows]
    with open(dest, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["category", "page", "serial", "formulation", "dosage", "unit", "ceiling_price", "as_on"])
        for label, r in out:
            w.writerow([label, r["page"], r["serial"], r["formulation"], r["dosage"], r["unit"], r["ceiling_price"], as_on])
    print(f"{len(out)} rows -> {dest}")
