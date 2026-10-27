"""The app must load, run both samples end to end offline, lead with the verdict, and never nest expanders. Headless AppTest."""
import pathlib
import re

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    return AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60).run()


def click(app, name):
    [b for b in app.button if b.key == f"sample_{name}"][0].click().run()
    return app


def html_blocks(app):
    return " ".join(m.value for m in app.markdown)


def test_start_screen_is_just_a_question_and_two_samples(app):
    assert not app.exception
    assert app.title[0].value == "Was your medicine bill fair?"
    assert [b.label for b in app.button] == ["Outpatient pharmacy bill", "Hospital pharmacy bill"]
    assert not app.metric and not app.dataframe          # no tables, no clutter before there is something to say


def test_there_is_no_sidebar_navigation_page_left():
    assert not (ROOT / "pages").exists() and not (ROOT / "app.py").exists()


def test_outpatient_sample_leads_with_a_verdict_then_plain_english_cards(app):
    click(app, "Outpatient pharmacy bill")
    assert not app.exception
    page = html_blocks(app)
    assert "4 things to ask about" in page
    assert page.index("4 things to ask about") < page.index("Above the legal ceiling price")      # verdict first
    for text in ("Check before taking", "Above the MRP printed on the pack", "Above the legal ceiling price",
                 "A cheaper generic exists: ask your doctor", "You paid ₹12.40 per tablet", "Legal limit ₹6.92", "Printed MRP ₹8", "Generic ₹0.91"):
        assert text in page, text
    assert page.count('class="db-meter"') == 3 and page.count('class="db-diff"') == 1                    # three price meters (MRP, ceiling, generic) and the Prescribed -> On the bill comparison
    assert "generic_gap" not in page and "above_ceiling" not in page          # no internal names reach the user
    assert not [d for d in app.dataframe if not str(d.key).startswith("editor_")]   # results are cards, not clipped table cells


def test_hospital_sample_asks_which_saline_pack_instead_of_accusing(app):
    click(app, "Hospital pharmacy bill")
    assert not app.exception
    page = html_blocks(app)
    assert "Please confirm what this is" in page and "special-features ceiling" in page and "Above the legal ceiling price" in page
    labels = [e.label for e in app.expander]
    assert not any(l.startswith("Help us identify") for l in labels)            # a bag is not an unknown medicine: no ingredient box
    assert "Within the limits (2)" in labels and "Not covered by a price list (2)" in labels


def test_detail_sections_start_folded_away(app):
    click(app, "Outpatient pharmacy bill")
    assert all(not e.proto.expanded for e in app.expander)


def test_explain_my_medicines_runs_offline_inside_the_result(app):
    click(app, "Outpatient pharmacy bill")
    [b for b in app.button if b.key == "explain"][0].click().run()
    assert not app.exception and any("Offline mode" in c.value for c in app.caption)


