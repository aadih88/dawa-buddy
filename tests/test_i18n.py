"""Hindi and Kannada text that is NOT model-written: complete, in the right script, correctly filled, and falling back to English only on purpose."""
import pytest

from dawa_buddy import i18n, knowledge
from dawa_buddy.explainer import PHRASES, script_counts
from dawa_buddy.reader import read_offline
from dawa_buddy.safety import check
from dawa_buddy.schemas import SafetyFlag


def all_tables():
    """Every {en, hi, kn} dict in the module, with a name for the failure message."""
    out = []
    for name in ("SEVERITY", "TITLES", "DETAILS", "NOT_WRITTEN", "STATUS", "LABELS"):
        for key, d in getattr(i18n, name).items():
            out.append((f"{name}.{key}", d))
    out += [("DISCLAIMER", i18n.DISCLAIMER), ("AI_NOTE", i18n.AI_NOTE), ("FIXED_NOTE", i18n.FIXED_NOTE), ("PARTIAL_NOTE.k", {"hi": i18n.PARTIAL_NOTE["hi"], "kn": i18n.PARTIAL_NOTE["kn"], "en": "x"}), ("FALLBACK_NOTE.hi", {"hi": i18n.FALLBACK_NOTE["hi"], "kn": i18n.FALLBACK_NOTE["kn"], "en": "x"})]
    for key, d in i18n.TIMETABLE.items():
        if key == "slots":
            out += [(f"slots.{k}", v) for k, v in d.items()]
        elif key == "headers":
            out += [(f"headers.{l}", {l: " ".join(v)}) for l, v in d.items()]
        else:
            out.append((f"TIMETABLE.{key}", d))
    return out


def test_every_phrase_exists_in_every_language():
    for name, d in all_tables():
        if name.startswith("headers."):
            continue
        assert set(d) == {"en", "hi", "kn"}, name
    assert set(i18n.TIMETABLE["headers"]) == {"en", "hi", "kn"} and all(len(v) == 3 for v in i18n.TIMETABLE["headers"].values())


def test_every_interaction_rule_has_a_translated_sentence_and_title():
    """Adding a rule to data/interactions.json without translations must fail here, not reach a family in English."""
    for rule in knowledge.INTERACTIONS:
        assert rule["code"] in i18n.DETAILS, rule
        assert i18n.TITLE_OF.get(rule["code"], rule["code"]) in i18n.TITLES, rule


@pytest.mark.parametrize("lang", ["hi", "kn"])
def test_no_phrase_contains_letters_from_another_script(lang):
    bad = []
    for name, d in all_tables():
        if lang not in d:                       # the per-language header rows
            continue
        target, other = script_counts(d[lang], lang)
        if other or (target == 0 and d[lang].strip()):
            bad.append((name, target, other))
    assert not bad, bad


def test_dose_phrases_also_stay_in_one_script():
    for lang in ("hi", "kn"):
        for key, v in PHRASES[lang].items():
            vals = list(v.values()) if isinstance(v, dict) else [v]
            assert all(script_counts(x, lang)[1] == 0 for x in vals if isinstance(x, str)), (lang, key)


def test_placeholders_always_fill():
    for code, d in i18n.DETAILS.items():
        for lang in ("en", "hi", "kn"):
            f = SafetyFlag(severity="info", title="t", detail="d", code=code, args={"drug": "ibuprofen", "ingredients": "paracetamol", "mg": 4400, "month": "2026-01", "status": "spurious"})
            title, detail = i18n.flag_text(f, lang)
            assert "{" not in detail and "}" not in detail and title and detail, (code, lang)


def test_real_flags_are_translated_from_the_rules_own_values():
    rx = read_offline("Tab Warfarin 5 mg 0-0-1 x 30 days\nTab Ecosprin 75 mg 0-0-1 x 30 days\nTab Dolo 650 mg 1-1-1 x 5 days\nTab Calpol 650 mg 1-1-1 x 5 days\nTab Crocin 650 mg 1-1-1 x 5 days\nTab Zed 1-0-1")
    flags = {f.code: f for f in check(rx)}
    assert {"warfarin_aspirin", "double_ingredient", "paracetamol_max", "not_written"} <= set(flags)
    hi = i18n.localize_flags(check(rx), "hi")
    by = {f.code: f for f in hi}
    assert by["warfarin_aspirin"].title == "खून बहने का ख़तरा" and by["warfarin_aspirin"].detail.startswith("वारफ़रिन के साथ एस्पिरिन")
    assert "paracetamol" in by["double_ingredient"].detail and "5850 mg" in by["paracetamol_max"].detail            # numbers and names come from the rule
    assert "Zed" in by["not_written"].detail and "यह इनके लिए नहीं लिखा है" in by["not_written"].detail
    kn = {f.code: f for f in i18n.localize_flags(check(rx), "kn")}
    assert kn["warfarin_aspirin"].title == "ರಕ್ತಸ್ರಾವದ ಅಪಾಯ" and "5850 mg" in kn["paracetamol_max"].detail


