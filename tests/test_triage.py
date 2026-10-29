"""Which lines the review screen folds away, which it opens, and what the banner says. The decision is a plain function; the screen only draws it."""
import pandas as pd
from streamlit.testing.v1 import AppTest

from dawa_buddy import review_triage as rt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_line_status_rules():
    assert rt.line_status(6, 2.24, 13.44, "tab")[0] == rt.OK
    assert rt.line_status(6, 2.24, 12.0, "tab")[0] == rt.FIX                               # does not multiply out
    assert rt.line_status(6, None, 12.0, "tab")[0] == rt.FIX                               # a missing number
    assert rt.line_status(6, 2.24, 13.44, "tab", unsure=True)[0] == rt.CHECK               # hard-to-read digits
    assert rt.line_status(6, 2.24, 13.44, None)[0] == rt.CHECK                             # how it was sold is unknown
    assert rt.line_status(6, 2.24, 13.44, "tab", notes=["Quantity, price and value were picked from the printed numbers so that they multiply out."])[0] == rt.CHECK
    assert rt.line_status(6, 2.24, 13.44, "tab", notes=["The bill prints the MRP per tablet, tax included."])[0] == rt.OK        # information only
    assert rt.line_status(float("nan"), 2.0, 4.0, "tab")[0] == rt.FIX


def test_bill_tie():
    assert rt.bill_tie([82.95, 201.7, 278.0, 35.5, 50.05], 648.0) == ("match", 648.2)     # a rupee of rounding on the bill is fine
    assert rt.bill_tie([10.0, 20.0], 40.0)[0] == "mismatch"
    assert rt.bill_tie([10.0], None)[0] == "none" and rt.bill_tie([10.0], 0)[0] == "none"


def _review(monkeypatch, rows, total=0.0, notes=None):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = pd.DataFrame([{"description": d, "qty": q, "rate": r, "amount": a, "unit": u, "pack": None, "mrp": None, "unsure": False} for d, q, r, a, u in rows])
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", total, "review"
    at.session_state["line_notes"] = notes or {}
    at.run()
    return at


def _banner(at):
    return " ".join(m.value for m in at.markdown)


GOOD = [("DOLO 650MG TAB", 6, 2.24, 13.44, "tab"), ("PAN 40MG TAB", 6, 11.0, 66.0, "tab")]


def test_all_clear_bill_is_one_tap(monkeypatch):
    at = _review(monkeypatch, GOOD, total=79.44)
    page = _banner(at)
    assert "2 lines read." in page and "Every line multiplies out." in page and "add up to the printed total" in page
    assert [b for b in at.button if b.label == "Looks right, see the result"]
    assert sorted(e.label[:1] for e in at.expander if e.label.startswith("✓")) == ["✓", "✓"]          # both lines are folded rows
    assert not [e for e in at.expander if e.label.startswith("✓") and e.proto.expanded]


def test_a_line_that_does_not_multiply_out_opens_and_the_total_points_at_it(monkeypatch):
    at = _review(monkeypatch, [GOOD[0], ("PAN 40MG TAB", 6, 11.0, 58.92, "tab")], total=79.44)
    page = _banner(at)
    assert "1 needs a correction." in page and "add up to ₹72.36 but the total on the bill is ₹79.44" in page
    assert not [b for b in at.button if b.label == "Looks right, see the result"] and [b for b in at.button if b.label == "See the result"]
    assert "✓ DOLO 650MG TAB: 6 × ₹2.24 = ₹13.44" in [e.label for e in at.expander]
    assert not any(e.label.startswith("✓ PAN") for e in at.expander)                                   # the bad line is open, not folded


def test_numbers_chosen_by_the_reader_are_shown_open_with_a_reason(monkeypatch):
    at = _review(monkeypatch, GOOD, total=79.44, notes={"PAN 40MG TAB": ["Quantity, price and value were picked from the printed numbers so that they multiply out."]})
    page = _banner(at)
    assert "1 to compare with your paper." in page and "We chose these numbers so they multiply out" in page
    assert not any(e.label.startswith("✓ PAN") for e in at.expander) and any(e.label.startswith("✓ DOLO") for e in at.expander)


