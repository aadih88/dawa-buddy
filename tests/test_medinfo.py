"""The fixed Kannada/English 'what is it for / watch for' table: complete, in one script, composed correctly, and wired into the explainer."""
import pytest

from dawa_buddy import explainer, i18n, medinfo
from dawa_buddy.explainer import script_counts
from dawa_buddy.schemas import Medication, MedExplanation, Prescription


def med(name, generic=None, freq="1-0-1", days=5):
    return Medication(name=name, generic=generic, frequency=freq, duration_days=days, raw=name)


def test_every_entry_uses_only_known_phrases():
    for key, (purpose, sides, warns) in medinfo.MEDS.items():
        assert purpose in medinfo._P, key
        assert all(s in medinfo.SIDE for s in sides), key
        assert all(w in medinfo.WARN and w in medinfo.ORDER for w in warns), key
    assert set(medinfo.WARN) <= set(medinfo.ORDER)
    assert all(v in medinfo.MEDS for v in medinfo.ALIASES.values() if "+" not in v)


@pytest.mark.parametrize("table", ["SIDE", "WARN", "_P"])
def test_kannada_phrases_are_pure_kannada_and_not_empty(table):
    bad = []
    for key, (en, kn) in getattr(medinfo, table).items():
        target, other = script_counts(kn, "kn")
        if other or target == 0 or not en.strip():
            bad.append((key, target, other))
    assert not bad, bad


def test_templates_and_joiners_are_kannada():
    for d in (medinfo.PURPOSE, medinfo.SIDE_SENTENCE, medinfo.PURPOSE_JOIN):
        assert script_counts(d["kn"].replace("{p}", "").replace("{x}", ""), "kn")[1] == 0


def test_composed_text_has_no_stray_braces_and_is_kannada():
    for key in medinfo.MEDS:
        for lang in ("en", "kn"):
            p, w = medinfo.info(med("x", key), lang)
            assert "{" not in p + w and p.strip() and w.strip(), (key, lang)
        p, w = medinfo.info(med("x", key), "kn")
        assert script_counts(p + w, "kn")[1] == 0, key


def test_a_combination_merges_without_repeating_a_warning():
    p, w = medinfo.info(med("Combiflam", "ibuprofen+paracetamol"), "en")
    assert p == "This medicine is used to ease pain, swelling and fever."
    assert w.count("Black stools") == 1 and "paracetamol" in w
    p2, w2 = medinfo.info(med("Augmentin", "amoxicillin:500mg;clavulanic acid:125mg"), "en")
    assert "help the antibiotic work better" in p2 and w2.count("rash") == 1


def test_an_unknown_ingredient_is_not_guessed():
    assert medinfo.info(med("Mystery", "unknownium"), "kn") is None
    assert medinfo.info(med("Mystery", "paracetamol+unknownium"), "kn") is None      # one unknown part: say nothing rather than half


def test_brand_names_resolve_through_the_brand_table():
    assert medinfo.info(med("Telma 40"), "en")[0] == "This medicine is used to lower blood pressure."
    assert medinfo.info(med("Pantop 40"), "kn") is not None


def test_no_warning_tells_the_reader_to_stop_a_medicine():
    for en, _ in medinfo.WARN.values():
        assert "stop taking" not in en.lower()


def test_kannada_explainer_uses_the_table_and_marks_the_rest_as_english(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    rx = Prescription(medications=[med("Telma 40", "telmisartan"), med("Shelcal 500", None)])
    items = explainer.explain(rx, "kn")
    assert items[0].fixed and not items[0].language_fallback and items[0].purpose == medinfo.info(rx.medications[0], "kn")[0]
    assert not items[1].fixed and items[1].language_fallback
    assert i18n.explainer_note("kn", items) == i18n.PARTIAL_NOTE["kn"]


def test_note_choice():
    f = MedExplanation(name="a", purpose="p", watch_for="w", fixed=True)
    e = MedExplanation(name="b", purpose="p", watch_for="w", language_fallback=True)
    ai = MedExplanation(name="c", purpose="p", watch_for="w")
    assert i18n.explainer_note("kn", [f, f]) == i18n.FIXED_NOTE["kn"]
    assert i18n.explainer_note("kn", [f, e]) == i18n.PARTIAL_NOTE["kn"]
    assert i18n.explainer_note("kn", [e]) == i18n.FALLBACK_NOTE["kn"]
    assert i18n.explainer_note("hi", [ai]) == i18n.AI_NOTE["hi"]
    assert i18n.explainer_note("en", [ai]) == i18n.AI_NOTE["en"]


def test_hindi_and_english_are_untouched_by_the_table(monkeypatch):
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    rx = Prescription(medications=[med("Telma 40", "telmisartan")])
    assert not explainer.explain(rx, "hi")[0].fixed and not explainer.explain(rx, "en")[0].fixed


def test_the_table_wins_over_ai_kannada_when_the_opt_in_is_on(monkeypatch):
    """Even with AI Kannada switched on, an ingredient in the reviewed table is never shown from the model."""
    monkeypatch.setenv("DAWA_PROVIDER", "offline")
    monkeypatch.setenv("DAWA_KN_MODEL_TEXT", "1")
    rx = Prescription(medications=[med("Dolo 650", "paracetamol")])
    out = explainer.with_doses([MedExplanation(name="Dolo", purpose="ಯಾವುದೋ ಪಠ್ಯ", watch_for="ಯಾವುದೋ ಪಠ್ಯ")], rx, "kn")
    assert out[0].fixed and out[0].purpose == medinfo.info(rx.medications[0], "kn")[0]
