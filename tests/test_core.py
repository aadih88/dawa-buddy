import os
os.environ["DAWA_OFFLINE"] = "1"
from dawa_buddy.reader import read_offline
from dawa_buddy.safety import check
from dawa_buddy.scheduler import build_schedule
from dawa_buddy.pipeline import run


def titles(text, alerts=None):
    return {f.title for f in check(read_offline(text), alerts=alerts)}


def test_reader_parses_indian_format():
    m = read_offline("Tab Dolo 650 mg 1-0-1 x 5 days after food").medications[0]
    assert (m.generic, m.strength, m.frequency, m.duration_days, m.timing) == ("paracetamol", "650 mg", "1-0-1", 5, "after food")


def test_reader_never_invents_missing_fields():
    m = read_offline("Tab Pantop 40 mg").medications[0]
    assert m.frequency is None and m.duration_days is None


def test_warfarin_nsaid_flagged_as_call_doctor():
    flags = check(read_offline("Tab Warfarin 5 mg 0-0-1 x 30 days\nTab Voveran 50 mg BD x 5 days"))
    assert any(f.title == "Bleeding risk" and f.severity == "call_doctor" for f in flags)


def test_no_false_alarm_on_safe_combo():
    assert not (titles("Tab Glycomet 500 mg 1-0-1 x 30 days\nTab Telma 40 mg 1-0-0 x 30 days") - {"Something is not written"})


def test_paracetamol_total_over_4g():
    assert "Paracetamol above 4 g a day" in titles("Tab Dolo 650 mg 1-1-1 x 3 days\nTab Paracetamol 1000 mg TDS x 3 days")


def test_alert_feed_matches_batch_only():
    alerts = [{"drug": "examplecillin", "batch": "TEST-001", "month": "2026-01", "status": "not_of_standard_quality"}]
    assert "Batch flagged by the regulator" in titles("Tab Examplecillin 500 mg BD x 5 days batch TEST-001", alerts)
    assert "Batch flagged by the regulator" not in titles("Tab Examplecillin 500 mg BD x 5 days batch OTHER-9", alerts)


def test_schedule_slots():
    items = build_schedule(read_offline("Tab Dolo 650 mg 1-0-1 x 5 days"))
    assert [i.slot for i in items] == ["morning", "night"]


def test_pipeline_offline_end_to_end():
    b = run("Tab Dolo 650 mg 1-0-1 x 5 days", "hi")
    assert b.mode == "offline" and b.explanations[0].language_fallback          # offline has no model text, and says so
    assert "यह बीमारी की पहचान नहीं करता" in b.disclaimer                          # the disclaimer is Hindi, from the fixed table
    assert b.explanations[0].how_to_take.startswith("दिन में 2 बार")             # and so is the dose, from the dose templates


# ---- Hindi / Kannada: right script or an honest English fallback, never garbled text ----
def _fake_chat(monkeypatch, answer):
    """answer(system, user, model) -> dict | Exception for every llm.chat_json call; returns the list of (kind, model) calls made."""
    from dawa_buddy import llm
    seen = []
    def fake(system, user, model=None, retries=2):
        seen.append(("repair" if system.startswith("Rewrite") else "explain", model))
        r = answer(system, user, model, len(seen))
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(llm, "chat_json", fake)
    monkeypatch.setattr(llm, "is_offline", lambda: False)
    return seen


def _kn(**over):
    return {"name": "Dolo", "purpose": "ಈ ಔಷಧಿ ಜ್ವರ ಮತ್ತು ನೋವನ್ನು ಕಡಿಮೆ ಮಾಡುತ್ತದೆ.", "how_to_take": "ದಿನಕ್ಕೆ ಎರಡು ಬಾರಿ ಊಟದ ನಂತರ ಒಂದು ಮಾತ್ರೆ ತೆಗೆದುಕೊಳ್ಳಿ.",
            "watch_for": "ಹೊಟ್ಟೆ ನೋವು ಬಂದರೆ ವೈದ್ಯರನ್ನು ಕೇಳಿ.", **over}


