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


# ---------------------------------------------------------------- real prescription: why a medicine came back in English
def _line(text):
    from dawa_buddy.reader import read_offline
    return read_offline(text).medications[0]


def test_roseday_gold_is_a_verified_three_ingredient_brand_and_gets_the_fixed_kannada_text():
    from dawa_buddy import brand_table
    hit = brand_table.lookup("Roseday Gold", "capsule")
    assert hit.salts == "aspirin+clopidogrel+rosuvastatin" and [v for v, _ in hit.strengths] == [75.0, 75.0, 10.0]
    m = _line("TAB.ROSEDAY GOLD, 75MG/75MG/10MG, PO, 0-0-1, AFTER FOOD@10PM X TO CONTINUE")            # the prescription says TAB; the product is a capsule
    assert medinfo._parts_for(m) == ["aspirin", "clopidogrel", "rosuvastatin"]
    purpose, watch = medinfo.info(m, "kn")
    assert script_counts(purpose + watch, "kn")[1] == 0
    en = medinfo.info(m, "en")[1]
    assert "Black stools, vomiting blood or unusual bleeding" in en and "Muscle pain or weakness" in en   # the warnings of ALL three ingredients, not two


def test_a_brand_table_that_dropped_an_ingredient_never_describes_part_of_a_product(monkeypatch):
    """The brand table keeps at most two actives. A line that prints three strengths means one is missing: say nothing rather than describe two."""
    import types
    from dawa_buddy import brand_table
    monkeypatch.setattr(brand_table, "lookup", lambda name, form="tablet": types.SimpleNamespace(salts="aspirin+rosuvastatin", strengths=[(75.0, "mg"), (10.0, "mg")]))
    assert medinfo._parts_for(types.SimpleNamespace(name="Zzz", generic=None, strength="75 mg", raw="TAB ZZZ 75MG/75MG/10MG 0-0-1")) == []
    assert medinfo._parts_for(types.SimpleNamespace(name="Zzz", generic=None, strength="75 mg", raw="TAB ZZZ 75MG/10MG 0-0-1")) == ["aspirin", "rosuvastatin"]


def test_printed_strengths_are_counted_per_product():
    assert medinfo.printed_actives("TAB.ROSEDAY GOLD, 75MG/75MG/10MG, PO") == 3
    assert medinfo.printed_actives("TAB.CONCOR T 5MG/40 PO, 1-0-0") == 2
    assert medinfo.printed_actives("Tab Telma 40 1-0-0 x 30 days") == 0 and medinfo.printed_actives("TAB VELTAM 0.4MG") == 0


def test_a_brand_the_table_keys_with_its_strength_is_found_by_name_and_strength():
    m = _line("TAB.VELTAM 0.4, 0.4MG, PO, 0-0-1, AFTER FOOD@10PM X TO CONTINUE")
    assert medinfo._parts_for(m) == ["tamsulosin"] and medinfo.info(m, "kn") is not None


def test_bisoprolol_has_fixed_text():
    p, w = medinfo.info(Medication(name="Concor", generic="bisoprolol"), "en")
    assert "blood pressure" in p and "Do not stop it suddenly" in w


# ---------------------------------------------------------------- what the 28 Oct 2026 second-opinion review taught us
def test_no_kannada_purpose_piece_ends_in_the_verb_the_frame_already_supplies():
    """The frame is 'This medicine is used {p}.' (...ಬಳಸಲಾಗುತ್ತದೆ). A piece that itself ends in 'ಬಳಸಲು' ('to use') made 'used to use'."""
    bad = [k for k, (en, kn) in medinfo._P.items() if kn.rstrip().endswith("ಬಳಸಲು") or kn.rstrip().endswith("ಬಳಸಲಾಗುತ್ತದೆ")]
    assert not bad, bad


def test_the_review_additions_only_reuse_warnings_that_already_exist_and_are_translated():
    assert medinfo.REVIEW_ADDITIONS and all(w in medinfo.WARN and w in medinfo.ORDER for ws in medinfo.REVIEW_ADDITIONS.values() for w in ws)
    for name, (pk, se, wn) in medinfo.MEDS.items():
        assert len(wn) == len(set(wn)), name                                               # no warning twice
        assert not ("pregnancy" in wn and "no_pregnancy" in wn), name                      # the stronger sentence replaces the softer, never both


def test_pregnancy_wording_follows_the_clinical_judgement_applied_on_top_of_the_review():
    never = {"telmisartan", "losartan", "olmesartan", "ramipril", "enalapril", "warfarin", "methotrexate", "valproate", "divalproex", "isotretinoin", "thiocolchicoside"}
    assert all("no_pregnancy" in medinfo.MEDS[n][2] for n in never)
    soft_only = {"atorvastatin", "rosuvastatin", "letrozole", "clomiphene"}                 # not 'never': guidance relaxed, or taken by women trying to conceive
    assert all("pregnancy" in medinfo.MEDS[n][2] and "no_pregnancy" not in medinfo.MEDS[n][2] for n in soft_only)
    assert all("pregnancy" in medinfo.MEDS[n][2] for n in ("diclofenac", "ibuprofen", "doxycycline", "albendazole", "fluconazole", "clonazepam"))


def test_the_reviewed_corrections_are_in_the_fixed_text():
    from dawa_buddy import i18n
    assert i18n.SEVERITY["call_doctor"]["hi"] == "अपने डॉक्टर से संपर्क करें"                     # not 'phone your doctor'
    assert "ನಂತಹ" in i18n.DETAILS["warfarin_nsaid"]["kn"] and "ಹಾಗೆ" not in i18n.DETAILS["warfarin_nsaid"]["kn"]   # 'like {drug}', not 'as {drug} does'
    assert i18n.TIMETABLE["headers"]["kn"][2] == "ತೆಗೆದುಕೊಳ್ಳುವ ರೀತಿ"
    from dawa_buddy.explainer import PHRASES
    assert "दी जाती" not in PHRASES["hi"]["stat"] and "ನೀಡಲಾಗುತ್ತದೆ" not in PHRASES["kn"]["stat"]   # neutral: right for a vaccine a nurse gives and for a pill


def test_a_composed_combination_stays_readable_with_the_extra_warnings():
    from dawa_buddy.schemas import Medication
    en = medinfo.info(Medication(name="Roseday Gold", generic="aspirin+clopidogrel+rosuvastatin"), "en")[1]
    assert en.count("Black stools") == 1 and "pregnan" in en                                 # merged without repeats
    assert len(en.split(". ")) <= 12                                                         # a long list is still a list a person can read


def test_torasemide_never_says_drink_plenty_of_water():
    # a water tablet for heart or kidney failure: fluid is often limited, so "drink plenty of water" is unsafe advice (second-opinion review)
    assert "water" not in medinfo.MEDS["torasemide"][2]
    assert "drink plenty" not in medinfo.info(type("M", (), {"generic": "torasemide", "name": "Torasemide", "form": "tablet", "strength": None, "raw": ""})(), "en")[1].lower()


def test_second_opinion_additions_reuse_existing_warnings():
    for name, extra in medinfo.SECOND_OPINION_ADDITIONS.items():
        assert all(w in medinfo.WARN and w in medinfo.ORDER for w in extra), name       # no new, untranslated sentence slipped in
        assert all(w in medinfo.MEDS[name][2] for w in extra), name
