"""Scheduler agent: turns frequency codes into a daily timetable. Pure code, no model."""
from __future__ import annotations
from . import i18n
from .schemas import Lang, Prescription, ScheduleItem

SLOTS = [("morning", "08:00"), ("afternoon", "14:00"), ("night", "21:00")]


def build_schedule(rx: Prescription, lang: Lang = "en") -> list[ScheduleItem]:
    items: list[ScheduleItem] = []
    for m in rx.medications:
        note = i18n.instruction(m.strength, m.timing, lang)
        if m.frequency == "SOS":
            items.append(ScheduleItem(time="--:--", slot="as_needed", med=m.name,
                                      instruction=f"{note}; {i18n._pick(i18n.TIMETABLE['sos'], lang)}"))
            continue
        if not m.frequency:
            continue
        parts = m.frequency.split("-")
        if len(parts) != 3:
            continue
        for (slot, time), count in zip(SLOTS, parts):
            if count == "1":
                items.append(ScheduleItem(time=time, slot=slot, med=m.name, instruction=note))
    return sorted(items, key=lambda i: i.time)


def share_text(items: list[ScheduleItem], days: int | None = None, lang: Lang = "en") -> str:
    return i18n.share_text(items, days, lang)