ENGLISH = {"explanations": [{"name": "Shelcal", "purpose": "Reduces fever.", "how_to_take": "1 tablet twice a day.", "watch_for": "Stomach upset."}]}
RX = "Tab Shelcal 500 mg 1-0-1 x 5 days"      # calcium: deliberately not in the fixed table (medinfo.py), so these tests exercise the model path


def test_kannada_that_stays_garbled_is_never_shown_and_the_english_fallback_is_flagged(monkeypatch):
    monkeypatch.setenv("DAWA_KN_MODEL_TEXT", "1")      # the opt-in path: AI-written Kannada
    from dawa_buddy.explainer import explain
    from dawa_buddy.reader import read_offline
    garbled = {"explanations": [_kn(purpose="ಈ ಔಷಧಿ ಜ್ವರ ಮತ್ತು ನೋವು ಕಡಿಮೆ ಮಾಡುತ್ತದೆ খাবার ದಿನಕ್ಕೆ.")]}      # Bengali letters inside Kannada
    def answer(system, user, model, n):
        return {"text": "খাবার"} if system.startswith("Rewrite") else garbled if "Kannada" in system else ENGLISH
    seen = _fake_chat(monkeypatch, answer)
    out = explain(read_offline(RX), "kn")
    assert out[0].language_fallback is True and out[0].purpose == "Reduces fever."     # never garbled Kannada, never silent English
    assert [k for k, _ in seen].count("explain") == 4 and seen[0][1] == "nvidia/Nemotron-3-Ultra-550b-a55b"   # 3 Kannada tries + the English fallback


def test_a_stray_word_is_repaired_in_place_instead_of_discarding_the_answer(monkeypatch):
    monkeypatch.setenv("DAWA_KN_MODEL_TEXT", "1")      # the opt-in path: AI-written Kannada
    from dawa_buddy.explainer import explain
    from dawa_buddy.reader import read_offline
    slipped = {"explanations": [_kn(watch_for="ಚक्कರ ಬಂದರೆ ವೈದ್ಯರನ್ನು ಕೇಳಿ.")]}          # a Devanagari word inside Kannada
    def answer(system, user, model, n):
        return {"text": "ತಲೆಸುತ್ತು ಬಂದರೆ ವೈದ್ಯರನ್ನು ಕೇಳಿ."} if system.startswith("Rewrite") else slipped
    seen = _fake_chat(monkeypatch, answer)
    out = explain(read_offline(RX), "kn")
    assert not out[0].language_fallback and out[0].watch_for == "ತಲೆಸುತ್ತು ಬಂದರೆ ವೈದ್ಯರನ್ನು ಕೇಳಿ."
    assert [k for k, _ in seen] == ["explain", "repair"]


def test_hindi_tries_the_next_model_when_the_first_answers_in_english(monkeypatch):
    from dawa_buddy.explainer import explain
    from dawa_buddy.reader import read_offline
    hindi = {"explanations": [{"name": "Dolo", "purpose": "यह दवा बुखार और दर्द कम करती है।", "how_to_take": "दिन में दो बार खाने के बाद एक गोली लें।",
                               "watch_for": "पेट में दर्द हो तो डॉक्टर से पूछें।"}]}
    seen = _fake_chat(monkeypatch, lambda s, u, m, n: ENGLISH if n == 1 else hindi)
    out = explain(read_offline(RX), "hi")
    assert not out[0].language_fallback and "दवा" in out[0].purpose and [m for _, m in seen][0] != [m for _, m in seen][1]


def test_clean_kannada_is_accepted_first_time(monkeypatch):
    monkeypatch.setenv("DAWA_KN_MODEL_TEXT", "1")      # the opt-in path: AI-written Kannada
    from dawa_buddy.explainer import explain
    from dawa_buddy.reader import read_offline
    seen = _fake_chat(monkeypatch, lambda s, u, m, n: {"explanations": [_kn()]})
    out = explain(read_offline(RX), "kn")
    assert not out[0].language_fallback and len(seen) == 1


def test_script_counts_ignore_latin_medicine_names_and_units():
    from dawa_buddy.explainer import script_counts
    assert script_counts("ಒಂದು ಟ್ಯಾಬ್ಲೆಟ್ (650 mg) Telma", "kn")[1] == 0
    assert script_counts("खाने के बाद ಒಂದು", "kn")[1] > 0


