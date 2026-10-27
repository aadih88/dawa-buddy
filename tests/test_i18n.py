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
    assert "मानक गुणवत्ता का नहीं" in i18n.flag_text(f, "hi")[1] and "ಗುಣಮಟ್ಟದ ಮಾನದಂಡಕ್ಕೆ" in i18n.flag_text(f, "kn")[1]


def test_timetable_is_translated_and_english_is_unchanged():
    from dawa_buddy.scheduler import build_schedule, share_text
    rx = read_offline("Tab Dolo 650 mg 1-0-1 x 5 days after food\nTab Cetzine 10 mg SOS\nTab Pantop 40 mg 1-0-0 x 30 days before food")
    en = build_schedule(rx)
    assert {i.instruction for i in en} == {"650 mg after food", "40 mg before food", "10 mg; only when needed, follow the doctor's limit"}
    hi = build_schedule(rx, "hi")
    assert any(i.instruction == "650 mg खाने के बाद" for i in hi) and any("खाने से पहले" in i.instruction for i in hi)
    rows = i18n.schedule_rows(hi, "hi")
    morning = next(r for r in rows if r["दवा"] == "Pantop")
    assert list(morning) == ["समय", "दवा", "कैसे लें"] and morning["समय"] == "08:00 सुबह" and morning["कैसे लें"] == "40 mg खाने से पहले"
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
    assert i18n.instruction("10 mg", "bedtime", "hi") == "10 mg सोने से पहले"
