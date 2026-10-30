"""A shared daily budget for the hosted demo, so an open link cannot spend the model and search credits without limit.

Three counters for the whole running app (not per visitor): photo reads, model calls and web look-ups. When one is used up, the app falls back to the mode it already has
for visitors without model access: the sample bills and every rule-based price check keep working, and the screens say that the AI part returns tomorrow.
The counters live in memory, so a restart of the app resets them: this is a best-effort guard. The hard limit is the balance on the API keys, which should be a separate
key with a small prepaid balance. Limits come from environment variables (Streamlit secrets); the day rolls over at 00:00 UTC (05:30 India time).
"""
from __future__ import annotations
import datetime, os, threading

LIMITS = {"photo": ("DAWA_DAILY_PHOTO_READS", 100), "model": ("DAWA_DAILY_MODEL_CALLS", 600), "web": ("DAWA_DAILY_WEB_CALLS", 400)}
_lock = threading.Lock()
_state: dict = {"day": None, "used": {}}


def _today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


def limit(kind: str) -> int:
    env, default = LIMITS[kind]
    try:
        return max(0, int(os.environ.get(env, default)))
    except ValueError:
        return default


def _roll() -> None:
    today = _today()
    if _state["day"] != today:
        _state["day"], _state["used"] = today, {}


def used(kind: str) -> int:
    with _lock:
        _roll()
        return _state["used"].get(kind, 0)


def exhausted(kind: str) -> bool:
    return used(kind) >= limit(kind)


def spend(kind: str, n: int = 1) -> bool:
    """Count n uses of `kind` today. False (and nothing counted) when that would pass the limit."""
    with _lock:
        _roll()
        if _state["used"].get(kind, 0) + n > limit(kind):
            return False
        _state["used"][kind] = _state["used"].get(kind, 0) + n
        return True


def reset() -> None:
    with _lock:
        _state["day"], _state["used"] = None, {}