# ---- Dose sentences come from templates, never from the model ----
def test_dose_sentence_is_built_from_the_prescription_in_three_languages():
    from dawa_buddy.explainer import dose_text
    from dawa_buddy.reader import read_offline
    m = read_offline("Tab Dolo 650 mg 1-0-1 x 5 days after food").medications[0]
    assert dose_text(m, "en") == "Twice a day: morning 1 tablet (650 mg), night 1 tablet (650 mg), after food, for 5 days."
    assert dose_text(m, "hi").startswith("दिन में 2 बार: सुबह 1 गोली (650 mg), रात 1 गोली (650 mg), खाने के बाद, 5 दिन तक लें")
    assert dose_text(m, "kn").startswith("ದಿನಕ್ಕೆ 2 ಬಾರಿ: ಬೆಳಿಗ್ಗೆ 1 ಮಾತ್ರೆ (650 mg), ರಾತ್ರಿ 1 ಮಾತ್ರೆ (650 mg), ಊಟದ ನಂತರ, 5 ದಿನಗಳವರೆಗೆ")
    sos = read_offline("Tab Cetzine 10 mg SOS").medications[0]
    assert dose_text(sos, "en") == "Take only when needed."
    unclear = read_offline("Tab Pantop 40").medications[0]
    assert "Ask your doctor or pharmacist" in dose_text(unclear, "en")           # no frequency written: never invent one


def test_a_wrong_dose_written_by_the_model_is_replaced_by_the_template(monkeypatch):
    """The default model once wrote '3 times a day' for 1-0-1 and added 'on an empty stomach' nobody had prescribed."""
    from dawa_buddy.explainer import explain
    from dawa_buddy.reader import read_offline
    wrong = {"explanations": [{"name": "Dolo", "purpose": "Relieves pain and fever.", "how_to_take": "Take 1 tablet 3 times a day on an empty stomach.",
                               "watch_for": "Stomach upset."}]}
    _fake_chat(monkeypatch, lambda s, u, m, n: wrong)
    out = explain(read_offline("Tab Dolo 650 mg 1-0-1 x 5 days after food"), "en")
    assert out[0].how_to_take == "Twice a day: morning 1 tablet (650 mg), night 1 tablet (650 mg), after food, for 5 days."
    assert "empty stomach" not in out[0].how_to_take and "3 times" not in out[0].how_to_take


# ---- missing information: one note, and 'to continue' is not a gap ----
def test_missing_information_is_one_note_for_the_whole_prescription():
    from dawa_buddy.reader import read_offline
    from dawa_buddy.safety import check
    rx = read_offline("Tab Dolo 650 mg 1-0-1\nTab Telma 40 mg 1-0-0\nTab Atorva 10 mg 0-0-1")
    gaps = [f for f in check(rx) if f.title == "Something is not written"]
    assert len(gaps) == 1 and set(gaps[0].meds) == {"Dolo", "Telma", "Atorva"}              # not three identical cards
    assert "Dolo, Telma, Atorva" in gaps[0].detail


def test_to_continue_is_not_reported_as_a_missing_number_of_days():
    from dawa_buddy.reader import read_offline
    from dawa_buddy.safety import check
    rx = read_offline("Tab Roseday Gold 75mg/75mg/10mg 0-0-1 after food to continue\nTab Dolo 650 mg 1-0-1")
    gaps = [f for f in check(rx) if f.title == "Something is not written"]
    assert len(gaps) == 1 and gaps[0].meds == ["Dolo"]                                       # only the line with no end and no 'continue'


def test_kannada_ai_text_is_off_by_default_but_the_dose_stays_in_kannada(monkeypatch):
    """A real run produced place names and 'Friday' as Kannada side effects: valid script, no meaning. So by default only English AI text is used."""
    from dawa_buddy.explainer import explain
    from dawa_buddy.reader import read_offline
    monkeypatch.delenv("DAWA_KN_MODEL_TEXT", raising=False)
    seen = _fake_chat(monkeypatch, lambda s, u, m, n: ENGLISH)
    out = explain(read_offline(RX), "kn")
    assert len(seen) == 1 and seen[0][1] is None                                   # one English call, no Kannada model call at all
    assert out[0].language_fallback is True and out[0].purpose == "Reduces fever."
    assert out[0].how_to_take.startswith("ದಿನಕ್ಕೆ 2 ಬಾರಿ")                          # the reviewed dose template is Kannada


