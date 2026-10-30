"""The shared daily budget: an open demo link must not be able to spend the credits without limit, and must degrade to the rule-based mode, not break."""
import datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dawa_buddy import budget, llm, webcheck, listings

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    budget.reset()
    llm.restrict(False)                      # an earlier app test may have left this thread locked
    for env, _ in budget.LIMITS.values():
        monkeypatch.delenv(env, raising=False)
    yield
    budget.reset()


def test_a_counter_stops_at_its_limit_and_counts_nothing_past_it(monkeypatch):
    monkeypatch.setenv("DAWA_DAILY_MODEL_CALLS", "3")
    assert [budget.spend("model") for _ in range(5)] == [True, True, True, False, False]
    assert budget.used("model") == 3 and budget.exhausted("model") and not budget.exhausted("photo")
    assert budget.spend("model", 0) is True or budget.spend("model", 0) is False        # a zero spend never raises


def test_defaults_and_a_bad_setting_fall_back_to_the_default(monkeypatch):
    assert (budget.limit("photo"), budget.limit("model"), budget.limit("web")) == (100, 600, 400)
    monkeypatch.setenv("DAWA_DAILY_PHOTO_READS", "not a number")
    assert budget.limit("photo") == 100
    monkeypatch.setenv("DAWA_DAILY_PHOTO_READS", "-5")
    assert budget.limit("photo") == 0


def test_the_day_rolls_over_at_utc_midnight(monkeypatch):
    monkeypatch.setenv("DAWA_DAILY_WEB_CALLS", "1")
    day = [datetime.date(2026, 10, 30)]
    monkeypatch.setattr(budget, "_today", lambda: day[0])
    assert budget.spend("web") and not budget.spend("web")
    day[0] = datetime.date(2026, 10, 31)
    assert budget.spend("web")                                                           # a new day, a new budget


def test_an_exhausted_model_budget_makes_the_app_rule_based(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "x")
    monkeypatch.delenv("DAWA_PROVIDER", raising=False)
    monkeypatch.delenv("DAWA_OFFLINE", raising=False)
    monkeypatch.setenv("DAWA_DAILY_MODEL_CALLS", "0")
    assert llm.provider() == "offline" and llm.is_offline() and not llm.vision_available()
    monkeypatch.setenv("DAWA_DAILY_MODEL_CALLS", "5")
    assert llm.provider() == "nebius"


def test_a_model_call_past_the_budget_is_refused_before_it_reaches_the_api(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "x")
    monkeypatch.setenv("DAWA_DAILY_MODEL_CALLS", "0")
    monkeypatch.setattr(llm, "_client", lambda: (_ for _ in ()).throw(AssertionError("the API was called")))
    with pytest.raises(RuntimeError, match="daily model budget"):
        llm._nebius_create(model="m", messages=[])


def test_web_lookups_stop_when_the_web_budget_is_used_up(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    assert webcheck.available()
    monkeypatch.setenv("DAWA_DAILY_WEB_CALLS", "0")
    assert not webcheck.available()
    assert webcheck.lookup_brand("TELMA 40 TAB") is None and listings._tavily("telma 40") == []      # no request is made, nothing raises


def test_the_start_screen_explains_a_used_up_budget_and_samples_still_work(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "nebius")
    monkeypatch.setenv("NEBIUS_API_KEY", "x")
    monkeypatch.setenv("DAWA_DAILY_MODEL_CALLS", "0")
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.run()
    page = " ".join(m.value for m in at.markdown)
    assert not at.exception and "AI budget for this demo is used up" in page and "Read my bill" not in [b.label for b in at.button]
    [b for b in at.button if b.key == "sample_Hospital pharmacy bill"][0].click().run()
    [b for b in at.button if "result" in b.label][0].click().run()
    assert not at.exception and "4 things to ask about" in " ".join(m.value for m in at.markdown)       # the price checks do not need the budget
