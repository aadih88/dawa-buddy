"""Synthetic pharmacy bills in many layouts, with known answers, to test the bill reader beyond the few real bills there are.

  python3 scripts/synth_bills.py gen            # draws my_data/synth/<layout>.png and <layout>.json (the truth)
  python3 scripts/synth_bills.py eval [names]   # reads each image with the real reader (needs NEBIUS_API_KEY) and scores quantity and line value per row

Layouts differ in column names and order, per-tablet or per-strip MRP, tax-inclusive or split tax, stacked two-value cells, a discount column, no rate column,
and a tilted, blurred "photo". Medicine names are real brands; prices and quantities are random but seeded. This is a stress test of layouts, not a measure of
accuracy on real bills: the README says so.
"""
from __future__ import annotations
import json, pathlib, random, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "my_data" / "synth"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
NAMES = ["DOLO 650MG TAB", "PAN 40MG TAB", "TELMA 40 TAB", "AMLONG 5MG TAB", "ATORVA 10MG TAB", "AZITHRAL 500 TAB", "ONDEM 4MG TAB", "MONTEK LC TAB",
         "GLYCOMET 500 TAB", "CROCIN ADVANCE 500MG TAB", "ECOSPRIN 75 TAB", "RABEKIND 20 TAB", "LIMCEE 500MG CHEW TAB", "CALPOL 500MG TAB"]


def f(x): return f"{x:.2f}"


def items(rng, n):
    out = []
    for name in rng.sample(NAMES, n):
        pack = rng.choice([10, 10, 15, 14])
        unit = round(rng.uniform(1.2, 18), 2)                     # tax-inclusive price of one tablet
        out.append({"name": name, "pack": pack, "unit": unit, "qty": rng.choice([5, 6, 10, 10, 15, 20, 30]), "gst": rng.choice([5, 12])})
    return out


def table(rows, headers, stacked=False):
    return {"headers": headers, "rows": rows, "stacked": stacked}


def layout(name, rng):
    its = items(rng, rng.choice([4, 5, 6]))
    rows, truth = [], []
    for i, it in enumerate(its, 1):
        q, u, nm, pk, g = it["qty"], it["unit"], it["name"], it["pack"], it["gst"]
        amt = round(q * u, 2)
        if name == "simple":
            hd = ["#", "Item", "Qty", "Rate", "Amount"]; rows.append([i, nm, q, f(u), f(amt)])
        elif name == "mrp_tax":      # per-tablet MRP, tax inside, tax column shown
            hd = ["S.No", "Item", "Batch", "Qty", "MRP", "Discount", "Tax Name", "Tax", "NetAmt"]
            rows.append([i, nm, "K21%04d" % rng.randint(0, 9999), f(q), f(u), "0.00", f"GST {g} %", f(amt * g / (100 + g)), f(amt)])
        elif name == "strip_mrp":    # sold per strip, MRP per strip
            sq, sp = rng.choice([1, 2, 3]), round(u * pk, 2); amt = round(sq * sp, 2); q, u = sq, sp
            hd = ["#", "Item Description", "Pack", "Qty", "MRP", "Rate", "Amount"]; rows.append([i, nm, f"{pk}'s", sq, f(sp), f(sp), f(amt)])
        elif name == "tab_with_strip_mrp":
            hd = ["Sl", "Particulars", "Qty (tabs)", "Rate/tab", "MRP (strip)", "Value"]; rows.append([i, nm, q, f(u), f(round(u * pk * 1.1, 2)), f(amt)])
        elif name == "discount":
            d = rng.choice([5, 10, 15]); amt = round(q * u * (1 - d / 100), 2)
            hd = ["#", "Item", "Qty", "MRP", "Disc %", "Net Amt"]; rows.append([i, nm, q, f(u), f"{d}%", f(amt)])
        elif name == "scrambled":
            hd = ["Value", "Nos", "Particulars", "Price", "Exp"]; rows.append([f(amt), q, nm, f(u), "%02d-26" % rng.randint(1, 12)])
        elif name == "taxable_split":     # price printed before tax; the line total includes it
            base = round(u / (1 + g / 100), 2); tx = round(q * base, 2); half = round(tx * g / 200, 2); amt = round(tx + 2 * half, 2); u = round(amt / q, 4)
            hd = ["#", "Item", "Qty", "Rate", "Taxable", "CGST", "SGST", "Total"]; rows.append([i, nm, q, f(base), f(tx), f(half), f(half), f(amt)])
        elif name == "no_rate":
            hd = ["Sr", "Medicine", "Qty", "Amount"]; rows.append([i, nm, q, f(amt)])
        elif name == "stacked":           # two values in each cell, like some hospital software
            base = round(q * u / (1 + g / 100), 2); half = round(q * u - base, 2) / 2
            hd = ["#", "Item (Mfr)", "MRP/Unit (Net/Unit)", "Qty / Disc%", "Taxable", "CGST", "SGST", "Val In-GST"]
            rows.append([i, [nm, "H/3004/Maker Ltd"], [f(u), f(u)], [q, "0 %"], base, [f"{g/2:g} %", f(half)], [f"{g/2:g} %", f(half)], amt])
        elif name == "photo":
            hd = ["S.No", "Item", "Qty", "MRP", "Disc", "Tax", "NetAmt"]; rows.append([i, nm, f(q), f(u), "0.00", f(amt * g / (100 + g)), f(amt)])
        truth.append({"name": nm, "qty": q, "amount": amt})
    return hd, rows, truth, round(sum(t["amount"] for t in truth), 2)


