"""Run the pipeline over the gold set and report extraction and safety quality.
Usage: python -m evals.run_evals [--out evals/results.md]
Offline mode (no NEBIUS_API_KEY) measures the rule-based baseline; with a key it measures the model."""
import argparse, time
from dawa_buddy import llm
from dawa_buddy.pipeline import run
from evals.gold import CASES


def norm(name):
    return name.lower().split()[0] if name else ""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=None); a = ap.parse_args()
    mode = "offline (rule-based baseline)" if llm.is_offline() else f"{llm.provider()}: {llm.model_name()}"
    f_tp = f_fp = f_fn = 0   # medicine-field tuples
    s_tp = s_fp = s_fn = 0   # safety flag titles
    hallucinated = 0; rows = []; lat = []
    for c in CASES:
        t0 = time.time()
        try:
            b = run(c["text"], "en")
        except Exception as e:
            rows.append((c["id"], f"ERROR {e}", "", "")); f_fn += len(c["meds"]); s_fn += len(c["flags"]); continue
        lat.append(time.time() - t0)
        got = {(norm(m.name), m.frequency, m.duration_days) for m in b.prescription.medications}
        exp = {(n, f, d) for n, f, d in c["meds"]}
        f_tp += len(got & exp); f_fp += len(got - exp); f_fn += len(exp - got)
        names_in_text = c["text"].lower()
        hallucinated += sum(1 for m in b.prescription.medications if norm(m.name) not in names_in_text)
        gf = {f.title for f in b.flags if f.severity != "info" or f.title in c["flags"]}
        s_tp += len(gf & c["flags"]); s_fp += len(gf - c["flags"]); s_fn += len(c["flags"] - gf)
        rows.append((c["id"], f"{len(got & exp)}/{len(exp)}", ", ".join(sorted(gf)) or "-", ", ".join(sorted(c["flags"])) or "-"))
    def prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 1.0; r = tp / (tp + fn) if tp + fn else 1.0
        return p, r, (2 * p * r / (p + r) if p + r else 0.0)
    fp_, fr_, ff_ = prf(f_tp, f_fp, f_fn); sp_, sr_, sf_ = prf(s_tp, s_fp, s_fn)
    out = [f"# Eval results\n", f"Mode: {mode}  |  Cases: {len(CASES)}\n",
           f"| Metric | Precision | Recall | F1 |\n|---|---|---|---|",
           f"| Medicine extraction (name, frequency, days) | {fp_:.2f} | {fr_:.2f} | {ff_:.2f} |",
           f"| Safety flags | {sp_:.2f} | {sr_:.2f} | {sf_:.2f} |\n",
           f"Hallucinated medicines (not in source text): {hallucinated}",
           f"Median latency: {sorted(lat)[len(lat)//2]:.2f}s\n" if lat else "",
           "| Case | Meds correct | Flags raised | Flags expected |\n|---|---|---|---|"]
    out += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows]
    text = "\n".join(out); print(text)
    if a.out: open(a.out, "w").write(text + "\n")


if __name__ == "__main__":
    main()
