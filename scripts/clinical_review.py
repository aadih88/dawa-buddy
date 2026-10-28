"""Second-opinion review of the English medicine table (medinfo.MEDS) by one or more models. No human review is claimed.

  python3 scripts/clinical_review.py export                    # writes my_data/clinical_review/table.json and prompt.md (paste into any chat model)
  python3 scripts/clinical_review.py ask --model <id> [...]    # asks a model on Nebius Token Factory, saves answers_<id>.json
  python3 scripts/clinical_review.py diff                      # reads every answers_*.json, lists what to look at by hand

Why English only: whether "pantoprazole is for acid" is right does not depend on the language, and a model is far more reliable on that than on
Kannada grammar. Use a model from a different family than the one that wrote the table; disagreement between reviewers is the signal.
The output is a triage list: a person (or a stricter pass) still decides each flagged entry. Nothing here edits medinfo.py.
"""
from __future__ import annotations
import argparse, concurrent.futures as cf, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dawa_buddy import medinfo as M

OUT = ROOT / "my_data" / "clinical_review"
BATCH = 8

RUBRIC = """You are checking short patient-information text for an Indian medicine app. The text is meant for lay readers and gives no dose advice.
For EACH ingredient below you get: the one-line purpose, the side effects listed, and the warning sentences listed (each has an id).
Answer three separate questions per ingredient:
1. purpose: "ok" if the purpose sentence matches what this drug is mainly prescribed for; "incomplete" if true but leaves out a major common use;
   "wrong" if it is inaccurate or misleading.
2. missing: serious or common safety points that standard labelling (CDSCO / BNF / FDA label) would list and that NONE of the warnings cover.
   Only real gaps, e.g. a pregnancy contraindication, a bleeding risk, a dangerous interaction, driving. Do not pad. Use [] if nothing important is missing.
3. wrong: ids of listed warnings or side effects that are inaccurate for THIS drug, or too strong or too weak to be safe. Use [] if none.
Also "note": one short sentence, only if useful, else "".
Do not suggest dose advice, and do not rewrite the text. Be strict, but report only what you are confident about.
Reply with ONLY a JSON list, one object per ingredient, in the same order:
[{"ingredient": str, "purpose": "ok"|"incomplete"|"wrong", "missing": [str], "wrong": [str], "note": str}]"""


def table() -> list[dict]:
    rows = []
    for name in sorted(M.MEDS):
        pk, side, warn = M.MEDS[name]
        rows.append({"ingredient": name, "purpose": M.PURPOSE["en"].format(p=M._P[pk][0]),
                     "side_effects": [M.SIDE[s][0] for s in side],
                     "warnings": {w: M.WARN[w][0] for w in sorted(warn, key=M.ORDER.index)}})
    return rows


def safe(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def export() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = table()
    (OUT / "table.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    (OUT / "prompt.md").write_text(RUBRIC + f"\n\nIngredients ({len(rows)}; send {BATCH} at a time if the chat is short):\n\n" + json.dumps(rows, indent=1, ensure_ascii=False))
    print(f"{len(rows)} ingredients -> {OUT}/table.json and prompt.md")


def ask(model: str) -> None:
    from dawa_buddy import llm
    if llm.is_offline():
        sys.exit("No NEBIUS_API_KEY loaded (put it in .env).")
    rows = table()
    batches = [rows[i:i + BATCH] for i in range(0, len(rows), BATCH)]

    def one(batch):
        for _ in range(2):
            try:
                data = llm.chat_json(RUBRIC, json.dumps(batch, ensure_ascii=False), model=model)
                if isinstance(data, list):
                    return data
            except Exception as e:
                err = e
        print("batch failed:", [b["ingredient"] for b in batch], err)
        return []

    with cf.ThreadPoolExecutor(4) as ex:
        answers = [a for part in ex.map(one, batches) for a in part if isinstance(a, dict)]
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"answers_{safe(model)}.json"
    f.write_text(json.dumps({"model": model, "answers": answers}, indent=1, ensure_ascii=False))
    print(f"{len(answers)}/{len(rows)} answered -> {f}")


def flags(a: dict) -> dict:
    return {"purpose": a.get("purpose") if a.get("purpose") in ("incomplete", "wrong") else None,
            "missing": [str(x) for x in a.get("missing") or []],
            "wrong": [str(x) for x in a.get("wrong") or []]}


def diff() -> None:
    files = sorted(OUT.glob("answers_*.json"))
    if not files:
        sys.exit("No answers_*.json yet. Run 'ask' or save a chat model's JSON reply as my_data/clinical_review/answers_<name>.json "
                 'in the form {"model": "<name>", "answers": [...]}.')
    by = {}
    for f in files:
        d = json.loads(f.read_text())
        by[d["model"]] = {a["ingredient"].lower(): flags(a) | {"note": a.get("note", "")} for a in d["answers"] if "ingredient" in a}
    names = sorted(M.MEDS)
    lines = [f"# Clinical second-opinion triage\n\nReviewers: {', '.join(by)}. Entries: {len(names)}. LLM output only; nothing here is a clinical review.\n"]
    unanimous, split, silent, unanswered = [], [], 0, []
    for n in names:
        got = {m: r[n] for m, r in by.items() if n in r}
        if not got:
            unanswered.append(n)
            continue
        flagged = {m: g for m, g in got.items() if g["purpose"] or g["wrong"]}      # "missing" alone is padding: models always suggest something
        if not flagged:
            silent += 1
            continue
        pk, side, warn = M.MEDS[n]
        block = [f"## {n}", f"- Now: {M.PURPOSE['en'].format(p=M._P[pk][0])} Warnings: {', '.join(warn) or 'none'}."]
        for m, g in flagged.items():
            bits = ([f"purpose {g['purpose']}"] if g["purpose"] else []) + ([f"missing: {'; '.join(g['missing'])}"] if g["missing"] else []) \
                + ([f"wrong: {'; '.join(g['wrong'])}"] if g["wrong"] else []) + ([f"note: {g['note']}"] if g["note"] else [])
            block.append(f"- **{m}**: " + " | ".join(bits))
        (unanimous if len(flagged) == len(got) and len(got) > 1 else split).append("\n".join(block))
    lines += [f"No purpose or wrong-warning flag from any reviewer: **{silent}** (missing-warning suggestions alone are not counted; they are in the answers files). Flagged by all reviewers: **{len(unanimous)}**. Flagged by only some: **{len(split)}**. "
              f"Unanswered: {len(unanswered)}.\n",
              "Decide the 'all reviewers' group first (most likely real). A single reviewer's flag is a prompt to look, not a finding.\n"]
    if unanimous:
        lines += ["# Flagged by all reviewers\n"] + unanimous
    if split:
        lines += ["\n# Flagged by only some reviewers\n"] + split
    if unanswered:
        lines += ["\n# Not answered\n", ", ".join(unanswered)]
    (OUT / "triage.md").write_text("\n\n".join(lines))
    print(f"{silent} clean, {len(unanimous)} flagged by all, {len(split)} by some, {len(unanswered)} unanswered -> {OUT}/triage.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["export", "ask", "diff"])
    ap.add_argument("--model", action="append", help="Token Factory model id (repeatable)")
    a = ap.parse_args()
    if a.cmd == "export":
        export()
    elif a.cmd == "ask":
        if not a.model:
            sys.exit("--model is required")
        try:
            from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
        except Exception:
            pass
        for m in a.model:
            ask(m)
    else:
        diff()
