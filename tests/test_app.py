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
    """Tap a sample and carry on to its result, the way a person does: sample -> check the numbers -> see the result."""
    [b for b in app.button if b.key == f"sample_{name}"][0].click().run()
    assert app.title[0].value == "Check the numbers"
    [b for b in app.button if b.label in ("See the result", "Looks right, see the result")][0].click().run()          # first run: the button disables itself ...
    app.run()                                                                       # ... the next run shows the result
    return app


def html_blocks(app):
    return " ".join(m.value for m in app.markdown)


def page_text(app):
    """Everything readable on the page: the markdown blocks and the labels of folded rows (a line that reads correctly is a folded row on the review screen)."""
    return html_blocks(app) + " " + " ".join(e.label for e in app.expander)


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
    assert not any("needs your confirmation" in l or l.endswith("· confirmed") for l in labels)       # a bag is not an unknown medicine: no ingredient row
    assert "Within the limits (2)" in labels and "Not covered by a price list (1)" in labels      # the IV set moved up: it is billed far above its printed MRP
    assert "Above the MRP printed on the pack" in page and "IV SET NOVOFUSION" in page


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
    assert "Start over" in {b.label for b in at.button} and {b.label for b in at.button} & {"See the result", "Looks right, see the result"}
    page = page_text(at)
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
    [b for b in at.button if b.label in ("See the result", "Looks right, see the result")][0].click().run()
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
    page = html_blocks(at)
    assert "Strip size and listed price" in page and "CONCOR T 5MG TAB" in page                       # says what the look-up is for and which medicine it covers
    btn = [b for b in at.button if b.label.startswith("Look up 1 line on pharmacy websites")][0]
    assert btn.proto.type == "primary"                                                              # the same action colour as the other main buttons
    btn.click().run()
    assert not at.exception
    assert at.session_state["df"].loc[0, "pack"] == 10                                              # filled in as a suggestion
    assert at.session_state["pack_guess"]["CONCOR T 5MG TAB"][0] == 10 and "pharmacy websites" in at.session_state["pack_guess"]["CONCOR T 5MG TAB"][1]
    assert "consistent with this bill" in " ".join(c.value for c in at.caption)                       # printed 174.75 per 10 = listed
    assert "This line is priced at or below the MRP printed on the pack" in html_blocks(at)             # the MRP check is now possible, and the page says what it checked


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


def test_start_screen_button_says_read_my_bill_and_is_disabled_until_a_photo_is_chosen(monkeypatch):
    from dawa_buddy import llm
    monkeypatch.setattr(llm, "vision_available", lambda: True)
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.run()
    read = [b for b in at.button if b.label == "Read my bill"][0]
    assert read.disabled and not [b for b in at.button if b.label == "Check my bill"]       # the first step reads the bill; it does not "check" it


def test_a_lost_upload_gives_the_start_controls_back_instead_of_crashing(monkeypatch):
    from dawa_buddy import llm
    monkeypatch.setattr(llm, "vision_available", lambda: True)
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["reading"] = True                  # as if the page was refreshed while a photo was being read
    at.run()
    assert not at.exception and at.session_state["reading"] is False
    assert all(not b.disabled for b in at.button if b.key and b.key.startswith("sample_"))


def test_samples_take_the_same_road_as_a_photo_through_the_review_screen():
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.run()
    [b for b in at.button if b.key == "sample_Hospital pharmacy bill"][0].click().run()
    assert at.title[0].value == "Check the numbers" and "Sample:" in " ".join(c.value for c in at.caption)
    assert "Start over" in {b.label for b in at.button} and {b.label for b in at.button} & {"See the result", "Looks right, see the result"}


def test_help_text_in_identify_section_is_for_users_not_about_vendors(monkeypatch):
    """No tooltip should mention Tavily or a URL; each should say what the button gives the user."""
    import re
    src = (ROOT / "bill_app.py").read_text()
    helps = re.findall(r'help="([^"]+)"', src)
    assert helps and not [h for h in helps if re.search(r"tavily|nppa\.gov|sends only", h, re.I)]




def _confirm(at, text, index=0):
    """What a person does: type the ingredients, then press the Confirm button (a bare text box only applies on Enter)."""
    [e for e in at.text_input if "Ingredients" in e.label][index].set_value(text)
    [b for b in at.button if b.label == "Confirm ingredients"][index].click().run()


def _identify_app(monkeypatch, desc="TAB.CONCOR T 5MG"):
    import pandas as pd
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = pd.DataFrame([{"description": desc, "qty": 26, "rate": 18.0, "amount": 468.0, "unit": "tab", "pack": None, "mrp": None, "unsure": False}])
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", 0.0, "results"
    at.run()
    return at


