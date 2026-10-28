"""Explainer: structured meds -> plain-language explanations (en/hi/kn).

Measured on Nebius Token Factory (27 Oct 2026): the default fast model answers a Hindi or Kannada request in English; Nemotron
Super 120B writes good Hindi but garbles Kannada (stray Bengali/Arabic letters); Nemotron Ultra 550B writes good Hindi (4 of 4 clean)
and usable Kannada only with an explicit script instruction and an example, and even then about one answer in three or four is
clean first time (it sometimes writes a Hindi word such as chakkar inside Kannada), hence the retries. So each language has its own model chain, and every answer is checked for the right
script before it is shown. If no model passes, the English explanation is shown with `language_fallback=True`: never silently.
Doses never come from the model's translation: the app shows the rule-built dose line next to it.
"""
from __future__ import annotations
import json
import os
import re
import unicodedata
from . import llm, medinfo
from .safety import ONGOING
from .schemas import LANG_NAMES, Lang, MedExplanation, Prescription

ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"
SUPER = "nvidia/nemotron-3-super-120b-a12b"
# lang -> (script name, unicode range, example sentence in that script, model chain: first that passes the script check wins)
NATIVE = {
    "hi": ("Devanagari", (0x0900, 0x097F), "यह दवा बुखार और दर्द कम करती है। दिन में दो बार खाने के बाद एक गोली लें।",
           [os.environ.get("DAWA_HI_MODEL", ULTRA), SUPER]),
    "kn": ("Kannada", (0x0C80, 0x0CFF), "ಈ ಔಷಧಿ ಜ್ವರ ಮತ್ತು ನೋವನ್ನು ಕಡಿಮೆ ಮಾಡುತ್ತದೆ. ದಿನಕ್ಕೆ ಎರಡು ಬಾರಿ ಊಟದ ನಂತರ ಒಂದು ಮಾತ್ರೆ ತೆಗೆದುಕೊಳ್ಳಿ.",
           [os.environ.get("DAWA_KN_MODEL", ULTRA)] * 3),     # Ultra's Kannada sometimes slips in a Devanagari word: retry before giving up
}
NATIVE_SYSTEM = """You write patient information for people in India, in {language} ({script} script) ONLY.
Every sentence must be in {language}. Do not write English sentences. Do not use any other script: no Devanagari in Kannada, no Bengali, no Arabic.
Medicine names, units (mg, ml) and numbers may stay as they are. Short sentences, simple words, Grade 5 reading level.
Example of the required style, in {language}: {example}
For EACH medicine given, return JSON: {{"explanations":[{{"name":str,"purpose":str,"watch_for":str}}]}}
Rules:
- purpose: what the medicine is generally used for. Do NOT say what the patient has or diagnose.
- Do NOT write any dose, number of tablets, how often, or when to take it: that is added separately from the prescription.
- watch_for: 1-2 common side effects and when to seek help. Never tell the patient to stop a medicine.
Reply with ONLY the JSON."""

SYSTEM = """You are a careful health educator writing for a patient with low health literacy in India.
Write in {language}, at about a Grade 5 reading level, short sentences, no jargon.
For EACH medicine given, return JSON: {{"explanations":[{{"name":str,"purpose":str,"watch_for":str}}]}}
Rules:
- purpose: what the medicine is generally used for. Do NOT say what the patient has or diagnose.
- Do NOT write any dose, number of tablets, how often, or when to take it: that is added separately from the prescription.
- watch_for: 1-2 common side effects and when to seek help. Never tell the patient to stop a medicine.
Reply with ONLY the JSON."""

_FREQ = {"en": {"1-0-0": "once a day (morning)", "0-1-0": "once a day (afternoon)", "0-0-1": "once a day (night)",
                "1-0-1": "twice a day (morning and night)", "1-1-1": "three times a day", "SOS": "only when needed"}}