NAMES_LAYOUT = ["simple", "mrp_tax", "strip_mrp", "tab_with_strip_mrp", "discount", "scrambled", "taxable_split", "no_rate", "stacked", "photo"]


def draw(hd, rows, total, photo=False):
    fn, fb = ImageFont.truetype(FONT, 26), ImageFont.truetype(FONT, 26)
    w, rh = 2200, 74
    img = Image.new("RGB", (w, 220 + rh * (len(rows) + 3)), (236, 234, 228))
    d = ImageDraw.Draw(img)
    d.text((40, 30), "CITY MEDICAL STORE   Invoice", fill=(20, 20, 20), font=fb)
    colw = [(w - 80) * wt / sum(ws) for ws in [[3 if h in ("Item", "Item Description", "Particulars", "Medicine", "Item (Mfr)") else 1.4 for h in hd]] for wt in ws]
    xs = [40 + sum(colw[:k]) for k in range(len(hd))]
    y = 130
    for x, h in zip(xs, hd): d.text((x, y), h, fill=(0, 0, 0), font=fb)
    d.line((40, y + 44, w - 40, y + 44), fill=(0, 0, 0), width=2)
    y += 54
    for r in rows:
        for x, c in zip(xs, r):
            if isinstance(c, list):
                d.text((x, y - 8), str(c[0]), fill=(10, 10, 10), font=fn); d.text((x, y + 24), str(c[1]), fill=(10, 10, 10), font=fn)
            else:
                d.text((x, y), str(c), fill=(10, 10, 10), font=fn)
        y += rh
    d.line((40, y, w - 40, y), fill=(0, 0, 0), width=2)
    d.text((xs[-1], y + 14), f"Total  {f(total)}" if len(hd) < 5 else f(total), fill=(0, 0, 0), font=fb)
    d.text((40, y + 64), f"Net payable: Rs {total:.0f}", fill=(0, 0, 0), font=fb)
    if photo:
        img = img.rotate(2.2, expand=True, fillcolor=(228, 226, 220)).filter(ImageFilter.GaussianBlur(1.1))
    return img


def gen():
    OUT.mkdir(parents=True, exist_ok=True)
    for k, name in enumerate(NAMES_LAYOUT):
        rng = random.Random(100 + k)
        hd, rows, truth, total = layout(name, rng)
        draw(hd, rows, total, photo=(name == "photo")).save(OUT / f"{name}.png")
        (OUT / f"{name}.json").write_text(json.dumps({"layout": name, "rows": truth, "total": total}, indent=1))
    print(f"{len(NAMES_LAYOUT)} bills -> {OUT}")


def evaluate(names):
    sys.path.insert(0, str(ROOT))
    from dawa_buddy import vision
    tot_rows = tot_ok = 0
    for name in names or NAMES_LAYOUT:
        gt = json.loads((OUT / f"{name}.json").read_text())
        try:
            rows, total = vision.read_bill_photo((OUT / f"{name}.png").read_bytes(), "image/png")
        except Exception as e:
            print(f"{name:20} read failed: {e}"); tot_rows += len(gt["rows"]); continue
        ok = 0
        for t, r in zip(gt["rows"], rows):
            good = r.qty is not None and r.amount is not None and abs(r.qty - t["qty"]) < 0.01 and abs(r.amount - t["amount"]) <= 0.06
            ok += good
            if not good:
                print(f"   {name}: wanted {t['name']} qty {t['qty']} amount {t['amount']}  got {r.description} qty {r.qty} amount {r.amount}")
        n = len(gt["rows"]); tot_rows += n; tot_ok += ok
        extra = "" if len(rows) == n else f"  (rows read {len(rows)}, expected {n})"
        print(f"{name:20} {ok}/{n} rows right; printed total {'ok' if total is not None and abs(total - gt['total']) <= 1 else 'WRONG ' + str(total) + ' vs ' + str(gt['total'])}{extra}")
    print(f"TOTAL {tot_ok}/{tot_rows} rows")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "gen"
    gen() if cmd == "gen" else evaluate(sys.argv[2:])
