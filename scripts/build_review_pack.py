"""Write docs/language_review.md: everything a Hindi or Kannada reader sees, for a native speaker to check.

  python scripts/build_review_pack.py            # Parts A and C come from the fixed tables; Part B calls the live models (needs NEBIUS_API_KEY)
Part A: dose phrases (explainer.PHRASES).  Part B: model-written purpose and side effects (a sample).  Part C: safety notes, timetable, disclaimer (i18n).
"""
import datetime, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from dawa_buddy import i18n, llm, medinfo
from dawa_buddy.explainer import PHRASES, dose_text, explain, explain_offline
from dawa_buddy.reader import read_offline
from dawa_buddy.scheduler import build_schedule

RX = read_offline("""Tab Telma 40 mg 1-0-0 x 30 days
Tab Dolo 650 mg 1-0-1 x 5 days after food
Tab Atorva 10 mg 0-0-1 x 30 days
Tab Metformin 500 mg 1-1-1 x 30 days after food
Tab Pantop 40 mg 1-0-0 x 30 days before food
Tab Cetzine 10 mg SOS
Tab Ecosprin 75 mg 0-0-1 to continue""")
P = PHRASES


def row(label, en, hi, kn):
    return f"| {label} | {en} | {hi} | {kn} | |".replace("\n", " ")


out = ["# Hindi and Kannada: reviewer pack", "",
       f"Generated {datetime.date.today()}. The script of every text is machine-checked (no stray letters from another script); **the wording is not, and that is what we need you for.**", "",
       "Medicine names, ingredient names, numbers and units (mg, ml) stay as printed on the strip, in Latin script, on purpose.", "",
       "## How to review", "",
       "For each row or item mark: **meaning** (says the same as the English), **dose or safety** (nothing wrong or missing: **a wrong dose or a softened warning is a blocking error**), "
       "**plain** (simple words an ordinary reader knows; no wrong-language words), **natural** (sounds like a pharmacist, not a translation). Write corrections in the last column.", "",
       "Three kinds of text, three ways they are made:", "",
       "- **Part A and Part C are fixed phrases.** No model writes them. If these are right, every dose sentence, safety note, timetable and disclaimer the app can show is right. **Please check every row.**",
       "- **Part B is written by AI** (what each medicine is for, and what to watch for). It differs every time; a sample is below.", "",
       "## Part A: dose sentences (fixed phrases)", "", "| Meaning (English) | English | Hindi | Kannada | OK? / correction |", "|---|---|---|---|---|"]
for label, k, sub in (("morning", "slots", "m"), ("afternoon", "slots", "a"), ("night", "slots", "n")):
    out.append(row(label, P["en"][k][sub], P["hi"][k][sub], P["kn"][k][sub]))
out.append(row("tablet (one)", P["en"]["unit"], P["hi"]["unit"], P["kn"]["unit"]))
out.append(row("dose (syrup, drops, injection)", P["en"]["dose"], P["hi"]["dose"], P["kn"]["dose"]))
out.append(row("one single dose (STAT)", P["en"]["stat"], P["hi"]["stat"], P["kn"]["stat"]))
for n in (1, 2, 3):
    out.append(row(f"{n} time(s) a day", P["en"]["times"][n], P["hi"]["times"][n], P["kn"]["times"][n]))
for k, label in (("before", "before food"), ("after", "after food"), ("bedtime", "at bedtime"), ("days", "for N days"), ("sos", "only when needed"),
                 ("go_on", "marked 'to continue'"), ("days_missing", "number of days not written"), ("unclear", "frequency not written"), ("end", "(ends every dose sentence: 'take')")):
    out.append(row(label, P["en"][k], P["hi"][k], P["kn"][k]))
out += ["", "### How they combine", ""]
for m in RX.medications:
    out += [f"- **{m.name}** ({m.frequency}): {dose_text(m, 'en')}  ", f"  Hindi: {dose_text(m, 'hi')}  ", f"  Kannada: {dose_text(m, 'kn')}", ""]

