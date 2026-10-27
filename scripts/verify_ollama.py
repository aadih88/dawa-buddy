"""Local verification of Dawa Buddy against an Ollama model.

  ollama pull nemotron-3-nano:4b          # or any model you want to test
  DAWA_PROVIDER=ollama OLLAMA_MODEL=nemotron-3-nano:4b python scripts/verify_ollama.py

Checks: (1) server + model present, (2) JSON reliability, (3) prescription reader vs rule baseline,
(4) model-assisted bill-line resolver on brands NOT in our brand table, with hallucination rejection,
(5) latency. Writes evals/ollama_<model>.md. Nothing leaves your machine.
"""
import json, os, statistics, sys, time
import httpx

os.environ.setdefault("DAWA_PROVIDER", "ollama")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dawa_buddy import llm, bill                         # noqa: E402
from dawa_buddy.reader import read_prescription, read_offline   # noqa: E402
from dawa_buddy import reader                              # noqa: E402
from evals.gold import CASES                              # noqa: E402
from evals.metrics import score_reader                      # noqa: E402

HELD_OUT = [("CONCOR 5 TAB", "bisoprolol"), ("LASIX 40 TAB", "furosemide"), ("ZYLORIC 100 TAB", "allopurinol"),
            ("CARDACE 5 TAB", "ramipril"), ("ZOFER 4 TAB", "ondansetron"), ("CIFRAN 500 TAB", "ciprofloxacin"),
            ("TAXIM-O 200 TAB", "cefixime"), ("LEVIPIL 500 TAB", "levetiracetam"), ("DYTOR 10 TAB", "torsemide"),
            ("NEXITO 10 TAB", "escitalopram")]
FAKE = ["ZYXOMAB 40 TAB", "QWERTYLIN 10 TAB"]   # invented names: the right answer is 'no match'


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0; r = tp / (tp + fn) if tp + fn else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main():
    model = llm.OLLAMA_MODEL
    out = [f"# Ollama verification: {model}\n"]
    # 1. server + model
    try:
        tags = httpx.get(llm.OLLAMA_HOST.rstrip("/") + "/api/tags", timeout=10).json()
        names = [m["name"] for m in tags.get("models", [])]
    except Exception as e:
        sys.exit(f"Cannot reach Ollama at {llm.OLLAMA_HOST}: {e}\nStart it with `ollama serve`.")
    if not any(n == model or n.startswith(model) for n in names):
        sys.exit(f"Model '{model}' not installed. Installed: {names}\nRun: ollama pull {model}")
    out.append(f"Server OK. Installed models: {', '.join(names)}\n")

    # 2+3. reader: model-assisted hybrid vs rules only, dev vs held-out
    reader.LAST_MODEL_OUTPUT.clear(); calls = []
    def hybrid(text):
        r = read_prescription(text); calls.extend(reader.LAST_MODEL_OUTPUT); return r
    t0 = time.time(); H = score_reader(hybrid); dt = time.time() - t0
    R = score_reader(read_offline)
    out += [f"## Prescription reader ({len(CASES)} synthetic cases: dev + held-out)",
            f"- Rules only   : dev F1 {R['dev'][2]:.2f} | held-out F1 {R['heldout'][2]:.2f} | timing {R['timing'][0]}/{R['timing'][1]}",
            f"- Hybrid+model : dev F1 {H['dev'][2]:.2f} | held-out F1 {H['heldout'][2]:.2f} | timing {H['timing'][0]}/{H['timing'][1]}",
            f"- Medicines not in the source text (hallucinated): {H['invented']}",
            f"- Lines sent to the model (rules handle the rest): {len(calls)}",
            f"- Total time for all cases: {dt:.1f}s\n"]

    # 4. bill-line resolver on unseen brands (+ invented names must be rejected)
    right = wrong = none = 0; bill.LAST_RAW.clear()
    for desc, salt in HELD_OUT:
        r = bill.resolve_with_model(desc)
        if r is None: none += 1
        elif r[0] == salt: right += 1
        else: wrong += 1; print("wrong:", desc, "->", r[0])
    rejected = sum(1 for d in FAKE if bill.resolve_with_model(d) is None)
    ceiling = sum(1 for desc, salt in HELD_OUT if salt in bill.candidate_salts(bill.desc_strengths(desc)))
    out += [f"## Bill-line resolver on {len(HELD_OUT)} unseen brands",
            f"- Correct salt AND present in price lists: {right}  | wrong salt: {wrong}  | no verified match: {none}",
            f"- Invented brand names correctly rejected: {rejected}/{len(FAKE)}",
            f"- Ceiling: true salt is among the candidates for {ceiling}/{len(HELD_OUT)} (it cannot do better than this)",
            "- ('no verified match' includes true salts absent from our two price lists; that is the safe failure.)\n"]
    out.append("## Diagnostics: reader mismatches (hybrid)")
    for cid, part, missing, extra in H["diffs"]:
        out.append(f"- {cid} [{part}]: missing {missing} | extra {extra}")
    for line, data in calls:
        out.append(f"    model saw: {line!r} -> {json.dumps(data)[:260]}")
    out.append("\n## Diagnostics: raw model answers for unseen brands")
    for desc, d, n in bill.LAST_RAW:
        out.append(f"- {desc!r} ({n} candidates) -> {json.dumps(d)[:200]}")
    text = "\n".join(out); print("\n" + text)
    safe = model.replace(":", "_").replace("/", "_")
    open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evals", f"ollama_{safe}.md"), "w").write(text)


if __name__ == "__main__":
    main()
