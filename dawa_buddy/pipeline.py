from __future__ import annotations
from . import i18n, llm
from .explainer import explain
from .reader import read_prescription
from .safety import check
from .scheduler import build_schedule
from .schemas import Briefing, Lang

DISCLAIMER = i18n.DISCLAIMER["en"]


def run(text: str, lang: Lang = "en") -> Briefing:
    rx = read_prescription(text)
    return Briefing(prescription=rx, explanations=explain(rx, lang), flags=i18n.localize_flags(check(rx), lang),
                    schedule=build_schedule(rx, lang), language=lang, disclaimer=i18n.DISCLAIMER[lang],
                    mode="offline" if llm.is_offline() else "llm")
