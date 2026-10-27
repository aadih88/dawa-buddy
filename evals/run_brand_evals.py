"""Brand resolution accuracy: python -m evals.run_brand_evals [--verbose]

Runs the gold set through the real audit path (resolve + supplement rule), with and without the brand table, so the
table's contribution is measured. 'wrong' is the number that matters: a wrong salt can create a false price accusation.
"""
import sys
from dawa_buddy import bill as b, benchmarks as ja
from .brands_gold import CASES

JUDGED = {b.TIER_ABOVE_CEILING, b.TIER_GENERIC_GAP, b.TIER_OK, b.TIER_DOCTOR_ONLY}


def same(got_salts: str, got_st, want) -> bool:
    ws = ja.parse_ingredients(" and ".join(s for s, _ in want))
    return ja.parse_ingredients(got_salts.replace("+", " and ")) == ws and \
        sorted(float(v) for v, _ in got_st) == sorted(float(v) for _, v in want)


def run(use_table: bool):
    saved = b.brand_lookup
    if not use_table:
        b.brand_lookup = lambda *a, **k: None
    try:
        out = []
        for desc, want, required in CASES:
            r = b.resolve(desc)
            tier = b.audit_line(b.BillLine(desc, desc, 1, 10.0, 10.0, "tab")).tier
            if want is None:
                status = "ok" if tier not in JUDGED else "wrong"
            elif r is None:
                status = "missed" if required else "ok_unresolved"
            else:
                status = "correct" if same(r[0], r[1], want) else "wrong"
            if status == "wrong" and tier in JUDGED:
                status = "WRONG+JUDGED"      # a wrong salt that reached a price verdict: the harmful case
            out.append((desc, want, r, status))
        return out
    finally:
        b.brand_lookup = saved


def main():
    verbose = "--verbose" in sys.argv
    res = {}
    for name, flag in (("curated map only", False), ("with brand table", True)):
        rows = run(flag)
        res[name] = rows
        pos = [x for x in rows if x[1] is not None]
        cnt = lambda s, xs=rows: sum(1 for x in xs if x[3] == s)
        print(f"{name:18} positives={len(pos)}  correct={cnt('correct')}  missed={cnt('missed')}  "
              f"WRONG={cnt('wrong') + cnt('WRONG+JUDGED')}  of which reached a price verdict={cnt('WRONG+JUDGED')}  negatives ok={sum(1 for x in rows if x[1] is None and x[3]=='ok')}/{sum(1 for x in rows if x[1] is None)}")
    for desc, want, r, status in res["with brand table"]:
        if status in ("wrong", "WRONG+JUDGED", "missed") or verbose:
            print(f"  {status:13} {desc:26} want={want}  got={(r[0], r[1]) if r else None}")


if __name__ == "__main__":
    main()
