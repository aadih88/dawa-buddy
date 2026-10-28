"""Reader agent: prescription text -> structured Prescription.

Design: deterministic rules do the heavy lifting (they are auditable and cannot invent things); the model only
sees lines the rules could not complete, and everything it returns is normalised and grounded in the source text.
"""
from __future__ import annotations
import re
from . import llm
from .knowledge import BRANDS, resolve_generic
from .schemas import Medication, Prescription

SYSTEM = """You extract medicines from an Indian prescription line. Reply with ONLY JSON:
{"medications":[{"name":str,"strength":str|null,"form":str|null,"frequency":str|null,
"duration_days":int|null,"timing":str|null}]}
frequency: use morning-afternoon-night counts like "1-0-1", or "SOS" for as-needed.
timing: "after food", "before food", "bedtime" or null. Use null for anything not written in the text.
Never add a medicine that is not written. Never correct a dose."""

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
             "nine": 9, "ten": 10, "fourteen": 14}
FORM_WORDS = {"tab": "tablet", "tablet": "tablet", "t": "tablet", "cap": "capsule", "capsule": "capsule",
              "syp": "syrup", "syrup": "syrup", "inj": "injection", "injection": "injection",
              "oint": "ointment", "drops": "drops"}
FILLER = {"take", "patient", "on", "add", "also", "continue", "start", "give", "rx", "then", "plus", "and"} | set(FORM_WORDS)
LAST_MODEL_OUTPUT: list = []      # diagnostics: raw model answers from the latest read


def deabbrev(s: str) -> str:
    """'b.i.d.' -> 'bid', 'p.c.' -> 'pc', 'o.d.' -> 'od'."""
    return re.sub(r"\b(?:[a-z]\.){2,}[a-z]?\.?", lambda m: m.group(0).replace(".", ""), s)


def freq_from_text(s: str) -> str | None:
    s = deabbrev(s.lower())
    # "0-0-1 ... SOS in case of constipation" is an as-needed medicine: never show it as a daily one
    if re.search(r"\b(sos|prn|in case of|as needed|when needed|if needed)\b", s):
        return "SOS"
    if re.search(r"\bstat\b", s):
        return "STAT"                      # one single dose, now
    # prescriptions print 1-0-1 with any number of dashes ("0---1---0"), or en/em dashes
    m = re.search(r"\b([01])\s*[-\u2013\u2014]+\s*([01])\s*[-\u2013\u2014]+\s*([01])\b", s)
    if m:
        return "-".join(m.groups())
    if re.search(r"\b(tds|tid|thrice|three times|3 times)\b", s):
        return "1-1-1"
    if re.search(r"\b(bd|bid|twice|two times|2 times)\b|morning\s*(?:and|&|-|/)\s*(?:night|evening)", s):
        return "1-0-1"
    if re.search(r"\b(hs|nocte|bedtime|bed time|at night|every night|nightly)\b", s):
        return "0-0-1"
    if re.search(r"\bafternoon\b", s):
        return "0-1-0"
    if re.search(r"\b(od|qd|once|daily|every morning|in the morning|morning)\b", s):
        return "1-0-0"
    return None


def days_from_text(s: str) -> int | None:
    s = deabbrev(s.lower())
    m = re.search(r"(?:x|×|for)\s*(\d+|" + "|".join(NUM_WORDS) + r")\s*(days?|d|weeks?|wks?|months?|mos?)\b", s)
    if not m:
        return None
    n = int(m[1]) if m[1].isdigit() else NUM_WORDS[m[1]]
    return n * 7 if m[2].startswith("w") else n * 30 if m[2].startswith("m") else n


def timing_from_text(s: str) -> str | None:
    s = deabbrev(s.lower())
    if re.search(r"\b(after (?:food|meals?|breakfast|lunch|dinner)|pc|af|a/f|post ?meals?|post[- ]?prandial)\b", s):
        return "after food"
    if re.search(r"\b(before (?:food|meals?|breakfast|lunch|dinner)|ac|bf|b/f|empty stomach)\b", s):
        return "before food"
    if re.search(r"\b(bedtime|bed time|hs|at night)\b", s):
        return "bedtime"
    return None


def _known_tokens() -> set:
    return set(BRANDS)


def _segments(line: str) -> list[str]:
    """Split a sentence that names several drugs into one segment per drug."""
    line = deabbrev(line)
    toks = re.findall(r"[a-z]+", line.lower())
    if len({t for t in toks if t in _known_tokens()}) < 2:
        return [line]
    parts = re.split(r"(?<=[A-Za-z0-9]{3})\.\s+(?=[A-Za-z])|;\s*|\b(?:also|add|plus)\b", line, flags=re.I)
    return [p.strip(" ,") for p in parts if p and p.strip(" ,")]