def test_review_screen_shows_one_readable_card_per_line_not_a_wide_table(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    from dawa_buddy import samples
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = samples.frame("Outpatient pharmacy bill")
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", 0.0, "review"
    at.run()
    assert not at.exception and at.title[0].value == "Check the numbers"
    assert {"Start over", "Check this bill"} <= {b.label for b in at.button}
    page = html_blocks(at)
    assert "SHELCAL 500MG TAB" in page and "30 × ₹9.81 = ₹294.21" in page                  # what we read, in one line, to compare with the paper
    assert not [d for d in at.dataframe]                                                     # no wide table to scroll sideways on a phone


def test_changing_a_number_on_a_card_changes_the_result(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    from dawa_buddy import samples
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = samples.frame("Outpatient pharmacy bill")
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", 0.0, "review"
    at.run()
    assert "legal limit ₹6.92" not in html_blocks(at)
    [b for b in at.button if b.label == "Check this bill"][0].click().run()
    assert not at.exception and "Above the legal ceiling price" in html_blocks(at)


def test_nppa_price_context_card_appears_after_a_lookup_and_is_not_called_a_limit(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    from dawa_buddy import nppa_orders as N, samples
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    df = samples.frame("Outpatient pharmacy bill")
    at.session_state["df"] = df[df["description"].str.startswith("VELTAM")].reset_index(drop=True)      # one line, so the verdict is about it alone
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", 0.0, "results"
    rows = [N.OrderRow((("tamsulosin", 0.4),), "tablet", "M/s A Ltd. / M/s B Ltd.", 9.0), N.OrderRow((("tamsulosin", 0.4),), "tablet", "M/s C Ltd.", 10.0)]
    at.session_state["orders"] = {"veltam 0.4mg tab": (((rows, ["https://nppa.gov.in/x.pdf"])), "tamsulosin 0.4 mg")}
    at.run()
    page = html_blocks(at)
    assert not at.exception
    assert "Same combination, price-controlled lower elsewhere" in page and "2 other companies: ₹9 to ₹10 per tablet before GST" in page
    assert "not a legal limit on your brand" in page and "Do not switch on your own" in page
    assert "Nothing above a legal limit, but a few questions" in page                       # the verdict counts this question too


def test_the_same_item_billed_twice_does_not_break_the_page(monkeypatch):
    """A real bill had one medicine on two lines (two batches): widget keys must not collide."""
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    import pandas as pd
    from dawa_buddy import samples
    df = samples.frame("Outpatient pharmacy bill")
    df = pd.concat([df, df[df["description"].str.startswith("VELTAM")]], ignore_index=True)     # the Veltam line twice
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = df
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", 0.0, "results"
    at.run()
    assert not at.exception
    assert sum(1 for e in at.expander if e.label.startswith("Check more on")) == 1
    assert "Check more on 1 item" in [e.label for e in at.expander]                          # Veltam once; Shelcal is a supplement


def test_a_model_guess_is_never_prefilled_into_the_confirm_box(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    from dawa_buddy import bill as b
    line = b.BillLine("x", "CONCOR T 5MG TAB", 30, 15.73, 471.82, "tab")
    f = b.Finding(line, b.TIER_NEEDS_CONFIRM, "bisoprolol", "5 mg", via_model=True)
    import importlib, sys, types
    st_stub = types.SimpleNamespace(session_state={})
    app_src = (ROOT / "bill_app.py").read_text().split("def prefill")[1].split("def peer_cards")[0]
    ns = {"b": b}
    exec("def prefill" + app_src, ns)
    assert ns["prefill"](f) == ""                                                           # the AI said bisoprolol; the tablet also has telmisartan
    table = b.Finding(line, b.TIER_NO_BENCHMARK, "tamsulosin", "0.4 mg")
    assert ns["prefill"](table) == "tamsulosin 0.4 mg"                                      # from the brand table: pre-filled to confirm


def _bill(rows):
    import pandas as pd
    cols = ["description", "qty", "rate", "amount", "unit", "pack", "mrp", "unsure"]
    return pd.DataFrame([{**dict(zip(cols, r)), "unsure": False} for r in rows], columns=cols)


def _listing(per_strip, pack):
    from dawa_buddy import listings as L
    pages = [L.Page(d, "https://" + d + "/x", "t", pack, per_strip) for d in ("pharmeasy.in", "1mg.com", "truemeds.in")]
    return L.combine("q", pages)


def test_one_button_fills_pack_sizes_and_checks_the_mrp_against_pharmacy_listings(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    monkeypatch.setenv("TAVILY_API_KEY", "test")
    from dawa_buddy import listings
    monkeypatch.setattr(listings, "search", lambda desc: _listing(174.75, 10))
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = _bill([("CONCOR T 5MG TAB", 30, 15.73, 471.82, "tab", None, 174.75)])      # MRP printed, strip size not
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", 0.0, "results"
    at.run()
    assert "tablets-per-strip" in " ".join(c.value for c in at.caption)                             # the nudge, and no MRP check yet
    [b for b in at.button if b.label.startswith("Look up 1 line on pharmacy websites")][0].click().run()
    assert not at.exception
    assert at.session_state["df"].loc[0, "pack"] == 10                                              # filled in as a suggestion
    assert at.session_state["pack_guess"]["CONCOR T 5MG TAB"][0] == 10 and "pharmacy websites" in at.session_state["pack_guess"]["CONCOR T 5MG TAB"][1]
    assert "consistent with this bill" in " ".join(c.value for c in at.caption)                       # printed 174.75 per 10 = listed
    assert re.search(r"100%</b><span[^>]*>of the bill checked", html_blocks(at))


def test_a_bill_without_mrp_charging_above_the_listed_mrp_gets_a_question_not_a_violation(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    monkeypatch.setenv("TAVILY_API_KEY", "test")
    from dawa_buddy import listings
    monkeypatch.setattr(listings, "search", lambda desc: _listing(174.75, 10))
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = _bill([("CONCOR T 5MG TAB", 10, 20.00, 200.00, "tab", None, None)])        # Rs 20 per tablet; listed 17.475
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", 0.0, "results"
    at.run()
    [b for b in at.button if b.label.startswith("Look up")][0].click().run()
    page = html_blocks(at)
    assert not at.exception and "Above the MRP listed online" in page and "ask to see the MRP on the strip" in page
    assert "Above the MRP printed on the pack" not in page                                            # never the violation label
    assert "a few questions" in page                                                                  # counted in the verdict


def test_button_is_absent_without_a_tavily_key_or_when_nothing_is_missing(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = _bill([("CONCOR T 5MG TAB", 30, 15.73, 471.82, "tab", None, 174.75)])
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", 0.0, "results"
    at.run()
    assert not [b for b in at.button if b.label.startswith("Look up")]


def test_explainer_labels_follow_the_chosen_language(monkeypatch):
    """'From your prescription' and 'Watch for' are fixed phrases per language, not English next to a Hindi sentence."""
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    from dawa_buddy import samples
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = samples.frame("Outpatient pharmacy bill")
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "Telma 40 tab 1-0-0 for 30 days", 0.0, "results"
    at.run()
    at.segmented_control[0].set_value("हिन्दी").run()
    [b for b in at.button if b.label == "Explain"][0].click().run()
    page = html_blocks(at)
    assert not at.exception and "आपके प्रिस्क्रिप्शन से" in page and "From your prescription" not in page
    assert "How to take it" not in page


def _review_with(monkeypatch, rx_text, stage="review"):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    from dawa_buddy import samples
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = samples.frame("Outpatient pharmacy bill")
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = rx_text, 0.0, stage
    at.run()
    return at


def test_unreadable_dose_gets_one_warning_and_opens_the_prescription_box(monkeypatch):
    at = _review_with(monkeypatch, "TAB SHELCAL-XT 0---0 TO CONTINUE\nTab Telma 40 1-0-0 x 30 days\nTAB OTHER 500MG TO CONTINUE")
    page = html_blocks(at)
    assert not at.exception and page.count("We could not read the dose on 2 prescription lines") == 1   # one note for all lines, not one card each
    assert "TAB SHELCAL-XT 0---0 TO CONTINUE" in page and "TAB OTHER 500MG TO CONTINUE" in page and "Telma" not in page.split("We could not read")[1].split("</div></div>")[0]
    assert [e for e in at.expander if e.label == "Prescription lines"][0].proto.expanded


def test_no_dose_warning_when_every_dose_reads(monkeypatch):
    at = _review_with(monkeypatch, "Tab Telma 40 1-0-0 x 30 days\nTAB SHELCAL-XT 0---1---0 TO CONTINUE\nINJ INFLUVAC 1 ML IM STAT\nTab Dolo 650 SOS")
    assert "We could not read the dose" not in html_blocks(at) and not [e for e in at.expander if e.label == "Prescription lines"][0].proto.expanded


def test_the_warning_also_shows_in_the_explainer_on_the_result_screen(monkeypatch):
    at = _review_with(monkeypatch, "TAB SHELCAL-XT 0---0 TO CONTINUE", stage="results")
    assert "We could not read the dose on 1 prescription line" in html_blocks(at)