# ---- Dose sentences: fixed templates filled from the prescription. The model never writes a dose (it once wrote "3 times a day" for 1-0-1
# and added "on an empty stomach" nobody had prescribed). Each phrase below is small enough for a native speaker to check once.
PHRASES = {
    "en": {"slots": {"m": "morning", "a": "afternoon", "n": "night"}, "unit": "tablet", "units": "tablets", "dose": "dose", "doses": "doses", "stat": "One single dose, given once.",
           "times": {1: "Once a day", 2: "Twice a day", 3: "3 times a day"}, "before": "before food", "after": "after food", "bedtime": "at bedtime", "days": "for {n} days",
           "end": ".", "sos": "Take only when needed.", "go_on": " Keep taking it as your doctor says.", "days_missing": " The number of days is not written: ask your pharmacist.", "unclear": "Ask your doctor or pharmacist how to take it."},
    "hi": {"slots": {"m": "सुबह", "a": "दोपहर", "n": "रात"}, "unit": "गोली", "units": "गोली", "dose": "खुराक", "doses": "खुराक", "stat": "एक ही खुराक, एक बार दी जाती है।",
           "times": {1: "दिन में 1 बार", 2: "दिन में 2 बार", 3: "दिन में 3 बार"}, "before": "खाने से पहले", "after": "खाने के बाद", "bedtime": "सोने से पहले", "days": "{n} दिन तक",
           "end": " लें।", "sos": "सिर्फ़ ज़रूरत पड़ने पर लें।", "go_on": " डॉक्टर के कहे अनुसार जारी रखें।", "days_missing": " कितने दिन लेना है, यह नहीं लिखा है: दवा-विक्रेता से पूछें।",
           "unclear": "कैसे लेना है, यह अपने डॉक्टर या दवा-विक्रेता से पूछें।"},
    "kn": {"slots": {"m": "ಬೆಳಿಗ್ಗೆ", "a": "ಮಧ್ಯಾಹ್ನ", "n": "ರಾತ್ರಿ"}, "unit": "ಮಾತ್ರೆ", "units": "ಮಾತ್ರೆ", "dose": "ಡೋಸ್", "doses": "ಡೋಸ್", "stat": "ಒಂದೇ ಡೋಸ್, ಒಂದು ಬಾರಿ ನೀಡಲಾಗುತ್ತದೆ.",
           "times": {1: "ದಿನಕ್ಕೆ 1 ಬಾರಿ", 2: "ದಿನಕ್ಕೆ 2 ಬಾರಿ", 3: "ದಿನಕ್ಕೆ 3 ಬಾರಿ"}, "before": "ಊಟದ ಮೊದಲು", "after": "ಊಟದ ನಂತರ", "bedtime": "ಮಲಗುವ ಮೊದಲು", "days": "{n} ದಿನಗಳವರೆಗೆ",
           "end": " ತೆಗೆದುಕೊಳ್ಳಿ.", "sos": "ಅಗತ್ಯವಿದ್ದಾಗ ಮಾತ್ರ ತೆಗೆದುಕೊಳ್ಳಿ.", "go_on": " ವೈದ್ಯರು ಹೇಳಿದಂತೆ ಮುಂದುವರಿಸಿ.", "days_missing": " ಎಷ್ಟು ದಿನ ತೆಗೆದುಕೊಳ್ಳಬೇಕು ಎಂದು ಬರೆದಿಲ್ಲ: ಔಷಧಿ ಅಂಗಡಿಯವರನ್ನು ಕೇಳಿ.",
           "unclear": "ಹೇಗೆ ತೆಗೆದುಕೊಳ್ಳಬೇಕು ಎಂದು ನಿಮ್ಮ ವೈದ್ಯರು ಅಥವಾ ಔಷಧಿ ಅಂಗಡಿಯವರನ್ನು ಕೇಳಿ."},
}


_VOLUME = re.compile(r"^\d+(?:\.\d+)?ml$", re.I)


