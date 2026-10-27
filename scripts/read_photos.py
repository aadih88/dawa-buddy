"""Read bill / prescription photos with the vision model and write editable text files for review.

  export NEBIUS_API_KEY=...            # or DAWA_PROVIDER=ollama DAWA_VISION_MODEL=...
  python scripts/read_photos.py --bill my_data/bill.JPG --rx my_data/prescription.JPG
        -> my_data/<photo name>_read.txt for each photo   (compare with the paper, fix, then rename to bill.txt / rx.txt)
  python scripts/read_photos.py --bill my_data/bill.JPG --truth my_data/bill.txt
        -> also scores the transcription against a bill.txt you typed by hand from the paper

The model only transcribes. Nothing is audited here; run scripts/audit_bill.py on the reviewed text afterwards.
"""
import argparse, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from dawa_buddy import bill as b, llm, vision


def fmt(v):
    return "" if v is None else f"{v:g}"


def row_text(r):
    return " | ".join([r.description, fmt(r.qty), fmt(r.rate), fmt(r.amount), r.unit or "", fmt(r.pack), fmt(r.mrp)]).rstrip(" |")


def score(rows, truth_lines):
    """Match each hand-typed line to the transcribed row with the same amount, then compare fields."""
    fields = ("qty", "rate", "amount", "unit", "pack")
    hit = {f: 0 for f in fields}
    found = 0
    for t in truth_lines:
        cand = [r for r in rows if r.amount is not None and abs(r.amount - t.amount) < 0.01]
        if not cand:
            print(f"  MISSING   {t.desc} (amount {t.amount:g})")
            continue
        r = cand[0]
        found += 1
        got = {"qty": r.qty, "rate": r.rate, "amount": r.amount, "unit": r.unit, "pack": r.pack}
        want = {"qty": t.qty, "rate": t.rate, "amount": t.amount, "unit": t.unit, "pack": t.pack}
        for f in fields:
            ok = (got[f] == want[f]) if f in ("unit",) else (got[f] == want[f] or (got[f] is None and want[f] is None))
            hit[f] += ok
            if not ok:
                print(f"  DIFFERENT {t.desc}: {f} read={got[f]} paper={want[f]}")
    n = len(truth_lines)
    print(f"\nlines found by amount: {found}/{n}; extra rows read: {max(0, len(rows) - found)}")
    print("field accuracy on found lines: " + ", ".join(f"{f} {hit[f]}/{found}" for f in fields))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bill")
    ap.add_argument("--rx")
    ap.add_argument("--truth", help="a hand-typed bill.txt for the same bill, to score the transcription")
    a = ap.parse_args()
    if not llm.vision_available():
        sys.exit("No vision model configured. Set NEBIUS_API_KEY (DAWA_PROVIDER=nebius) or DAWA_PROVIDER=ollama with DAWA_VISION_MODEL.")
    print("provider:", llm.provider(), "| vision model:", llm.vision_model())
    if a.bill:
        p = pathlib.Path(a.bill)
        rows, total = vision.read_bill_photo(p.read_bytes(), "image/jpeg")
        out = ["# Read from photo. CHECK EVERY NUMBER AGAINST THE PAPER, then save as bill.txt",
               "# description | qty | rate | amount | unit | pack | mrp", f"# printed total read: {fmt(total)}"]
        for r in rows:
            usable = None not in (r.qty, r.rate, r.amount)
            out.append(("" if usable else "# NEEDS FIX: ") + row_text(r) + ("   # unsure: " + "; ".join(r.notes) if r.unsure or r.notes else ""))
        dest = p.with_name(p.stem + "_read.txt")
        dest.write_text("\n".join(out) + "\n")
        print(f"{len(rows)} bill rows -> {dest}  (printed total read: {fmt(total)}; {sum(1 for r in rows if r.unsure)} marked unsure)")
        if a.truth:
            truth, rej = b.parse_bill_ex(pathlib.Path(a.truth).read_text())
            score(rows, truth)
    if a.rx:
        p = pathlib.Path(a.rx)
        text = vision.read_rx_photo(p.read_bytes(), "image/jpeg")
        dest = p.with_name(p.stem + "_read.txt")
        dest.write_text(text + "\n")
        print(f"{len(text.splitlines())} prescription lines -> {dest}")


main()
