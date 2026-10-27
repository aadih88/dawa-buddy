"""Safety agent. Deterministic rules first (cheap, auditable); model never overrides them."""
from __future__ import annotations
import re
from itertools import combinations
from .knowledge import INTERACTIONS, load_alerts
from .schemas import Prescription, SafetyFlag

ONGOING = re.compile(r"\b(continue|ongoing|long[- ]?term|regularly|lifelong)\b", re.I)    # 'to continue': no end date is normal, not a gap
DAILY_DOSES = {"1-0-0": 1, "0-1-0": 1, "0-0-1": 1, "1-0-1": 2, "1-1-0": 2, "0-1-1": 2, "1-1-1": 3}


def _ingredients(generic: str | None) -> set[str]:
    return set(generic.split("+")) if generic else set()


def check(rx: Prescription, alerts: list | None = None) -> list[SafetyFlag]:
    flags: list[SafetyFlag] = []
    meds = rx.medications

    # 1. Interactions between ingredients of different medicines
    for a, b in combinations(meds, 2):
        ia, ib = _ingredients(a.generic), _ingredients(b.generic)
        for rule in INTERACTIONS:
            if (rule["a"] in ia and rule["b"] in ib) or (rule["b"] in ia and rule["a"] in ib):
                flags.append(SafetyFlag(severity=rule["severity"], title=rule["title"], detail=rule["detail"], meds=[a.name, b.name],
                                        code=rule["code"], args={"drug": next(x for x in (rule["a"], rule["b"]) if x in ("ibuprofen", "diclofenac"))}
                                        if rule["code"] == "warfarin_nsaid" else {}))

    # 2. Same ingredient in two different lines (accidental double dosing)
    for a, b in combinations(meds, 2):
        shared = _ingredients(a.generic) & _ingredients(b.generic)
        if shared and a.name.lower() != b.name.lower():
            flags.append(SafetyFlag(
                severity="ask_pharmacist", title="Same ingredient twice",
                detail=f"Both contain {', '.join(sorted(shared))}. Taking both can mean a double dose. Ask if both are needed.",
                meds=[a.name, b.name], code="double_ingredient", args={"ingredients": ", ".join(sorted(shared))}))

    # 3. Paracetamol daily maximum (4 g/day for adults)
    total_mg = 0
    for m in meds:
        if "paracetamol" in _ingredients(m.generic) and m.strength and m.frequency in DAILY_DOSES:
            try:
                mg = float(m.strength.split()[0])
                if m.strength.endswith("mg") and m.generic == "paracetamol":
                    total_mg += mg * DAILY_DOSES[m.frequency]
            except ValueError:
                pass
    if total_mg > 4000:
        flags.append(SafetyFlag(severity="call_doctor", title="Paracetamol above 4 g a day",
                                detail=f"The written doses add up to {int(total_mg)} mg a day, above the usual adult maximum of 4000 mg. Confirm with the prescriber.",
                                meds=[m.name for m in meds if "paracetamol" in _ingredients(m.generic)], code="paracetamol_max", args={"mg": int(total_mg)}))

    # 4. Missing information: ONE note for the whole prescription, not one card per medicine
    no_freq = [m.name for m in meds if not m.frequency]
    no_days = [m.name for m in meds if m.frequency and m.frequency not in ("SOS", "STAT") and not m.duration_days and not ONGOING.search(m.raw or "")]
    if no_freq or no_days:
        parts = []
        if no_freq:
            parts.append(f"How often to take it is not written for: {', '.join(no_freq)}.")
        if no_days:
            parts.append(f"The number of days is not written for: {', '.join(no_days)}.")
        flags.append(SafetyFlag(severity="info", title="Something is not written",
                                detail=" ".join(parts) + " Ask the pharmacist before you start.", meds=no_freq + [n for n in no_days if n not in no_freq],
                                code="not_written", args={"no_freq": ", ".join(no_freq), "no_days": ", ".join(no_days)}))

    # 5. Regulator alert feed (batch-level; only fires if a batch number is provided in the text)
    for al in (alerts if alerts is not None else load_alerts()):
        for m in meds:
            if al["drug"] in (m.name.lower(), (m.generic or "")) and al.get("batch", "").lower() in m.raw.lower():
                flags.append(SafetyFlag(severity="call_doctor", title="Batch flagged by the regulator",
                                        detail=f"This batch appears in a {al['month']} alert as '{al['status'].replace('_', ' ')}'. Do not use it; return it to the pharmacy.",
                                        meds=[m.name], source="alert-feed", code="batch_alert", args={"month": al["month"], "status": al["status"]}))
    order = {"call_doctor": 0, "ask_pharmacist": 1, "info": 2}
    return sorted(flags, key=lambda f: order[f.severity])