def pretty_strength(s: str | None) -> str:
    """'500MG' -> '500 mg'; '75MG/75MG/10MG' -> '75 mg / 75 mg / 10 mg'; '5MG/40' -> '5 mg / 40 mg' (a bare number takes the unit before it);
    stray words around the numbers ('T 5MG/40' from a model) are dropped: only the amounts are kept."""
    if not s:
        return ""
    found = [re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|iu)?\b", x, re.I) for x in re.split(r"\s*/\s*", str(s))]
    found = [m for m in found if m]
    first = next((m.group(2).lower() for m in found if m.group(2)), "")
    return " / ".join(f"{m.group(1)} {(m.group(2) or first).lower()}".strip() for m in found)


def amount_text(m, lang: str = "en", n: int = 1) -> str:
    """What to take at one time, in words a person understands: '1 tablet (500 mg)', '15 ml', '1 dose (500 mg)'. The strength says what is IN the medicine; the amount says how much to take."""
    p = PHRASES[lang]
    strength = pretty_strength(m.strength)
    solid = (m.form or "").lower() in ("", "tablet", "capsule", "tab", "cap")
    if not solid and _VOLUME.match(strength.replace(" ", "")):
        return strength                                        # a syrup or drops: the volume IS the amount
    unit, units = (p["unit"], p["units"]) if solid else (p["dose"], p["doses"])
    return f"{n} {unit if n == 1 else units}" + (f" ({strength})" if strength else "")


def dose_text(m, lang: str = "en") -> str:
    """The dose sentence for one prescribed medicine, from the prescription only (frequency 1-0-1, timing, days, SOS)."""
    p = PHRASES[lang]
    freq = (m.frequency or "").strip()
    timing = {"before food": p["before"], "after food": p["after"], "bedtime": p["bedtime"]}.get(m.timing or "", "")
    if freq == "SOS":
        return p["sos"]
    if freq == "STAT":
        return p["stat"]
    digits = re.findall(r"\d", freq)
    if len(digits) != 3 or not any(int(d) for d in digits):
        return p["unclear"]
    parts = [f"{p['slots'][slot]} {amount_text(m, lang, int(d))}" for slot, d in zip("man", digits) if int(d)]
    tail = ([timing] if timing else []) + ([p["days"].format(n=m.duration_days)] if m.duration_days else [])
    sentence = f"{p['times'][len(parts)]}: " + ", ".join(parts) + "".join(", " + t for t in tail)
    # No end date: 'to continue' really means keep going; otherwise the days are simply missing, and a painkiller course must not read as ongoing
    return sentence + p["end"] + ("" if m.duration_days else p["go_on"] if ONGOING.search(m.raw or "") else p["days_missing"])


def unclear_dose_lines(text: str) -> list[str]:
    """Prescription lines (as typed) whose dose we cannot read: the same test dose_text uses to say 'ask your doctor', plus medicine lines the
    offline reader could not parse at all (it would otherwise drop them silently). Offline on purpose: instant, free, and it validates the model's reading."""
    from .reader import medicine_segments
    return [seg for seg, m in medicine_segments(text) if m is None or dose_text(m, "en") == PHRASES["en"]["unclear"]]


def model_text_langs() -> set:
    """Languages in which the MODEL may write purpose and side effects. Kannada is off by default: on a real run three of four 'watch for' lines were
    fluent-looking nonsense (place names, 'Friday') in valid Kannada script, which no script check can catch. Set DAWA_KN_MODEL_TEXT=1 to test it."""
    return {"hi"} | ({"kn"} if os.environ.get("DAWA_KN_MODEL_TEXT") == "1" else set())


def with_doses(items: list[MedExplanation], rx: Prescription, lang: str) -> list[MedExplanation]:
    """Replace whatever dose text the model wrote with the template sentence, matched by order (the count is checked by the caller)."""
    if len(items) == len(rx.medications):
        for e, m in zip(items, rx.medications):
            e.how_to_take = dose_text(m, lang)
            fixed = medinfo.info(m, lang) if lang == "kn" else None
            if fixed:       # a reviewed table beats a model for the common ingredients; anything not in it keeps the English line and its notice
                e.purpose, e.watch_for = fixed
                e.fixed, e.language_fallback = True, False
    return items


