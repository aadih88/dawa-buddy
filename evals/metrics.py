"""Reader scoring shared by run_evals and verify_ollama: dev vs held-out F1, plus timing accuracy."""
from evals.gold import CASES


def key(m):
    return (m.name.lower().split()[0], m.frequency, m.duration_days)


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0; r = tp / (tp + fn) if tp + fn else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def score_reader(read_fn, cases=CASES):
    """read_fn(text) -> Prescription. Returns {'dev': (p,r,f1), 'heldout': (...), 'timing': (right, total), 'invented': n}."""
    acc = {"dev": [0, 0, 0], "heldout": [0, 0, 0]}
    t_ok = t_all = invented = 0
    diffs = []
    for c in cases:
        part = c.get("set", "dev")
        exp = {(n, f, d) for n, f, d in c["meds"]}
        try:
            rx = read_fn(c["text"])
        except Exception:
            acc[part][2] += len(exp); continue
        got = {key(m) for m in rx.medications}
        acc[part][0] += len(got & exp); acc[part][1] += len(got - exp); acc[part][2] += len(exp - got)
        invented += sum(1 for m in rx.medications if m.name.lower().split()[0] not in c["text"].lower())
        for name, want in c.get("timing", {}).items():
            t_all += 1
            t_ok += any(m.name.lower().split()[0] == name and m.timing == want for m in rx.medications)
        if got != exp:
            diffs.append((c["id"], part, sorted(exp - got, key=str), sorted(got - exp, key=str)))
    return {"dev": prf(*acc["dev"]), "heldout": prf(*acc["heldout"]), "timing": (t_ok, t_all),
            "invented": invented, "diffs": diffs}