def test_a_discount_on_the_whole_bill_explains_the_gap_between_the_lines_and_the_total():
    lines = [114.60, 75.00]                                                                  # the real WhatsApp bill: TOTAL AMT 189.60, LESS DIS 20.00, Net Amt (R/O) 170.00
    assert rt.settle_discount(lines, 170.0, 20.0) == (20.0, "read")
    assert rt.settle_discount(lines, 170.0, None) == (19.6, "inferred")                         # no discount printed: the gap is named, and said to be inferred
    assert rt.settle_discount(lines, 189.6, 20.0) == (0.0, "")                                  # the lines already add up: a "discount" the reader invented is ignored
    assert rt.settle_discount(lines, None, 20.0) == (20.0, "read") and rt.settle_discount(lines, 50.0, None) == (0.0, "")     # 74% off is not a discount, it is a misread
    assert rt.bill_tie(lines, 170.0, 20.0)[0] == "match" and rt.bill_tie(lines, 170.0)[0] == "mismatch"      # a rupee of round-off is fine, the whole discount is not


def test_the_review_banner_names_the_discount_and_the_lines_it_applies_to(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    rows = [("CIFRAN CT TAB", 6, 19.1, 114.6, "tab"), ("SHDICLO SP TAB", 6, 12.5, 75.0, "tab")]
    at.session_state["df"] = pd.DataFrame([{"description": d, "qty": q, "rate": r, "amount": a, "unit": u, "pack": 10, "mrp": 191.0, "unsure": False, "mrp_each": False} for d, q, r, a, u in rows])
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"], at.session_state["discount0"] = "", 170.0, "review", 20.0      # as read_photos sets them
    at.run()
    page = _banner(at)
    assert "less the ₹20 discount on the whole bill, that is the printed total, ₹170" in page
    assert "Discount on the whole bill: ₹20" in [e.label for e in at.expander]


def test_both_samples_open_on_a_clean_review_screen_not_a_wall_of_amber(monkeypatch):
    # the first thing a demo viewer sees: a bill that multiplies out and adds up must not raise warnings about its own sample
    # (found 29 Oct 2026: IV fluids and a syringe had no unit, and an unreadable sample dose, each reported up to three times)
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    for name in ("Hospital pharmacy bill", "Outpatient pharmacy bill"):
        at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
        at.run()
        [b for b in at.button if b.key == f"sample_{name}"][0].click().run()
        page = _banner(at)
        assert "Every line multiplies out." in page and "add up to the printed total" in page, name
        assert "need a number" not in page and "could not read the dose" not in page and "to compare with your paper" not in page, name
        assert [b for b in at.button if b.label == "Looks right, see the result"], name


def test_a_missing_unit_is_missing_whether_pandas_makes_it_none_or_nan():
    # the deployed app runs a newer pandas than the tests did: a missing unit became NaN, which is truthy, so no unit was ever defaulted (found 29 Oct 2026)
    import importlib.util
    spec = importlib.util.spec_from_file_location("bill_app_ns", ROOT / "bill_app.py")
    src = (ROOT / "bill_app.py").read_text()
    start = src.index("def default_units"); end = src.index("def billed_word")
    ns = {"pd": pd, "re": __import__("re"), "b": __import__("dawa_buddy.bill", fromlist=["x"]), "injectables": __import__("dawa_buddy.injectables", fromlist=["x"])}
    exec(src[start:end], ns)
    for missing in (None, float("nan")):
        df = pd.DataFrame({"description": ["SYRINGE 10ML WITH NEEDLE", "NS 0.9% 100ML", "AACEF 250 INJ", "TELMA 40 TAB"], "unit": [missing] * 4})
        assert list(ns["default_units"](df)["unit"]) == ["each", "each", "vial", None], missing