# Words that follow a brand name but are not part of it (route, form, frequency, timing, numbers written out)
_NOT_NAME = {"tab", "tablet", "tablets", "cap", "caps", "capsule", "capsules", "syp", "syrup", "inj", "injection", "drops", "cream", "gel", "ointment", "po", "iv", "im",
             "sc", "sos", "prn", "stat", "od", "bd", "bid", "tds", "tid", "qid", "hs", "daily", "twice", "thrice", "once", "nightly", "after", "before", "with", "for", "x",
             "in", "as", "to", "at", "per", "every", "morning", "night", "evening", "noon", "afternoon", "bedtime", "food", "meals", "meal", "and", "directed", "continue",
             "days", "day", "week", "weeks", "month", "months", "empty", "stomach", "when", "if", "needed", "take", "give", "only", "mg", "ml", "mcg", "gm", "iu",
             "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}


def complete_name(name: str, line: str) -> str:
    """A brand name cut short ('Concor' for 'CONCOR T 5MG/40') becomes the full printed name. Only the one or two short words that follow it directly,
    before a number, comma, route or frequency word, are added. A truncated name would otherwise raise a false wrong-variant warning (Concor is not Concor T)."""
    words = re.findall(r"[A-Za-z0-9]+", name)
    if not words:
        return name
    m = re.search(r"[\s\-\.]*".join(re.escape(w) for w in words), line, re.I)
    if not m:
        return name
    tail, extra = line[m.end():], []
    for _ in range(2):
        t = re.match(r"\s+([A-Za-z]{1,9})(?=[\s,]|$)", tail)
        if not t or t.group(1).lower() in _NOT_NAME:
            break
        extra.append(t.group(1))
        tail = tail[t.end():]
    return " ".join([name] + [w.title() for w in extra]) if extra else name


def _parse_segment(seg: str) -> Medication | None:
    low = deabbrev(seg.lower())
    toks = re.findall(r"[a-z][a-z\-]*", low)
    known = _known_tokens()
    drug = next((t for t in toks if t in known), None)
    form = next((FORM_WORDS[t] for t in toks[:3] if t in FORM_WORDS), None)
    if drug is None:
        drug = next((t for t in toks if t not in FILLER and len(t) > 1), None)
    if drug is None:
        return None
    st = re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|iu)\b", low)
    freq, days, timing = freq_from_text(low), days_from_text(low), timing_from_text(low)
    if not (st or freq or days or drug in known):
        return None                       # e.g. 'Rx' or a stray header line
    drug = drug.strip("-")
    return Medication(name=complete_name(drug.title(), seg), generic=resolve_generic(drug), strength=f"{st.group(1)} {st.group(2)}" if st else None,
                      form=form, frequency=freq, duration_days=days, timing=timing, raw=seg)


FORM_START = re.compile(r"^\W*(?:tab|tablet|cap|capsule|syp|syrup|inj|injection|oint|ointment|drops?)\b", re.I)


def medicine_segments(text: str) -> list[tuple[str, Medication | None]]:
    """Every line or segment that looks like a medicine, with what the offline reader made of it (None if it could not read it).
    read_offline drops a line it cannot read; this keeps it, so a caller can tell the user instead of the line quietly vanishing.
    A line counts as a medicine if the reader parsed it, or if it starts with a form word (TAB, SYP, INJ...)."""
    out = []
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        for seg in _segments(line):
            m = _parse_segment(seg)
            if m or FORM_START.match(seg):
                out.append((seg.strip(), m))
    return out


def read_offline(text: str) -> Prescription:
    meds = []
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        for seg in _segments(line):
            m = _parse_segment(seg)
            if m:
                meds.append(m)
    return Prescription(medications=meds)


# ----------------------------------------------------------------------------- model-assisted path
def canon_freq(f) -> str | None:
    """Accept only canonical dose patterns; anything else becomes None (never keep model free text)."""
    if not f or not isinstance(f, str):
        return None
    return freq_from_text(f)


def canon_timing(t, line: str) -> str | None:
    """Model timing is kept only if the source line itself contains evidence for it."""
    if not t or not isinstance(t, str):
        return None
    norm = timing_from_text(t)
    return norm if norm and norm == timing_from_text(line) else None


def is_complete(m: Medication) -> bool:
    return bool(m.generic and m.frequency and (m.duration_days or m.frequency in ("SOS", "STAT")))


def _clean_model_meds(data, line: str) -> list[Medication]:
    """Normalise model output and enforce grounding: a medicine must be literally present in the source line."""
    out = []
    low = line.lower()
    for d in (data or {}).get("medications", []) if isinstance(data, dict) else []:
        try:
            name = re.sub(r"^(?:tablet|tab|capsule|cap|syrup|syp|injection|inj|t|c)\.?\s+", "", str(d.get("name", "")).strip(), flags=re.I).strip()
            name = re.sub(r"[\s\-]*\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml)?$", "", name, flags=re.I).strip()
            first = re.findall(r"[a-z]+", name.lower())
            if not first or first[0] not in low:
                continue                                  # not in the source text -> discard
            days = d.get("duration_days")
            days = int(days) if isinstance(days, (int, float)) and days > 0 else None
            out.append(Medication(name=complete_name(name.title(), line), generic=resolve_generic(name), strength=d.get("strength"),
                                  form=d.get("form"), frequency=canon_freq(d.get("frequency")),
                                  duration_days=days, timing=canon_timing(d.get("timing"), line), raw=line))
        except Exception:
            continue
    return out


def _fill_from_rules(modeled: list[Medication], ruled: list[Medication]) -> list[Medication]:
    """Where the model left a field empty and the rules found it, keep the rule value."""
    by = {m.name.lower(): m for m in ruled}
    for m in modeled:
        r = by.get(m.name.lower())
        if r:
            m.frequency = m.frequency or r.frequency
            m.duration_days = m.duration_days or r.duration_days
            m.timing = m.timing or r.timing
            m.strength = m.strength or r.strength
    return modeled


def read_prescription(text: str) -> Prescription:
    """Rules first; the model only handles lines the rules cannot fully parse."""
    if llm.is_offline():
        return read_offline(text)
    LAST_MODEL_OUTPUT.clear()
    meds: list[Medication] = []
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        ruled = [m for seg in _segments(line) if (m := _parse_segment(seg))]
        if ruled and all(is_complete(m) for m in ruled):
            meds += ruled
            continue
        try:
            data = llm.chat_json(SYSTEM, line, model=llm.FAST_MODEL)
            LAST_MODEL_OUTPUT.append((line, data))
            modeled = _fill_from_rules(_clean_model_meds(data, line), ruled)
        except Exception:
            modeled = []
        meds += modeled or ruled
    return Prescription(medications=meds)
