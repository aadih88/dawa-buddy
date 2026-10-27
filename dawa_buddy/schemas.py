from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

Lang = Literal["en", "hi", "kn"]
LANG_NAMES = {"en": "English", "hi": "Hindi", "kn": "Kannada"}


class Medication(BaseModel):
    name: str
    generic: Optional[str] = None          # active ingredient(s), lowercase
    strength: Optional[str] = None         # e.g. "650 mg"
    form: Optional[str] = None             # tablet, syrup, ...
    frequency: Optional[str] = None        # normalised: "1-0-1", "SOS", ...
    duration_days: Optional[int] = None
    timing: Optional[str] = None           # "after food" | "before food" | ...
    raw: str = ""


class Prescription(BaseModel):
    medications: list[Medication] = Field(default_factory=list)
    notes: Optional[str] = None


class MedExplanation(BaseModel):
    name: str
    purpose: str
    how_to_take: str = ""                  # built from the prescription by fixed templates, never written by the model
    watch_for: str
    language_fallback: bool = False        # True if requested language unavailable
    fixed: bool = False                    # purpose and watch_for come from the reviewed table (medinfo.py), not a model


class SafetyFlag(BaseModel):
    severity: Literal["info", "ask_pharmacist", "call_doctor"]
    title: str
    detail: str
    meds: list[str] = Field(default_factory=list)
    source: str = "rule"                   # rule | alert-feed | model
    code: str = ""                         # stable id of the rule (see i18n.py): translations are keyed by it, never guessed from the English text
    args: dict = Field(default_factory=dict)   # the values the rule's sentence needs (ingredients, mg, names...)


class ScheduleItem(BaseModel):
    time: str                              # "08:00"
    slot: Literal["morning", "afternoon", "night", "as_needed"]
    med: str
    instruction: str


class Briefing(BaseModel):
    prescription: Prescription
    explanations: list[MedExplanation]
    flags: list[SafetyFlag]
    schedule: list[ScheduleItem]
    language: Lang
    disclaimer: str
    mode: Literal["llm", "offline"]