out += ["## Part C: safety notes, timetable, disclaimer (fixed phrases)", "", "### Headings", "", "| English | Hindi | Kannada | OK? / correction |", "|---|---|---|---|"]
for k, d in i18n.SEVERITY.items():
    out.append(f"| {d['en']} | {d['hi']} | {d['kn']} | |")
out += ["", "### Explainer screen labels", "", "| English | Hindi | Kannada | OK? / correction |", "|---|---|---|---|"]
for k, d in i18n.LABELS.items():
    out.append(f"| {d['en']} | {d['hi']} | {d['kn']} | |")
out += ["", "### Safety notes: titles", "", "| English | Hindi | Kannada | OK? / correction |", "|---|---|---|---|"]
for k, d in i18n.TITLES.items():
    out.append(f"| {d['en']} | {d['hi']} | {d['kn']} | |")
out += ["", "### Safety notes: sentences (`{...}` is filled with a medicine name, an ingredient or a number)", ""]
for k, d in i18n.DETAILS.items():
    out += [f"**{k}**", f"- English: {d['en']}", f"- Hindi: {d['hi']}", f"- Kannada: {d['kn']}", "- Reviewer: meaning [ ]  safety [ ]  plain [ ]  natural [ ]   Notes:", ""]
out += ["### \"Something is not written\" (built from these parts)", ""]
for k, d in i18n.NOT_WRITTEN.items():
    out += [f"**{k}**", f"- English: {d['en'].strip()}", f"- Hindi: {d['hi'].strip()}", f"- Kannada: {d['kn'].strip()}", "- Reviewer: meaning [ ]  plain [ ]  natural [ ]   Notes:", ""]
out += ["### Regulator status words", "", "| English | Hindi | Kannada | OK? / correction |", "|---|---|---|---|"]
for k, d in i18n.STATUS.items():
    out.append(f"| {d['en']} | {d['hi']} | {d['kn']} | |")
out += ["", "### Timetable and sharing text", "", "| English | Hindi | Kannada | OK? / correction |", "|---|---|---|---|"]
for k, d in i18n.TIMETABLE.items():
    if k == "headers":
        out.append(f"| {' / '.join(d['en'])} (column headings) | {' / '.join(d['hi'])} | {' / '.join(d['kn'])} | |")
    elif k == "slots":
        out += [f"| {v['en']} | {v['hi']} | {v['kn']} | |" for v in d.values()]
    else:
        out.append(f"| {d['en']} | {d['hi']} | {d['kn']} | |")
out += ["", "### The two notices above the explanations", "",
        "Shown above the medicine cards, depending on whether the AI text was written in the language or fell back to English.", "",
        f"- AI note, English: {i18n.AI_NOTE['en']}", f"- AI note, Hindi: {i18n.AI_NOTE['hi']}", f"- AI note, Kannada: {i18n.AI_NOTE['kn']}",
        f"- Fallback notice, Hindi: {i18n.FALLBACK_NOTE['hi']}", f"- Fallback notice, Kannada: {i18n.FALLBACK_NOTE['kn']}",
        "- Reviewer: meaning [ ]  plain [ ]  natural [ ]   Notes:", "", "### Disclaimer (shown under every explanation)", "", f"- English: {i18n.DISCLAIMER['en']}", f"- Hindi: {i18n.DISCLAIMER['hi']}", f"- Kannada: {i18n.DISCLAIMER['kn']}",
        "- Reviewer: meaning [ ]  plain [ ]  natural [ ]   Notes:", "", "### A whole timetable, as the family sees it", ""]
for lang, label in (("hi", "Hindi"), ("kn", "Kannada")):
    items = build_schedule(RX, lang)
    out += [f"**{label}**", "", "```", i18n.share_text(items, 30, lang), "```", ""]