def test_hindi_ai_text_is_on_by_default(monkeypatch):
    from dawa_buddy.explainer import model_text_langs
    monkeypatch.delenv("DAWA_KN_MODEL_TEXT", raising=False)
    assert model_text_langs() == {"hi"}
    monkeypatch.setenv("DAWA_KN_MODEL_TEXT", "1")
    assert model_text_langs() == {"hi", "kn"}


def test_vowel_signs_from_another_script_are_caught_inside_a_word():
    """'ತोಂಡ' mixes Devanagari vowel signs into a Kannada word; those are marks, not letters, and an earlier checker let them through."""
    from dawa_buddy.explainer import script_counts
    assert script_counts("ತोಂಡ", "kn")[1] > 0 and script_counts("ತೊಂಡ", "kn")[1] == 0


def test_a_missing_number_of_days_is_not_presented_as_keep_taking_it():
    from dawa_buddy.explainer import dose_text
    from dawa_buddy.reader import read_offline
    short = read_offline("Tab Dolo 650 mg 1-0-1 after food").medications[0]
    ongoing = read_offline("Tab Ecosprin 75 mg 0-0-1 to continue").medications[0]
    assert "number of days is not written" in dose_text(short, "en") and "Keep taking" not in dose_text(short, "en")
    assert "कितने दिन लेना है, यह नहीं लिखा है" in dose_text(short, "hi") and "ಎಷ್ಟು ದಿನ" in dose_text(short, "kn")
    assert "Keep taking it as your doctor says" in dose_text(ongoing, "en")


def test_common_food_abbreviations_are_read_as_timing():
    """Prescriptions write AF / A/F / a.f. and BF / B/F; losing them silently dropped 'after food' from the dose sentence."""
    from dawa_buddy.explainer import dose_text
    from dawa_buddy.reader import read_offline
    for tail, timing in [("AF", "after food"), ("A/F", "after food"), ("a.f.", "after food"), ("post prandial", "after food"), ("BF", "before food"), ("B/F", "before food")]:
        m = read_offline(f"Tab Shelcal-XT 0-1-0 {tail} x 30 days").medications[0]
        assert (m.frequency, m.timing, m.duration_days) == ("0-1-0", timing, 30), tail
    m = read_offline("Tab Shelcal-XT 0-1-0 AF x 30 days").medications[0]
    assert dose_text(m, "en") == "Once a day: afternoon 1 tablet, after food, for 30 days."
    assert "ಊಟದ ನಂತರ" in dose_text(m, "kn")
    assert read_offline("Tab Shelcal-XT 0-1-0 x 30 days").medications[0].timing is None          # nothing written, nothing invented


def test_the_real_prescription_lines_read_correctly():
    """From a real prescription: dose patterns printed with extra dashes, an SOS syrup that also has 0-0-1, a STAT injection, an injection with 1-1-1."""
    from dawa_buddy.explainer import dose_text
    from dawa_buddy.reader import read_offline
    from dawa_buddy.safety import check
    rx = read_offline("TAB SHELCAL-XT 0---1---0 TO CONTINUE\nSYP. CREMAFFIN PLUS, 15mL, PO, 0-0-1, AFTER FOOD SOS IN CASE OF CONSTIPATION.\n"
                      "INJ INFLUVAC TETRA 1 ML IM STAT\nINJ.ACYCLOVIR 500MG IV 1-1-1 AFTER FOOD X 7 DAYS")
    by = {m.name.split()[0].lower(): m for m in rx.medications}
    assert dose_text(by["shelcal-xt"], "en") == "Once a day: afternoon 1 tablet. Keep taking it as your doctor says."
    assert dose_text(by["cremaffin"], "en") == "Take only when needed."                                  # SOS wins over the printed 0-0-1
    assert dose_text(by["influvac"], "en") == "One single dose, given once." and dose_text(by["influvac"], "kn").startswith("ಒಂದೇ ಡೋಸ್")
    assert "1 dose (500 mg)" in dose_text(by["acyclovir"], "en") and "tablet" not in dose_text(by["acyclovir"], "en")   # an injection is a dose, not a tablet
    assert not [f for f in check(rx) if f.title == "Something is not written" and "Influvac" in f.detail]


