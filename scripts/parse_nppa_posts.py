"""Parse NPPA category price posters (PDF, 'As on March 2026') into rows.

Layout (1152x648 pt pages): serial ~x84, name ~x156-400, dosage form+strength ~x400-800,
unit ~x802-960, ceiling price ~x966. A row is anchored by its price line; words between the
previous price line and this one (names/dosage can wrap above and below the serial) belong to it.
Usage: python3 -I scripts/parse_nppa_posts.py out.csv file1.pdf file2.pdf ...
"""
import csv, re, sys, pdfplumber

PRICE = re.compile(r"^\d+(?:\.\d+)?$")


def parse_pdf(path, category):
    out = []
    with pdfplumber.open(path) as pdf:
        for pno, pg in enumerate(pdf.pages, 1):
            words = pg.extract_words()
            prices = sorted([w for w in words if w["x0"] > 940 and PRICE.match(w["text"])], key=lambda w: w["top"])
            prev_y = -1
            for pw in prices:
                y = pw["top"]
                band = [w for w in words if prev_y + 1 < w["top"] <= y + 6 and w["x0"] < 940 and not w["text"].startswith("*As")]
                prev_y = y + 6
                serial = next((w for w in band if w["x0"] < 120 and w["text"].isdigit()), None)
                name = " ".join(w["text"] for w in sorted([w for w in band if 120 <= w["x0"] < 400], key=lambda w: (round(w["top"] / 6), w["x0"])))
                dose = " ".join(w["text"] for w in sorted([w for w in band if 400 <= w["x0"] < 800], key=lambda w: (round(w["top"] / 6), w["x0"])))
                unit = " ".join(w["text"] for w in sorted([w for w in band if 800 <= w["x0"] < 940], key=lambda w: w["x0"]))
                out.append({"category": category, "page": pno, "serial": serial["text"] if serial else "",
                            "formulation": name.strip(), "dosage": dose.strip(), "unit": unit.strip(),
                            "ceiling_price": float(pw["text"]), "as_on": "March 2026"})
    return out


if __name__ == "__main__":
    dest, files = sys.argv[1], sys.argv[2:]
    rows = []
    for f in files:
        cat = re.search(r"posts-([a-z\-]+?)-[0-9a-f]{32}", f).group(1)
        r = parse_pdf(f, cat); print(f"{cat}: {len(r)} rows"); rows += r
    with open(dest, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
