"""Hindi / Kannada explainer check (needs NEBIUS_API_KEY): python -m evals.run_lang_evals [--out evals/results_lang.md]

For each language, runs the real explainer on two prescriptions and reports whether the answer was accepted (right script, no stray
scripts, one entry per medicine), which model won, whether it fell back to English, and latency. Script purity is machine-checked;
whether the Hindi and Kannada are GOOD still needs a native speaker.
"""
import json, os, sys, time
from dawa_buddy import llm
from dawa_buddy.explainer import NATIVE, explain, native_ok, script_counts
from dawa_buddy.reader import read_offline

CASES = {
    "three common tablets": "Tab Telma 40 mg 1-0-0 x 30 days\nTab Dolo 650 mg 1-0-1 x 5 days after food\nTab Atorva 10 mg 0-0-1 x 30 days",
    "heart and diabetes": "Tab Ecosprin 75 mg 0-0-1 x 30 days\nTab Metformin 500 mg 1-0-1 x 30 days after food\nTab Concor 5 mg 1-0-0 x 30 days\nTab Pantop 40 mg 1-0-0 x 30 days before food",
}


def main():
    os.environ["DAWA_KN_MODEL_TEXT"] = "1"      # measure the opt-in Kannada path; users do not get it by default (see explainer.model_text_langs)
    if llm.is_offline():
        sys.exit("Set NEBIUS_API_KEY: this evaluation calls the live models.")
    rows = []
    for lang in NATIVE:
        for case, text in CASES.items():
            rx = read_offline(text)
            t = time.time()
            out = explain(rx, lang)
            fell_back = any(e.language_fallback for e in out)
            tgt = other = 0
            if not fell_back:
                for e in out:
                    a, b = script_counts(f"{e.purpose} {e.how_to_take} {e.watch_for}", lang)
                    tgt, other = tgt + a, other + b
            rows.append((lang, case, len(rx.medications), "English fallback" if fell_back else "accepted",
                         "-" if fell_back else f"{tgt} / {other}", f"{time.time() - t:.1f}s"))
            print(rows[-1])
    lines = ["# Hindi / Kannada explainer: live check", "", f"Models: hi {NATIVE['hi'][3]}, kn {NATIVE['kn'][3]}", "",
             "| Language | Case | Medicines | Outcome | Target-script / stray-script letters | Latency |", "|---|---|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |" for r in rows]
    lines += ["", "Machine-checked for script only. A native speaker has not yet reviewed the wording.",
              "Kannada AI text is switched off for users by default: a real run passed this script check yet contained place names and 'Friday' as side effects."]
    if "--out" in sys.argv:
        open(sys.argv[sys.argv.index("--out") + 1], "w", encoding="utf-8").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