def explain_offline(rx: Prescription, lang: Lang) -> list[MedExplanation]:
    """No model: the dose sentence comes from the templates and, in Kannada, common ingredients from the reviewed table; the rest says to ask the pharmacist."""
    items = [MedExplanation(name=m.name, purpose="Ask your pharmacist what this medicine is for (offline mode has no medical text).",
                            how_to_take=dose_text(m, lang), watch_for="Ask your pharmacist about side effects.", language_fallback=(lang != "en"))
             for m in rx.medications]
    return with_doses(items, rx, lang)


def script_counts(text: str, lang: str) -> tuple[int, int]:
    """(letters in the target script, letters in any other non-Latin script). Latin stays free: medicine names and units."""
    lo, hi = NATIVE[lang][1]
    target = other = 0
    for c in text:
        if ord(c) >= 0x250 and unicodedata.category(c)[0] in "LM":       # vowel signs and viramas are marks, not letters: they must count too
            if lo <= ord(c) <= hi:
                target += 1
            else:
                other += 1
    return target, other


REPAIR_SYSTEM = """Rewrite the text below in {language} ({script} script) ONLY. Do not use any other script: no Devanagari, Bengali or Arabic letters.
Keep the meaning and every number and unit exactly as they are. Reply with ONLY JSON: {{"text": str}}"""


def repair(items: list[MedExplanation], lang: str, model: str) -> list[MedExplanation]:
    """A wrong-script slip is usually one word in one field: rewrite just that field instead of throwing the whole answer away."""
    script = NATIVE[lang][0]
    system = REPAIR_SYSTEM.format(language=LANG_NAMES[lang], script=script)
    for e in items:
        for field in ("purpose", "watch_for"):
            value = getattr(e, field)
            if script_counts(value, lang)[1]:
                try:
                    setattr(e, field, str(llm.chat_json(system, json.dumps({"text": value}), model=model, retries=0)["text"]))
                except Exception:
                    pass
    return items


def native_ok(items: list[MedExplanation], n_meds: int, lang: str) -> bool:
    """Right script, no stray scripts, one explanation per medicine, and real text in the fields that carry the instruction."""
    if len(items) != n_meds:
        return False
    for e in items:
        t, o = script_counts(e.purpose, lang)
        if o or t < 8:
            return False
        if script_counts(e.watch_for, lang)[1]:
            return False
    return True


def explain(rx: Prescription, lang: Lang) -> list[MedExplanation]:
    if llm.is_offline() or not rx.medications:
        return explain_offline(rx, lang)
    payload = json.dumps([m.model_dump(exclude={"raw"}) for m in rx.medications])
    if lang in NATIVE and lang not in model_text_langs():
        # the dose sentence is still in the reader's language (reviewed templates); only the AI-written lines stay English
        data = llm.chat_json(SYSTEM.format(language="English"), payload)
        return with_doses([MedExplanation(**e, language_fallback=True) for e in data["explanations"]], rx, lang)
    if lang in NATIVE:
        script, _, example, chain = NATIVE[lang]
        system = NATIVE_SYSTEM.format(language=LANG_NAMES[lang], script=script, example=example)
        for model in chain:
            try:
                items = [MedExplanation(**e) for e in llm.chat_json(system, payload, model=model, retries=1)["explanations"]]
            except Exception:
                continue            # model unavailable or bad JSON: try the next one
            if len(items) == len(rx.medications) and not native_ok(items, len(rx.medications), lang):
                items = repair(items, lang, model)
            if native_ok(items, len(rx.medications), lang):
                return with_doses(items, rx, lang)
        # no model produced clean text in this language: say so, in English, rather than show garbled medical text
        data = llm.chat_json(SYSTEM.format(language="English"), payload)
        return with_doses([MedExplanation(**e, language_fallback=True) for e in data["explanations"]], rx, lang)
    data = llm.chat_json(SYSTEM.format(language=LANG_NAMES[lang]), payload)
    return with_doses([MedExplanation(**e) for e in data["explanations"]], rx, "en")
