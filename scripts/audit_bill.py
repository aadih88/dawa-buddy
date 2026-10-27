"""Audit a bill (and optionally a prescription) from text files.

  python scripts/audit_bill.py --bill my_data/bill.txt --rx my_data/rx.txt [--total 1234.50]
        [--confirm "TELMA 40=telmisartan"] [--out my_data/report.md]
Set DAWA_PROVIDER=offline to skip the model; ollama or nebius to let it suggest salts for unknown brands.
"""
import argparse, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from dawa_buddy import bill as b, webcheck
from dawa_buddy.reader import read_prescription
from dawa_buddy.reconcile import reconcile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bill", required=True)
    ap.add_argument("--rx")
    ap.add_argument("--total", type=float)
    ap.add_argument("--confirm", action="append", default=[], help='"BILL DESCRIPTION=salt" (repeatable)')
    ap.add_argument("--lookup", action="store_true", help="web-check unidentified brands (needs TAVILY_API_KEY); evidence only")
    ap.add_argument("--out")
    a = ap.parse_args()
    text = pathlib.Path(a.bill).read_text()
    confirmed = {k.strip().lower(): v.strip().lower() for k, v in (c.split("=", 1) for c in a.confirm)}
    lines, rejects = b.parse_bill_ex(text)
    fs = [b.audit_line(l, confirmed) for l in lines]
    out = []
    out.append(f"{'ITEM':28} {'TIER':19} {'PAID/u':>7} {'CEIL':>7} {'GENERIC':>7}  NOTE")
    for f in fs:
        n = lambda x: f"{x:7.2f}" if x is not None else "      -"
        out.append(f"{f.line.desc[:28]:28} {f.tier:19} {n(f.unit_price)} {n(f.ceiling)} {n(f.generic_unit)}  {f.note[:70]}")
    tot = sum(f.line.amount for f in fs) or 1
    out.append("\nSHARE OF BILL VALUE BY TIER")
    by = {}
    for f in fs:
        by[f.tier] = by.get(f.tier, 0) + f.line.amount
    for t, v in sorted(by.items(), key=lambda x: -x[1]):
        out.append(f"  {t:19} {v:10.2f}  {100*v/tot:5.1f}%")
    judged = sum(v for t, v in by.items() if t in (b.TIER_ABOVE_CEILING, b.TIER_GENERIC_GAP, b.TIER_OK, b.TIER_DOCTOR_ONLY, b.TIER_ABOVE_MRP))
    out.append(f"  -> value the tool could actually judge against a price list: {100*judged/tot:.1f}%")
    mrp_ok = sum(f.line.amount for f in fs if f.mrp_pct is not None)
    out.append(f"  -> value checked against the printed MRP: {100*mrp_ok/tot:.1f}% "
               f"({', '.join(f'{f.line.desc} at {f.mrp_pct:.0f}% of MRP' for f in fs if f.mrp_pct is not None)})")
    s = b.summary(fs)
    out.append(f"\nPossible saving above ceiling: {s['possible_saving_above_ceiling']:.2f}   "
               f"possible saving via generics (a question for your doctor): {s['possible_saving_generic']:.2f}")
    if s["needs_confirmation"]:
        out.append("\nNEEDS YOUR CONFIRMATION (read the salt off the strip, then pass --confirm):")
        for f in fs:
            if f.tier == b.TIER_NEEDS_CONFIRM:
                out.append(f"  {f.line.desc}  model guess: {f.ingredients}")
    if a.lookup:
        out.append("\nWEB EVIDENCE (read the strip before relying on it; no price judgement uses this):")
        for f in fs:
            if f.tier in (b.TIER_NEEDS_CONFIRM, b.TIER_NO_BENCHMARK) and not f.line.desc.lower() in confirmed:
                ev = webcheck.lookup_brand(f.line.desc) if webcheck.available() else None
                if ev is None:
                    out.append("  (set TAVILY_API_KEY to enable)")
                    break
                out.append(f"  {f.line.desc}: " + (webcheck.show(ev.consensus) if ev.consensus else "no agreement") + f"  [{len(ev.sources)} pages]")
                out += [f"      {s.url}" for s in ev.sources[:3]]
    if rejects:
        out.append(f"\nUNREADABLE LINES ({len(rejects)}) - not audited:")
        out += [f"  {r}" for r in rejects]
    if a.rx:
        rx = read_prescription(pathlib.Path(a.rx).read_text())
        out.append(f"\nPRESCRIPTION READ: {len(rx.medications)} medicines")
        for m in rx.medications:
            out.append(f"  {m.name} {m.strength or ''} freq={m.frequency} days={m.duration_days} timing={m.timing}")
        fl = reconcile(rx, lines, a.total)
        out.append("\nPRESCRIPTION vs BILL")
        out += [f"  [{x.kind}] {x.subject}: {x.note}" for x in fl] or ["  no differences found"]
    elif a.total:
        s2 = sum(l.amount for l in lines)
        out.append(f"\nLines sum {s2:.2f} vs printed total {a.total:.2f}")
    txt = "\n".join(out)
    print(txt)
    if a.out:
        pathlib.Path(a.out).write_text(txt)


main()