def test_typing_an_ingredient_updates_the_result_in_the_same_step(monkeypatch):
    """Before: the cards and lists stayed stale until the next click, so typing seemed to do nothing."""
    at = _identify_app(monkeypatch)
    assert "cheaper generic" not in html_blocks(at).lower()
    _confirm(at, "bisoprolol 5 mg")          # one interaction, no extra click
    page = html_blocks(at)
    assert "cheaper generic" in page.lower() and "Compared as bisoprolol 5 mg" in page
    assert "Not covered by a price list" not in [e.label for e in at.expander][0]


def test_a_confirmed_item_says_what_the_confirmation_did_and_an_unconfirmed_one_says_nothing_was_judged(monkeypatch):
    at = _identify_app(monkeypatch)
    assert "Not confirmed yet" in " ".join(c.value for c in at.caption)
    _confirm(at, "bisoprolol 5 mg + telmisartan 40 mg")
    assert "Compared as" in html_blocks(at) and "No price list covers this" in html_blocks(at)       # an honest outcome, not silence


def test_not_covered_items_say_why_and_how_they_were_judged(monkeypatch):
    import pandas as pd
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = pd.DataFrame([{"description": "VELTAM 0.4MG TAB", "qty": 15, "rate": 12.66, "amount": 189.9, "unit": "tab", "pack": 15, "mrp": 210.94, "unsure": False}])
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", 0.0, "results"
    at.run()
    page = html_blocks(at)
    assert "Identified as tamsulosin 0.4 mg" in page and "We hold no NPPA ceiling or Jan Aushadhi price" in page
    assert "Charged 90% of the printed MRP" in page




def test_the_identify_box_stays_open_after_a_confirmation_so_the_outcome_is_visible(monkeypatch):
    at = _identify_app(monkeypatch)
    assert not [e for e in at.expander if e.label.startswith("TAB.CONCOR T 5MG")][0].proto.expanded
    _confirm(at, "bisoprolol 5 mg")
    box = [e for e in at.expander if e.label.startswith("TAB.CONCOR T 5MG")][0]
    assert box.proto.expanded and "Compared as bisoprolol 5 mg" in " ".join(m.value for m in at.markdown)







def _bill_app(monkeypatch, rows, rx=""):
    import pandas as pd
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = pd.DataFrame([{"description": d, "qty": q, "rate": r, "amount": round(q * r, 2), "unit": "tab", "pack": pk, "mrp": m, "unsure": False} for d, q, r, pk, m in rows])
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = rx, 0.0, "results"
    at.run()
    return at


REAL4 = [("SHELCAL 500MG TAB", 30, 9.81, 15, 163.45), ("VELTAM 0.4MG TAB", 15, 12.66, 15, 210.94), ("TAB.CONCOR T 5MG/40", 26, 18.1, 15, 271.5)]


def test_a_clean_bill_reads_as_protection_not_as_zeros(monkeypatch):
    """No tiles that say 0: tiles appear only when there is news. The page lists what was checked and found fine, and says when a check does not apply."""
    page = re.sub(r"<style>.*?</style>", "", html_blocks(_bill_app(monkeypatch, REAL4)), flags=re.S)          # what the user sees, not the stylesheet
    assert "All 3 lines are priced at or below the MRP printed on the pack" in page and "Selling above the printed MRP is not allowed" in page
    assert "Not applicable: none of these has a government ceiling" in page           # a neutral grey row, not an alarming 0%
    assert "₹0" not in page and not re.search(r"(?<!\d)0%", page) and "possible saving" not in page    # no zero tiles, no 0%, no empty generic saving
    assert 'class="db-stats"' not in page and 'class="db-check"' in page


def test_tiles_appear_only_when_they_carry_news(monkeypatch):
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    at.run(); click(at, "Hospital pharmacy bill")
    page = html_blocks(at)
    assert "above legal limits" in page                                                # the hospital sample really has amounts above limits
    assert "possible saving with a generic" not in page                               # and no generic saving to show, so no tile


def test_the_prescription_row_says_what_was_checked_in_each_case(monkeypatch):
    none = html_blocks(_bill_app(monkeypatch, REAL4))
    assert "None added. Add one to check you were given the medicines the doctor wrote." in none
    same = html_blocks(_bill_app(monkeypatch, [("SHELCAL 500MG TAB", 30, 9.81, 15, 163.45)], rx="Tab Shelcal 500 1-0-0 x 30 days"))
    assert "The bill matches your prescription" in same
    diff = html_blocks(_bill_app(monkeypatch, [("SHELCAL 500MG TAB", 30, 9.81, 15, 163.45)], rx="Tab Shelcal-XT 0-1-0 to continue"))
    assert "from the prescription, listed below" in diff and "Some lines are above a legal price limit" not in diff