def test_unclear_dose_lines_keeps_the_line_the_offline_reader_would_drop():
    from dawa_buddy.explainer import unclear_dose_lines
    assert unclear_dose_lines("TAB SHELCAL-XT 0---0 TO CONTINUE") == ["TAB SHELCAL-XT 0---0 TO CONTINUE"]     # read_offline drops this line entirely
    assert unclear_dose_lines("INJ INFLUVAC 1 ML IM STAT\nTab Dolo 650 SOS\nFBS, PPBS, RFT, CBC AFTER 3 MONTH - REVIEW WITH REPORTS .\nRx") == []
    assert unclear_dose_lines("Tab Telma 40 1-0-0 x 30 days\nSYP. COUGH SYRUP 5ML") == ["SYP. COUGH SYRUP 5ML"]


import pytest as _pytest


@_pytest.mark.parametrize("name,line,want", [
    ("Concor", "TAB.CONCOR T 5MG/40 PO, 1-0-0, AS DIRECTED@9AM X TO CONTINUE", "Concor T"),
    ("Roseday", "TAB.ROSEDAY GOLD, 75MG/75MG/10MG, PO, 0-0-1, AFTER FOOD@10PM", "Roseday Gold"),
    ("Cremaffin", "SYP. CREMAFFIN PLUS, 15mL, PO, 0-0-1", "Cremaffin Plus"),
    ("Pan", "Tab Pan D 40 1-0-0 x 30 days", "Pan D"),                          # Pan D is not Pan
    ("Influvac", "INJ INFLUVAC TETRA 1 ML IM STAT", "Influvac Tetra"),
    ("Telma", "Tab Telma 40 1-0-0 x 30 days", "Telma"),                       # a number ends the name
    ("Dolo", "Tab Dolo SOS", "Dolo"),                                          # a frequency word is not part of the name
    ("Amlong", "Tab Amlong after food 1-0-0", "Amlong"),
    ("Combiflam", "Tab Combiflam one tab at night", "Combiflam"),
    ("Shelcal-Xt", "TAB SHELCAL-XT 0---1---0 TO CONTINUE", "Shelcal-Xt"),
    ("Zzz", "Tab Dolo 650", "Zzz"),                                            # not in the line: unchanged
])
def test_a_truncated_brand_name_is_completed_from_the_printed_line(name, line, want):
    from dawa_buddy.reader import complete_name
    assert complete_name(name, line) == want


def test_a_model_that_truncates_the_name_cannot_cause_a_false_variant_warning():
    """The model returned 'Concor' for 'CONCOR T 5MG/40' in 1 of 3 live runs; that passed the grounding check and made a red wrong-variant card."""
    from dawa_buddy.reader import _clean_model_meds, read_offline
    line = "TAB.CONCOR T 5MG/40 PO, 1-0-0, AS DIRECTED@9AM X TO CONTINUE"
    got = _clean_model_meds({"medications": [{"name": "Concor", "frequency": "1-0-0"}]}, line)
    assert [m.name for m in got] == ["Concor T"]
    assert [m.name for m in read_offline(line).medications] == ["Concor T"]       # the rules-only reader, too


def test_the_real_prescription_names_are_complete_in_the_rules_only_reader():
    from dawa_buddy.reader import read_offline
    rx = read_offline("TAB.ROSEDAY GOLD, 75MG/75MG/10MG, PO, 0-0-1, AFTER FOOD@10PM X TO CONTINUE\nTAB.GLYCOMET-500 SR, 500MG, PO, 1-0-0, AFTER FOOD X TO CONTINUE\n"
                      "TAB.CONCOR T 5MG/40 PO, 1-0-0, AS DIRECTED@9AM X TO CONTINUE\nSYP. CREMAFFIN PLUS, 15mL, PO, 0-0-1, AFTER FOOD SOS IN CASE OF CONSTIPATION.")
    assert [m.name for m in rx.medications] == ["Roseday Gold", "Glycomet", "Concor T", "Cremaffin Plus"]