out += ["## Part B: model-written text (a sample)", "",
        "Written by NVIDIA Nemotron each time, so it varies. Mark: **meaning**, **plain**, **safe** (no diagnosis; never says to stop or change a dose), **natural**. "
        "Please also mark anything that is **nonsense** (a sentence that is fluent but is not about the medicine).", "",
        "**Hindi** is shown to users. **Kannada is NOT shown to users by default**: on a real run three of four 'watch for' lines were fluent-looking nonsense "
        "(place names, 'Friday'), which no automatic check can catch. The Kannada samples below are here so you can tell us whether it could ever be switched on, "
        "and the answer is probably no unless nearly all lines are correct.", ""]
if llm.is_offline():
    out += ["_Not generated: set NEBIUS_API_KEY and run again._", ""]
else:
    import os
    os.environ["DAWA_KN_MODEL_TEXT"] = "1"        # Part B only: show reviewers what the switched-off Kannada path produces
    en = {m.name: e for m, e in zip(RX.medications, explain(RX, "en"))}
    for lang, label in (("hi", "Hindi"), ("kn", "Kannada (switched off for users)")):
        _info = medinfo.info
        if lang == "kn":
            medinfo.info = lambda *a, **k: None       # the fixed table would answer for common medicines: show the raw model output the table replaces
        items = explain(RX, "hi" if lang == "hi" else "kn")
        medinfo.info = _info
        out += [f"### {label}", ""]
        if any(i.language_fallback for i in items):
            out += ["_This run fell back to English; the app would have shown a notice._", ""]
        for m, e in zip(RX.medications, items):
            out += [f"**{m.name}**: English: _{en[m.name].purpose} / {en[m.name].watch_for}_", f"- purpose: {e.purpose}", f"- watch for: {e.watch_for}",
                    "- Reviewer: meaning [ ]  plain [ ]  safe [ ]  natural [ ]   Notes:", ""]
out += ["", "## Part D: Kannada \"what it is for / watch for\" table (fixed, no AI)", "",
        "Shown to a Kannada reader for the ingredients below instead of AI text. Each line is built from the short pieces in D1 to D4, so checking those checks everything.", "",
        "### D1. Sentence frames", "", "| English | Kannada | OK? / correction |", "|---|---|---|"]
for k in ("PURPOSE", "SIDE_SENTENCE", "PURPOSE_JOIN"):
    out.append(f"| {medinfo.__dict__[k]['en']} | {medinfo.__dict__[k]['kn']} | |")
out += ["", "### D2. What it is for (completes the frame above)", "", "| English | Kannada | OK? / correction |", "|---|---|---|"]
for en, kn in medinfo._P.values():
    out.append(f"| {en} | {kn} | |")
out += ["", "### D3. Side effects (\"Some people get ...\")", "", "| English | Kannada | OK? / correction |", "|---|---|---|"]
for en, kn in medinfo.SIDE.values():
    out.append(f"| {en} | {kn} | |")
out += ["", "### D4. Warnings (whole sentences)", "", "| English | Kannada | OK? / correction |", "|---|---|---|"]
for en, kn in medinfo.WARN.values():
    out.append(f"| {en} | {kn} | |")
out += ["", f"### D5. Which ingredient gets which pieces ({len(medinfo.MEDS)} ingredients). Please check the medical meaning, not only the Kannada.", "",
        "| Ingredient | Purpose | Side effects | Warnings |", "|---|---|---|---|"]
for name, (pk, se, wn) in medinfo.MEDS.items():
    out.append(f"| {name} | {medinfo._P[pk][0]} | {', '.join(medinfo.SIDE[x][0] for x in se) or '-'} | {' / '.join(medinfo.WARN[x][0] for x in wn) or '-'} |")
pathlib.Path("docs/language_review.md").write_text("\n".join(out), encoding="utf-8")
print("written docs/language_review.md,", len(out), "lines")