def test_medicines_to_confirm_are_listed_and_leave_the_list_as_you_confirm_them(monkeypatch):
    at = _bill_app(monkeypatch, [("TAB.CONCOR T 5MG/40", 26, 18.1, 15, 271.5), ("TAB.ROSEDAY GOLD 75MG/75MG/10MG", 30, 17.0, 10, 170.0)])
    page = html_blocks(at)
    assert "Medicines to confirm" in page and "TAB.CONCOR T 5MG/40, TAB.ROSEDAY GOLD" in page
    _confirm(at, "bisoprolol 5 mg + telmisartan 40 mg")
    after = html_blocks(at).split("Medicines to confirm")[1].split("</div>")[0]
    assert "TAB.ROSEDAY GOLD" in after and "CONCOR" not in after


def test_the_mrp_row_reads_correctly_with_one_other_line_and_lines_that_could_not_be_compared(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.run(); click(at, "Hospital pharmacy bill")
    page = html_blocks(at)
    assert ("1 line is priced above the MRP printed on the pack. IV SET NOVOFUSION 30115: charged ₹265 per piece, the pack says ₹11. "
            "1 other line is priced at or below its MRP. 5 lines could not be compared because the MRP or the strip size is missing.") in page
    ok = html_blocks(_bill_app(monkeypatch, [("SHELCAL 500MG TAB", 30, 9.81, 15, 163.45), ("DOLO 650 TAB", 10, 2.1, None, None)]))
    assert "1 of 2 lines are priced at or below the MRP printed on the pack" in ok and "1 line could not be compared because the MRP or the strip size is missing" in ok


def _fake_web(monkeypatch):
    """Tavily is not called: one clear answer comes back for any brand, so the buttons can be exercised."""
    from dawa_buddy import webcheck
    monkeypatch.setattr(webcheck, "available", lambda: True)
    calls = []
    def fake(desc, form="tablet"):
        calls.append(desc)
        return webcheck.Evidence(query="q", consensus=frozenset({("bisoprolol", "5mg"), ("telmisartan", "40mg")}), note="Two different sites agree. Check this against your strip.")
    monkeypatch.setattr(webcheck, "lookup_brand", fake)
    return calls


def test_the_online_lookup_button_is_disabled_once_used_and_runs_only_once(monkeypatch):
    calls = _fake_web(monkeypatch)
    at = _identify_app(monkeypatch)
    btn = [b for b in at.button if b.key and b.key.startswith("web_")][0]
    assert not btn.disabled and btn.label == "Look up the ingredients online"
    btn.click().run()
    done = [b for b in at.button if b.key and b.key.startswith("web_")][0]
    assert done.disabled and done.label == "Looked up online (see below)" and len(calls) == 1
    at.run()                                                                         # any later interaction: still disabled, still one search
    assert [b for b in at.button if b.key and b.key.startswith("web_")][0].disabled and len(calls) == 1


def test_the_use_it_button_is_disabled_once_used_and_the_row_stays_open(monkeypatch):
    _fake_web(monkeypatch)
    at = _identify_app(monkeypatch)
    [b for b in at.button if b.key and b.key.startswith("web_")][0].click().run()
    use = [b for b in at.button if b.key and b.key.startswith("use_")][0]
    assert not use.disabled and use.label.startswith("My strip says bisoprolol 5mg + telmisartan 40mg")
    use.click().run()
    used = [b for b in at.button if b.key and b.key.startswith("use_")][0]
    assert used.disabled and used.label.startswith("Using: bisoprolol 5mg + telmisartan 40mg")
    assert [e for e in at.expander if e.label.startswith("TAB.CONCOR T 5MG")][0].proto.expanded
    assert "confirmed" in [e for e in at.expander if e.label.startswith("TAB.CONCOR T 5MG")][0].label


def test_changing_the_ingredients_after_using_a_suggestion_enables_the_button_again(monkeypatch):
    _fake_web(monkeypatch)
    at = _identify_app(monkeypatch)
    [b for b in at.button if b.key and b.key.startswith("web_")][0].click().run()
    [b for b in at.button if b.key and b.key.startswith("use_")][0].click().run()
    [b for b in at.button if b.label == "Change ingredients"][0].click().run()                                  # the user changed their mind
    _confirm(at, "bisoprolol 5 mg")
    assert not [b for b in at.button if b.key and b.key.startswith("use_")][0].disabled


def test_each_medicine_to_identify_is_its_own_collapsed_row_with_a_status(monkeypatch):
    import pandas as pd
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    rows = [("TAB.CONCOR T 5MG/40", 26, 18.1, 15, 271.5), ("TAB.ROSEDAY GOLD 75MG/75MG/10MG", 30, 17.0, 10, 170.0), ("TAB.NEWBRANDX 10MG", 10, 5.0, 10, 60.0)]
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = pd.DataFrame([{"description": d, "qty": q, "rate": r, "amount": round(q * r, 2), "unit": "tab", "pack": pk, "mrp": m, "unsure": False} for d, q, r, pk, m in rows])
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", 0.0, "results"
    at.run()
    mine = [e for e in at.expander if "needs your confirmation" in e.label]
    assert len(mine) == 3 and all(not e.proto.expanded for e in mine)                             # three short rows, none open: the section stays compact
    assert not [e for e in at.expander if e.label.startswith("Help us identify")]                 # no outer box: expanders cannot nest, and the rows are the structure
    _confirm(at, "bisoprolol 5 mg + telmisartan 40 mg")
    labels = [e.label for e in at.expander]
    assert "TAB.CONCOR T 5MG/40 · confirmed" in labels and sum("needs your confirmation" in l for l in labels) == 2


def test_the_government_orders_button_is_disabled_once_searched_for_the_same_text(monkeypatch):
    from dawa_buddy import webcheck
    monkeypatch.setattr(webcheck, "available", lambda: True)
    calls = []
    monkeypatch.setattr(webcheck, "lookup_orders", lambda text: calls.append(text) or ([], []))
    at = _identify_app(monkeypatch)
    _confirm(at, "bisoprolol 5 mg + telmisartan 40 mg")
    btn = [b for b in at.button if b.key and b.key.startswith("ord_")][0]
    assert not btn.disabled and btn.label.startswith("See government price orders")
    btn.click().run()
    done = [b for b in at.button if b.key and b.key.startswith("ord_")][0]
    assert done.disabled and done.label == "Searched: no price order found" and len(calls) == 1
    [b for b in at.button if b.label == "Change ingredients"][0].click().run()
    _confirm(at, "bisoprolol 5 mg + telmisartan 80 mg")     # different text: a new search makes sense
    assert not [b for b in at.button if b.key and b.key.startswith("ord_")][0].disabled


def test_the_text_box_gives_way_to_the_confirmed_state_and_a_change_link(monkeypatch):
    at = _identify_app(monkeypatch)
    assert [e for e in at.text_input if "Ingredients" in e.label] and [b for b in at.button if b.label == "Confirm ingredients"]       # a visible OK button
    _confirm(at, "bisoprolol 5 mg + telmisartan 40 mg")
    assert not [e for e in at.text_input if "Ingredients" in e.label]                                                            # the box has disappeared
    assert not [b for b in at.button if b.label == "Confirm ingredients"] and [b for b in at.button if b.label == "Change ingredients"]
    assert "Compared as" in html_blocks(at)
    [b for b in at.button if b.label == "Change ingredients"][0].click().run()                                                   # a typo is not a dead end
    box = [e for e in at.text_input if "Ingredients" in e.label][0]
    assert box.value == "bisoprolol 5 mg + telmisartan 40 mg"                                                                    # it comes back pre-filled with what was confirmed


def test_using_the_online_suggestion_also_replaces_the_box_and_hides_the_lookup(monkeypatch):
    _fake_web(monkeypatch)
    at = _identify_app(monkeypatch)
    [b for b in at.button if b.key and b.key.startswith("web_")][0].click().run()
    [b for b in at.button if b.key and b.key.startswith("use_")][0].click().run()
    assert not [e for e in at.text_input if "Ingredients" in e.label]
    assert not [b for b in at.button if b.key and b.key.startswith("web_")]                                                      # nothing left to look up once confirmed




def test_pressing_confirm_with_an_empty_box_asks_for_the_ingredients_and_confirms_nothing(monkeypatch):
    at = _identify_app(monkeypatch)
    [b for b in at.button if b.label == "Confirm ingredients"][0].click().run()
    assert "Type the ingredients printed on the strip first." in " ".join(c.value for c in at.caption)
    assert not at.session_state["confirmed"]


def test_the_explainer_is_its_own_section_not_one_more_row_of_the_identify_list(monkeypatch):
    at = _bill_app(monkeypatch, REAL4, rx="Tab Shelcal-XT 0-1-0 to continue")
    page = html_blocks(at)
    assert page.index("Help us identify") < page.index("Understand your prescription")
    assert "Understand your prescription" in page and any(e.label == "Explain my medicines in plain language" for e in at.expander)
    assert "Understand your prescription" not in html_blocks(_bill_app(monkeypatch, REAL4))               # no prescription, no section


def test_change_ingredients_has_the_same_style_as_confirm_ingredients(monkeypatch):
    """Both are the primary button (solid teal, white text); neither borrows the tint of the 'confirmed' banner above."""
    at = _identify_app(monkeypatch)
    confirm = [b for b in at.button if b.label == "Confirm ingredients"][0]
    assert confirm.proto.type == "primary"
    _confirm(at, "bisoprolol 5 mg + telmisartan 40 mg")
    change = [b for b in at.button if b.label == "Change ingredients"][0]
    assert change.proto.type == "primary"


def test_the_same_item_billed_twice_does_not_break_the_page(monkeypatch):
    """A real bill had one medicine on two lines (two batches): widget keys must not collide, and it gets one row."""
    two = [("TAB.CONCOR T 5MG/40", 26, 18.1, 15, 271.5), ("TAB.CONCOR T 5MG/40", 10, 18.1, 15, 271.5), ("SHELCAL 500MG TAB", 30, 9.81, 15, 163.45)]
    at = _bill_app(monkeypatch, two)
    assert not at.exception
    assert [e.label for e in at.expander if "needs your confirmation" in e.label] == ["TAB.CONCOR T 5MG/40 · needs your confirmation"]


def test_a_medicine_we_identified_but_no_price_list_covers_is_not_asked_to_be_confirmed(monkeypatch):
    """Veltam is tamsulosin (brand table) and nothing prices it: there is nothing for the user to confirm, so it must not appear in the identify list."""
    at = _bill_app(monkeypatch, [("VELTAM 0.4MG TAB", 15, 12.66, 15, 210.94), ("TAB.CONCOR T 5MG/40", 26, 18.1, 15, 271.5)])
    labels = [e.label for e in at.expander]
    assert not [l for l in labels if l.startswith("VELTAM")]
    assert [l for l in labels if l.startswith("TAB.CONCOR T")] == ["TAB.CONCOR T 5MG/40 · needs your confirmation"]
    assert "Identified as tamsulosin 0.4 mg" in html_blocks(at)                      # still explained, in the 'not covered' list


def test_the_checklist_row_and_the_identify_list_always_name_the_same_medicines(monkeypatch):
    import re as _re
    rows = [("TAB.CONCOR T 5MG/40", 26, 18.1, 15, 271.5), ("VELTAM 0.4MG TAB", 15, 12.66, 15, 210.94), ("TAB.ROSEDAY GOLD 75MG/75MG/10MG", 30, 17.0, 10, 170.0), ("SHELCAL 500MG TAB", 30, 9.81, 15, 163.45)]
    at = _bill_app(monkeypatch, rows)
    page = html_blocks(at)
    row = _re.search(r"Medicines to confirm</b><span>\d+ medicines? not identified yet: ([^<]*?)\. Confirm them", page).group(1)
    listed = sorted(e.label.split(" · ")[0] for e in at.expander if "needs your confirmation" in e.label)
    assert sorted(row.split(", ")) == listed == ["TAB.CONCOR T 5MG/40", "TAB.ROSEDAY GOLD 75MG/75MG/10MG"]


def test_one_rule_decides_who_needs_identifying():
    import importlib.util, sys
    from dawa_buddy import bill as b
    src = (ROOT / "bill_app.py").read_text()
    assert src.count("needs_identifying(f)") >= 3 and "def needs_identifying" in src
    L = b.BillLine(raw="x", desc="X", qty=1, rate=1.0, amount=1.0, unit="tab", pack=10, mrp=None)
    ask = lambda **kw: __import__("types").SimpleNamespace(basis="", ingredients="", **kw)
    ns = {}
    exec(src[src.index("def needs_identifying"):src.index("def results(")], {"b": b}, ns)
    f = ns["needs_identifying"]
    assert f(ask(tier=b.TIER_NEEDS_CONFIRM)) and f(ask(tier=b.TIER_NO_BENCHMARK))                     # a guess, or nothing matched
    assert not f(__import__("types").SimpleNamespace(basis="", ingredients="tamsulosin", tier=b.TIER_NO_BENCHMARK))   # identified, no price list: nothing to confirm
    assert not f(__import__("types").SimpleNamespace(basis="bag", ingredients="", tier=b.TIER_NO_BENCHMARK))          # an IV bag is not an unknown medicine
    assert f(__import__("types").SimpleNamespace(basis="", ingredients="bisoprolol", tier=b.TIER_NEEDS_CONFIRM))      # an AI guess still needs the strip


def _badge(page, label):
    m = re.search(rf"{re.escape(label)}<span class=\"db-count\">(\d+)</span>", page)
    return int(m.group(1)) if m else None


def test_the_identify_header_counts_only_what_is_pending_and_changes_when_all_is_confirmed(monkeypatch):
    rows = [("TAB.CONCOR T 5MG/40", 26, 18.1, 15, 271.5), ("TAB.ROSEDAY GOLD 75MG/75MG/10MG", 30, 17.0, 10, 170.0)]
    at = _bill_app(monkeypatch, rows)
    page = html_blocks(at)
    assert _badge(page, "Help us identify") == 2 and "Medicines you confirmed" not in page
    _confirm(at, "bisoprolol 5 mg + telmisartan 40 mg")                                    # one of two confirmed: one still pending
    page = html_blocks(at)
    assert _badge(page, "Help us identify") == 1 and "Medicines you confirmed" not in page
    assert sorted(e.label for e in at.expander if e.label.endswith("confirmed") or "needs your confirmation" in e.label)[0].endswith("confirmed")   # both rows still listed
    _confirm(at, "rosuvastatin 10 mg + aspirin 75 mg + clopidogrel 75 mg")                 # the last one
    page = html_blocks(at)
    assert "Help us identify" not in page and _badge(page, "Medicines you confirmed") == 2   # no pending action, so no 'Help us' wording and no pending badge
    assert "Nothing more to do here" in " ".join(c.value for c in at.caption)
    assert len([e for e in at.expander if e.label.endswith("· confirmed")]) == 2          # still there to review or change
    assert [b for b in at.button if b.label == "Change ingredients"]


def test_changing_a_confirmed_answer_keeps_the_section_available(monkeypatch):
    at = _identify_app(monkeypatch)
    _confirm(at, "bisoprolol 5 mg + telmisartan 40 mg")
    assert _badge(html_blocks(at), "Medicines you confirmed") == 1
    [b for b in at.button if b.label == "Change ingredients"][0].click().run()
    assert [e for e in at.text_input if "Ingredients" in e.label]                          # reopened for editing


# ---------------------------------------------------------------- the review screen: staged edits, undo, add, missing numbers
def _review(monkeypatch, rows, **kw):
    import pandas as pd
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    at.session_state["df"] = pd.DataFrame([{"description": d, "qty": q, "rate": r, "amount": round(q * r, 2), "unit": u, "pack": pk, "mrp": m, "unsure": False} for d, q, r, u, pk, m in rows])
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", 0.0, "review"
    at.run()
    return at


ROWS2 = [("TELMA 40 TAB", 10, 12.4, "tab", 30, None), ("SHELCAL 500MG TAB", 30, 9.81, "tab", None, 163.45)]


def test_fix_a_number_is_staged_until_save_changes_is_pressed(monkeypatch):
    at = _review(monkeypatch, ROWS2)
    assert "10 × ₹12.40 = ₹124" in page_text(at)
    at.number_input(key="r0_0_fq0").set_value(20).run()                         # typed, not saved: nothing changes
    assert "10 × ₹12.40 = ₹124" in page_text(at) and "20 × ₹12.40" not in page_text(at)
    at = _review(monkeypatch, ROWS2)
    at.number_input(key="r0_0_fq0").set_value(20)
    [b for b in at.button if b.label == "Save changes"][0].click().run()          # typed and saved: the card changes and the total follows
    assert "20 × ₹12.40 = ₹248" in page_text(at)


def test_the_total_is_always_quantity_times_price_and_is_not_an_input(monkeypatch):
    at = _review(monkeypatch, ROWS2)
    labels = [n.label for n in at.number_input]
    assert not [l for l in labels if l.startswith("Total") and "bill" not in l]    # no per-line Total field (the bill-level 'Total printed' stays)
    at.number_input(key="r0_0_fr0").set_value(10.0)
    [b for b in at.button if b.label == "Save changes"][0].click().run()
    assert "10 × ₹10 = ₹100" in page_text(at)


def test_a_line_whose_total_does_not_add_up_is_marked(monkeypatch):
    import pandas as pd
    at = _review(monkeypatch, ROWS2)
    df = at.session_state["df"].copy(); df.loc[0, "amount"] = 999.0
    at.session_state["df"] = df; at.run()
    assert "Quantity × price does not match the total" in html_blocks(at)


def test_a_removed_line_can_be_put_back(monkeypatch):
    at = _review(monkeypatch, ROWS2)
    [b for b in at.button if b.key == "r0_0_rm"][0].click().run()
    page = html_blocks(at)
    assert "TELMA 40 TAB" not in page.split("Removed lines")[0] if "Removed lines" in page else True
    assert "Removed lines (1)" in [e.label for e in at.expander]
    [b for b in at.button if b.label == "Put back"][0].click().run()
    assert "Removed lines" not in " ".join(e.label for e in at.expander) and "TELMA 40 TAB" in page_text(at)


def test_a_removed_line_is_not_in_the_result_but_can_still_be_restored_after_moving_on(monkeypatch):
    at = _review(monkeypatch, ROWS2)
    [b for b in at.button if b.key == "r0_0_rm"][0].click().run()
    [b for b in at.button if b.label in ("See the result", "Looks right, see the result")][0].click().run()
    assert len(at.session_state["df"]) == 1                                         # the result is built without it
    assert "Removed lines (1)" in [e.label for e in at.expander]                    # ... but it is still recoverable
    [b for b in at.button if b.label == "Put back"][0].click().run()
    assert len(at.session_state["df"]) == 2


def test_add_a_line_is_a_form_with_a_primary_button_and_validates(monkeypatch):
    at = _review(monkeypatch, ROWS2)
    add = [b for b in at.button if b.label == "Add this line"][0]
    assert add.proto.type == "primary"
    add.click().run()                                                              # empty form
    assert "Give the item a name, a quantity and a price first." in " ".join(c.value for c in at.caption) and len(at.session_state["df"]) == 2
    at.text_input(key="new_name0").set_value("DOLO 650 TAB")
    at.number_input(key="new_qty0").set_value(10)
    at.number_input(key="new_rate0").set_value(2.1)
    [b for b in at.button if b.label == "Add this line"][0].click().run()
    assert len(at.session_state["df"]) == 3 and "10 × ₹2.10 = ₹21" in html_blocks(at)


def test_lines_that_need_a_strip_size_are_named_at_the_top_and_flagged_on_the_card(monkeypatch):
    at = _review(monkeypatch, ROWS2)
    page = html_blocks(at)
    assert "1 line needs a number before we can check it" in page and "SHELCAL 500MG TAB" in page.split("needs a number")[1]
    assert "Needed: the MRP of ₹163.45 on the pack is for a whole strip" in page
    assert "1 line will not be checked against its printed MRP" in " ".join(c.value for c in at.caption)
    assert "TELMA 40 TAB" not in page.split("needs a number")[1].split("</div></div>")[0]          # Telma has its pack size: not listed


def test_no_strip_size_note_when_everything_needed_is_filled_in(monkeypatch):
    at = _review(monkeypatch, [("TELMA 40 TAB", 10, 12.4, "tab", 30, None)])
    assert "needs a number" not in html_blocks(at) and "will not be checked" not in " ".join(c.value for c in at.caption)


def test_find_strip_sizes_online_sits_on_the_review_screen_names_the_medicines_and_fills_them_in(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test")
    from dawa_buddy import listings
    monkeypatch.setattr(listings, "search", lambda desc: _listing(163.45, 15))
    at = _review(monkeypatch, ROWS2)
    btn = [b for b in at.button if b.key == "find_strips"][0]
    assert btn.proto.type == "primary" and "SHELCAL 500MG TAB" in btn.label
    btn.click().run()
    assert not at.exception and at.session_state["df"].loc[1, "pack"] == 15
    assert "needs a number" not in html_blocks(at)                                              # the gap is closed; the suggestion is labelled for checking
    assert "Suggested from pharmacy websites" in " ".join(c.value for c in at.caption)


def test_results_lookup_callout_names_the_medicines_it_will_look_up(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test")
    at = _bill_app(monkeypatch, [("SHELCAL 500MG TAB", 30, 9.81, None, 163.45), ("CONCOR T 5MG TAB", 30, 15.73, None, 174.75)])
    page = html_blocks(at)
    assert "Strip size and listed price" in page and "SHELCAL 500MG TAB, CONCOR T 5MG TAB" in page


def test_the_check_rows_name_the_line_and_both_prices_in_plain_words(monkeypatch):
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    at.run(); click(at, "Hospital pharmacy bill")
    page = html_blocks(at)
    assert "AACEF 250 INJ: charged ₹90 per vial, the legal limit is ₹29.02" in page             # which line, what was charged, what the limit is
    assert "2 of 5 price-controlled lines are above the legal ceiling price." in page
    assert "Charged above the printed MRP on" not in page and "other line is within it" not in page    # the old, hard-to-read wording is gone


def test_a_vaccine_is_shown_apart_from_the_daily_timetable(monkeypatch):
    at = _bill_app(monkeypatch, [("SHELCAL 500MG TAB", 30, 9.81, 15, 163.45)], rx="Tab Glycomet 500 mg 1-0-0 x 30 days after food\nINJ INFLUVAC TETRA 1 ML IM STAT")
    at.segmented_control[0].set_value("English")
    [b for b in at.button if b.label == "Explain"][0].click().run()
    page = html_blocks(at)
    assert "One-time dose (not part of the daily routine)" in page and "One single dose, given once." in page
    rows = [row for tbl in at.table for row in tbl.value.to_dict("records")]
    assert [r["Medicine"] for r in rows] == ["Glycomet"]                                         # the table holds only the daily routine
    assert rows[0]["How"] == "1 tablet (500 mg), after food"                                     # an amount, not a bare strength


# ---------------------------------------------------------------- the access code: a leaked link must not be able to spend model credits
def _gated(monkeypatch, code="judge-1234", stage="start", **state):
    monkeypatch.delenv("DAWA_PROVIDER", raising=False)
    monkeypatch.delenv("DAWA_OFFLINE", raising=False)
    monkeypatch.setenv("NEBIUS_API_KEY", "key")
    monkeypatch.setenv("TAVILY_API_KEY", "tav")
    if code:
        monkeypatch.setenv("DAWA_ACCESS_CODE", code)
    else:
        monkeypatch.delenv("DAWA_ACCESS_CODE", raising=False)
    monkeypatch.setattr("time.sleep", lambda s: None)
    at = AppTest.from_file(str(ROOT / "bill_app.py"), default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    if stage != "start":
        at.session_state["stage"] = stage
    at.run()
    return at


def _boom(*a, **k):
    raise AssertionError("a model or web call was made without the access code")


def test_without_a_configured_code_there_is_no_gate(monkeypatch):
    at = _gated(monkeypatch, code=None)
    assert "I have an access code" not in " ".join(e.label for e in at.expander)
    assert "Read my bill" in [b.label for b in at.button]                                   # photo reading is on, as in local use


def test_with_a_code_the_visitor_starts_locked_with_only_the_samples(monkeypatch):
    at = _gated(monkeypatch)
    labels = [b.label for b in at.button]
    assert "Read my bill" not in labels and "Outpatient pharmacy bill" in labels and "Hospital pharmacy bill" in labels
    assert "I have an access code" in [e.label for e in at.expander] and "access code" in html_blocks(at)


def test_a_wrong_code_does_not_unlock_and_the_right_one_does(monkeypatch):
    at = _gated(monkeypatch)
    at.text_input[0].set_value("wrong"); [b for b in at.button if b.label == "Unlock"][0].click().run()
    assert "That code is not right." in " ".join(c.value for c in at.caption) and "Read my bill" not in [b.label for b in at.button]
    at.text_input[0].set_value("judge-1234"); [b for b in at.button if b.label == "Unlock"][0].click().run()
    assert "Read my bill" in [b.label for b in at.button] and "I have an access code" not in [e.label for e in at.expander]


def test_unlocking_survives_starting_another_bill(monkeypatch):
    at = _gated(monkeypatch, unlocked=True)
    at.session_state["df"] = __import__("dawa_buddy.samples", fromlist=["frame"]).frame("Outpatient pharmacy bill")
    at.session_state["rx"], at.session_state["total"], at.session_state["stage"] = "", 0.0, "results"
    at.run()
    [b for b in at.button if b.label == "Check another bill"][0].click().run()
    assert "Read my bill" in [b.label for b in at.button] and at.session_state["unlocked"] is True


def test_a_locked_visitor_cannot_make_any_model_or_web_call(monkeypatch):
    from dawa_buddy import llm, webcheck, listings
    for fn in ("chat", "chat_json", "chat_vision_json"):
        if hasattr(llm, fn):
            monkeypatch.setattr(llm, fn, _boom)
    monkeypatch.setattr(listings, "search", _boom)
    monkeypatch.setattr(webcheck, "lookup_brand", _boom)
    monkeypatch.setattr(webcheck, "lookup_orders", _boom)
    at = _gated(monkeypatch)
    [b for b in at.button if b.key == "sample_Hospital pharmacy bill"][0].click().run()
    [b for b in at.button if b.label in ("See the result", "Looks right, see the result")][0].click().run()
    at.run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert not [l for l in labels if l.startswith("Look up")]                               # no web look-up buttons at all
    [e for e in at.expander if e.label == "Explain my medicines in plain language"][0]
    for lang in ("हिन्दी", "ಕನ್ನಡ"):
        at.segmented_control[0].set_value(lang).run()
        [b for b in at.button if b.label == "Explain"][0].click().run()
        assert not at.exception
        assert "AI text is switched off without the access code" in " ".join(c.value for c in at.caption)


def test_an_unlocked_visitor_gets_everything_back(monkeypatch):
    from dawa_buddy import llm
    at = _gated(monkeypatch, unlocked=True)
    assert llm.provider() == "nebius" and not llm.restricted()
    assert "Read my bill" in [b.label for b in at.button]


def test_restriction_is_per_visitor_not_global():
    import threading
    from dawa_buddy import llm
    seen = {}
    def other():
        seen["other"] = llm.restricted()
    llm.restrict(True)
    t = threading.Thread(target=other); t.start(); t.join()
    assert llm.restricted() is True and seen["other"] is False                            # another visitor's thread is unaffected
    llm.restrict(False)