def test_english_is_the_rules_own_text_unchanged():
    rx = read_offline("Tab Warfarin 5 mg 0-0-1 x 30 days\nTab Ecosprin 75 mg 0-0-1 x 30 days")
    flags = check(rx)
    assert [(f.title, f.detail) for f in i18n.localize_flags(flags, "en")] == [(f.title, f.detail) for f in flags]


def test_a_rule_without_a_translation_shows_english_not_a_guess():
    f = SafetyFlag(severity="info", title="Future rule", detail="Some new English sentence.", code="future_rule")
    assert i18n.flag_text(f, "hi") == ("Future rule", "Some new English sentence.")
    assert i18n.flag_text(SafetyFlag(severity="info", title="T", detail="D"), "kn") == ("T", "D")             # no code at all


def test_batch_alert_status_is_translated():
    f = SafetyFlag(severity="call_doctor", title="x", detail="y", code="batch_alert", args={"month": "2026-01", "status": "not_of_standard_quality"})
    assert "मानक गुणवत्ता का नहीं" in i18n.flag_text(f, "hi")[1] and "ನಿಗದಿತ ಗುಣಮಟ್ಟದ್ದಲ್ಲ" in i18n.flag_text(f, "kn")[1]


def test_timetable_is_translated_and_english_is_unchanged():
    from dawa_buddy.scheduler import build_schedule, share_text
    rx = read_offline("Tab Dolo 650 mg 1-0-1 x 5 days after food\nTab Cetzine 10 mg SOS\nTab Pantop 40 mg 1-0-0 x 30 days before food")
    en = build_schedule(rx)
    assert {i.instruction for i in en} == {"1 tablet (650 mg), after food", "1 tablet (40 mg), before food", "1 tablet (10 mg); only when needed, follow the doctor's limit"}
    hi = build_schedule(rx, "hi")
    assert any(i.instruction == "1 गोली (650 mg), खाने के बाद" for i in hi) and any("खाने से पहले" in i.instruction for i in hi)
    rows = i18n.schedule_rows(hi, "hi")
    morning = next(r for r in rows if r["दवा"] == "Pantop")
    assert list(morning) == ["समय", "दवा", "कैसे लें"] and morning["समय"] == "08:00 सुबह" and morning["कैसे लें"] == "1 गोली (40 mg), खाने से पहले"
    assert "सिर्फ़ ज़रूरत पड़ने पर" in [i for i in hi if i.slot == "as_needed"][0].instruction
    text = share_text(hi, 5, "hi")
    assert text.splitlines()[0] == "दवाओं की समय-सारणी" and "अवधि: 5 दिन" in text and text.splitlines()[-1].startswith("यह चिकित्सा सलाह नहीं है")
    kn = share_text(build_schedule(rx, "kn"), None, "kn")
    assert kn.splitlines()[0] == "ಔಷಧಿಗಳ ವೇಳಾಪಟ್ಟಿ" and "ಅವಧಿ" not in kn
    assert share_text(en, 5).splitlines()[0] == "Medicine timetable" and "Duration: 5 days" in share_text(en, 5)


def test_bedtime_is_not_dropped_from_the_dose_sentence_or_the_timetable():
    from dawa_buddy.explainer import dose_text
    m = read_offline("Tab Zolfresh 10 mg 0-0-1 at bedtime x 7 days").medications[0]
    assert m.timing == "bedtime"
    assert "at bedtime" in dose_text(m, "en") and "सोने से पहले" in dose_text(m, "hi") and "ಮಲಗುವ ಮೊದಲು" in dose_text(m, "kn")
    assert i18n.instruction("1 गोली (10 mg)", "bedtime", "hi") == "1 गोली (10 mg), सोने से पहले"


# ---------------------------------------------------------------- the timetable says what to TAKE, and keeps one-off doses out of the daily routine
def _med(line):
    return read_offline(line).medications[0]


