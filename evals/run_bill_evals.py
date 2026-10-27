import sys
from dawa_buddy import bill as b
from evals.bills_gold import BILLS

ok = tot = 0
for case in BILLS:
    fs = b.audit(case["text"])
    for f in fs:
        exp = case["expected"].get(f.line.desc)
        tot += 1; ok += (f.tier == exp)
        flag = "OK " if f.tier == exp else "MISS"
        print(f"{flag} {case['id'][:22]:22s} {f.line.desc[:26]:26s} got={f.tier:16s} exp={exp}")
print(f"\nTier accuracy on synthetic bills: {ok}/{tot}")
sys.exit(0 if ok == tot else 1)
