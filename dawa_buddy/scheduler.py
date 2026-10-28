"""Scheduler agent: turns frequency codes into a daily timetable. Pure code, no model."""
from __future__ import annotations
from . import i18n
from .explainer import PHRASES, amount_text
from .schemas import Lang, Prescription, ScheduleItem

SLOTS = [("morning", "08:00"), ("afternoon", "14:00"), ("night", "21:00")]


def build_schedule(rx: Prescription, lang: Lang = "en") -> list[ScheduleItem]:
    """Daily rows say WHAT TO TAKE ('1 tablet (500 mg), after food'), not what is in it. A single dose (STAT, a vaccine) is not part of a daily routine:
    it goes in its own 'once' slot, which the screen shows apart from the table."""
    items: list[ScheduleItem] = []
    for m in rx.medications:
        amount = amount_text(m, lang)
        note = i18n.instruction(amount, m.timing, lang)
        if m.frequency == "SOS":
            items.append(ScheduleItem(time="--:--", slot="as_needed", med=m.name, instruction=f"{amount}; {i18n._pick(i18n.TIMETABLE['sos'], lang)}"))
            continue
        if m.frequency == "STAT":
            items.append(ScheduleItem(time="--:--", slot="once", med=m.name, instruction=f"{amount}. {PHRASES[lang]['stat']}"))
            continue
        if not m.frequency:
            continue
        parts = m.frequency.split("-")
        if len(parts) != 3:
            continue
        for (slot, time), count in zip(SLOTS, parts):
            if count == "1":
                items.append(ScheduleItem(time=time, slot=slot, med=m.name, instruction=note))
    return sorted(items, key=lambda i: (i.slot in ("as_needed", "once"), i.slot == "once", i.time))


def share_text(items: list[ScheduleItem], days: int | None = None, lang: Lang = "en") -> str:
    return i18n.share_text(items, days, lang)