@__import__("pytest").mark.parametrize("line,en", [
    ("Tab Glycomet 500 mg 1-0-0 x 30 days after food", "1 tablet (500 mg)"),
    ("TAB.ROSEDAY GOLD, 75MG/75MG/10MG, PO, 0-0-1, AFTER FOOD X TO CONTINUE", "1 tablet (75 mg)"),
    ("SYP. CREMAFFIN PLUS, 15mL, PO, 0-0-1 x 5 days", "15 ml"),                       # a syrup: the volume is the amount
    ("INJ.ACYCLOVIR 500MG IV 1-1-1 AFTER FOOD X 7 DAYS", "1 dose (500 mg)"),         # an injection is a dose, not a tablet
    ("TAB SHELCAL-XT 0-1-0 TO CONTINUE", "1 tablet"),                                  # no strength written: still says how much to take
])
def test_the_amount_is_what_to_take_not_what_is_in_it(line, en):
    from dawa_buddy.explainer import amount_text
    assert amount_text(_med(line), "en") == en


def test_strengths_are_tidied_and_a_bare_number_takes_the_unit_before_it():
    from dawa_buddy.explainer import pretty_strength
    assert pretty_strength("500MG") == "500 mg" and pretty_strength("75MG/75MG/10MG") == "75 mg / 75 mg / 10 mg"
    assert pretty_strength("5MG/40") == "5 mg / 40 mg" and pretty_strength("0.4mg") == "0.4 mg" and pretty_strength(None) == ""
    assert pretty_strength("T 5MG/40") == "5 mg / 40 mg" and pretty_strength("Forte") == ""       # stray words from a model are dropped


def test_the_timetable_rows_name_an_amount_in_every_language():
    from dawa_buddy.scheduler import build_schedule
    rx = read_offline("Tab Glycomet 500 mg 1-0-0 x 30 days after food")
    assert build_schedule(rx)[0].instruction == "1 tablet (500 mg), after food"
    assert build_schedule(rx, "hi")[0].instruction == "1 गोली (500 mg), खाने के बाद"
    assert build_schedule(rx, "kn")[0].instruction == "1 ಮಾತ್ರೆ (500 mg), ಊಟದ ನಂತರ"


def test_a_single_dose_is_not_in_the_daily_table_and_the_as_needed_rows_come_last():
    from dawa_buddy.scheduler import build_schedule, share_text
    rx = read_offline("Tab Glycomet 500 mg 1-0-0 x 30 days after food\nTab Dolo 650 SOS\nINJ INFLUVAC TETRA 1 ML IM STAT\nTab Telma 40 0-0-1 x 30 days")
    items = build_schedule(rx)
    assert [i.slot for i in items] == ["morning", "night", "as_needed", "once"]                 # daily first, then as-needed, then the one-off
    once = [i for i in items if i.slot == "once"][0]
    assert once.med == "Influvac" or "Influvac" in once.med
    assert once.instruction == "1 ml. One single dose, given once."
    text = share_text(items, None, "en")
    assert "One-time dose (not part of the daily routine):" in text and "Influvac" in text.split("One-time dose")[1] and "Influvac" not in text.split("One-time dose")[0]
    assert "सिर्फ़ एक बार की खुराक" in share_text(build_schedule(rx, "hi"), None, "hi")


def test_an_sos_word_in_the_line_beats_the_digits_a_model_returns():
    """The model reads 'SYP CREMAFFIN 0-0-1 ... SOS in case of constipation' as 0-0-1 and loses the SOS; the nightly row was wrong."""
    from dawa_buddy.reader import _clean_model_meds
    line = "SYP. CREMAFFIN PLUS, 15mL, PO, 0-0-1, AFTER FOOD SOS IN CASE OF CONSTIPATION."
    got = _clean_model_meds({"medications": [{"name": "Cremaffin Plus", "frequency": "0-0-1", "strength": "15 ml", "form": "syrup"}]}, line)
    assert got[0].frequency == "SOS"
    stat = _clean_model_meds({"medications": [{"name": "Influvac Tetra", "frequency": "SOS", "strength": "1 ml"}]}, "INJ INFLUVAC TETRA 1 ML IM STAT")
    assert stat[0].frequency == "STAT"                                                          # and a model that says SOS for a STAT line is corrected too
    two = _clean_model_meds({"medications": [{"name": "Dolo", "frequency": "1-0-1"}, {"name": "Cetzine", "frequency": "SOS"}]}, "Tab Dolo 650 1-0-1, Tab Cetzine SOS")
    assert [m.frequency for m in two] == ["1-0-1", "SOS"]                                       # a line with two medicines is left to the model
