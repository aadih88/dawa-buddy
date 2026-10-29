from dawa_buddy import bill as b


def one(line):
    return b.audit(line)[0]


def test_above_ceiling_only_beyond_gst_allowance():
    assert one("AMLONG 5 TAB | 10 | 9.00 | 90.00 | tab").tier == b.TIER_ABOVE_CEILING
    assert one("AMLONG 5 TAB | 10 | 2.80 | 28.00 | tab").tier != b.TIER_ABOVE_CEILING  # 2.56 ceiling + 12% = 2.87


def test_at_ceiling_but_far_above_generic_is_a_question_not_a_violation():
    f = one("ATORVA 10 TAB | 30 | 4.90 | 147.00 | tab")
    assert f.tier == b.TIER_GENERIC_GAP and f.possible_saving > 100


def test_never_guesses_the_billed_unit():
    assert one("PANTOP 40 | 10 | 120.00 | 1200.00").tier == b.TIER_UNIT_UNCLEAR


def test_qty_rate_amount_mismatch_is_flagged():
    assert one("TELMA 40 TAB | 10 | 8.00 | 90.00 | tab").tier == b.TIER_UNIT_UNCLEAR


def test_doctor_only_drugs_never_get_a_swap_nudge():
    # phenytoin 100 mg: NPPA ceiling 1.80 (x1.12 = 2.02), Jan Aushadhi 0.57: 1.90 is under the ceiling but >3x the generic
    f = one("PHENYTOIN 100 TAB | 30 | 1.90 | 57.00 | tab")
    assert f.tier == b.TIER_DOCTOR_ONLY and f.possible_saving == 0
    assert one("WARFARIN 5 TAB | 30 | 6.00 | 180.00 | tab").tier == b.TIER_ABOVE_CEILING   # a legal ceiling applies to every drug


def test_consumables_are_labelled_not_covered_not_judged():
    assert one("IV SET DISPOSABLE | 4 | 85.00 | 340.00").tier == b.TIER_NOT_MEDICINE


def test_summary_separates_violation_from_generic_savings():
    s = b.summary(b.audit("AMLONG 5 TAB | 10 | 9.00 | 90.00 | tab\nATORVA 10 TAB | 30 | 4.90 | 147.00 | tab"))
    assert s["possible_saving_above_ceiling"] > 0 and s["possible_saving_generic"] > 0


def test_unit_must_be_explicit_so_a_strip_price_is_never_read_as_per_tablet():
    # TELMA 40: Rs 124 per strip of 10 = 12.40/tab. Read as per-tablet it would falsely look 18x the ceiling.
    assert one("TELMA 40 TAB | 3 | 124.00 | 372.00").tier == b.TIER_UNIT_UNCLEAR            # no unit given
    f = one("TELMA 40 TAB | 3 | 124.00 | 372.00 | strip | 10")
    assert abs(f.unit_price - 12.4) < 1e-6 and f.tier == b.TIER_ABOVE_CEILING
    assert one("TELMA 40 TAB | 3 | 124.00 | 372.00 | strip").tier == b.TIER_UNIT_UNCLEAR   # strip without pack size


def test_unreadable_lines_are_reported_not_silently_dropped():
    lines, rejects = b.parse_bill_ex("# comment\nItem | Qty | Rate | Amount\nTELMA 40 | 3 | 124.00 | 372.00 | strip | 10\nTotal payable 4500")
    assert len(lines) == 1 and rejects == ["Total payable 4500"]


def test_reconcile_flags_extra_units_unprescribed_and_missing():
    from dawa_buddy.reader import read_offline
    from dawa_buddy.reconcile import reconcile
    rx = read_offline("Tab Telma 40 1-0-0 x 30 days\nTab Atorva 10 1-0-1 x 30 days")
    lines, _ = b.parse_bill_ex("TELMA 40 | 9 | 124 | 1116 | strip | 10\nPANTOP 40 | 1 | 120 | 120 | strip | 10")
    kinds = {(f.kind, f.subject) for f in reconcile(rx, lines, 1000)}
    assert ("billed_more", "Telma") in kinds and ("not_prescribed", "PANTOP 40") in kinds
    assert ("not_billed", "Atorva") in kinds and any(k == "total_mismatch" for k, _ in kinds)


def test_question_list_is_built_from_findings_only():
    from dawa_buddy.report import questions
    fs = b.audit("TELMA 40 | 3 | 124.00 | 372.00 | strip | 10\nPHENYTOIN 100 TAB | 30 | 1.90 | 57.00 | tab\nIV SET DISPOSABLE | 1 | 85 | 85")
    q = questions(fs)
    assert "Ask the pharmacy" in q and "12.40" in q and "6.92" in q and "Do not switch" in q


def test_supplements_are_labelled_no_ceiling_not_unbenchmarked():
    f = one("ZINCOVIT MULTIVITAMIN TAB | 10 | 12.00 | 120.00 | tab")
    assert f.tier == b.TIER_SUPPLEMENT and "not price-controlled" in f.note and f.possible_saving == 0
    assert one("WHEY PROTEIN 1KG | 1 | 2500 | 2500").tier == b.TIER_SUPPLEMENT   # no unit needed: no price judgement made


def test_mrp_check_applies_to_every_product_including_supplements():
    assert one("ZINCOVIT TAB | 1 | 120 | 120 | strip | 15 | 100").tier == b.TIER_ABOVE_MRP
    f = one("ZINCOVIT TAB | 1 | 100 | 100 | strip | 15 | 100")
    assert f.tier == b.TIER_SUPPLEMENT and "within the MRP on your bill" in f.note
    f = one("AMLONG 5 TAB | 10 | 9.00 | 90.00 | tab | 10 | 80.00")        # MRP printed per strip of 10 = 8.00 per tab
    assert f.tier == b.TIER_ABOVE_MRP and f.possible_saving == 10.0
    assert b.summary([f])["possible_saving_above_mrp"] == 10.0


def test_brand_table_resolves_real_brands_with_strengths_from_the_table():
    from dawa_buddy.brand_table import lookup
    h = lookup("TELMA-H 40/12.5 TAB")
    assert h.salts == "telmisartan+hydrochlorothiazide" and h.strengths == [(40.0, "mg"), (12.5, "mg")]
    assert lookup("LASIX TAB").salts == "furosemide"
    assert lookup("PANTOP-D SR CAP", "capsule").modified_release


def test_brand_table_never_drops_a_letter_token_or_guesses():
    from dawa_buddy.brand_table import lookup
    assert lookup("ZYXOLEX 40 TAB") is None
    # 'pan d' is a different product from 'pan'; an unlisted 'pan d' must not fall back to plain Pan
    assert lookup("PAN XQ 40 TAB") is None


def test_brand_table_hit_is_priced_and_labelled_as_unverified():
    f = one("TELMA 40 TAB | 3 | 124.00 | 372.00 | strip | 10")
    assert f.tier == b.TIER_ABOVE_CEILING and "brand table" in f.note


def test_three_active_brands_use_the_hand_checked_override_not_the_two_active_table_row():
    from dawa_buddy.brand_table import lookup
    h = lookup("ZERODOL-SP TAB")
    assert h.salts == "aceclofenac+paracetamol+serratiopeptidase" and len(h.strengths) == 3


def test_liquids_resolve_to_a_composition_but_get_no_per_tablet_price_judgement():
    from dawa_buddy.brand_table import lookup
    assert lookup("DOLO 250 SUSPENSION", "liquid").salts == "paracetamol"
    f = one("DOLO 250 SUSPENSION | 1 | 45.00 | 45.00 | strip | 1")      # a strip price is meaningless for a bottle
    assert f.tier == b.TIER_UNIT_UNCLEAR and f.ingredients == "paracetamol"
    assert one("DOLO 250 SUSPENSION | 1 | 60.00 | 60.00 | bottle | 60 | 45.00").tier == b.TIER_ABOVE_MRP   # MRP check still works


def test_a_dropped_strength_number_must_match_the_product_found():
    from dawa_buddy.brand_table import lookup
    assert lookup("TAXIM-O 50 DRY SYRUP", "liquid") is None


def test_liquid_above_nppa_ceiling_is_priced_per_ml():
    # prednisolone 15 mg/5 ml: NPPA ceiling 0.88 per ml (x1.12 GST = 0.99). 60 ml at Rs 90 = 1.50 per ml.
    f = one("OMNACORTIL FORTE SYRUP | 1 | 90.00 | 90.00 | bottle | 60")
    assert f.tier == b.TIER_ABOVE_CEILING and abs(f.unit_price - 1.5) < 1e-6 and abs(f.possible_saving - 37.2) < 0.01
    assert one("OMNACORTIL FORTE SYRUP | 1 | 55.00 | 55.00 | bottle | 60").tier == b.TIER_OK


def test_liquid_generic_gap_uses_concentration_not_pack_size():
    # azithromycin 100 mg/5 ml, Jan Aushadhi 14.06 per 15 ml = 0.94 per ml
    f = one("ABIZITH 100 SUSPENSION | 1 | 140.00 | 140.00 | bottle | 15")
    assert f.tier == b.TIER_GENERIC_GAP and abs(f.generic_unit - 14.06 / 15) < 1e-3
    assert one("ABIZITH 100 SUSPENSION | 1 | 20.00 | 20.00 | bottle | 15").tier == b.TIER_OK


def test_topical_priced_per_gm_and_pack_size_read_from_description():
    f = one("CANDID CREAM 15GM | 1 | 120.00 | 120.00 | tube")
    assert f.tier == b.TIER_GENERIC_GAP and abs(f.unit_price - 8.0) < 1e-6


def test_liquid_without_pack_size_or_volume_in_strength_is_never_judged():
    assert one("OMNACORTIL FORTE SYRUP | 1 | 90.00 | 90.00 | bottle").tier == b.TIER_UNIT_UNCLEAR     # no ml given
    f = one("PERINORM SYRUP | 1 | 90.00 | 90.00 | bottle | 30")                                       # table strength has no per-ml
    assert f.tier == b.TIER_NO_BENCHMARK and "could not be read with certainty" in f.note


def test_mrp_is_per_pack_as_bills_print_it_and_needs_tablets_per_strip_for_per_tablet_rates():
    # Real layout: MRP 163.45 per strip of 15, sale price 9.81 per tablet (10% discount)
    f = one("SHELCAL 500MG TAB | 30 | 9.81 | 294.21 | tab | 15 | 163.45")
    assert f.tier == b.TIER_SUPPLEMENT and abs(f.mrp_pct - 90.0) < 0.1 and "within the MRP on your bill" in f.note
    f = one("SHELCAL 500MG TAB | 30 | 9.81 | 294.21 | tab | | 163.45")          # no pack: cannot compare, must not guess
    assert f.mrp_pct is None and "tablets per strip are missing" in f.note
    assert one("SHELCAL 500MG TAB | 30 | 12.00 | 360.00 | tab | 15 | 163.45").tier == b.TIER_ABOVE_MRP   # 12.00 > 10.90


def test_modified_release_suffix_missing_on_the_bill_still_finds_the_brand():
    from dawa_buddy.brand_table import lookup
    h = lookup("VELTAM 0.4MG TAB")
    assert h.salts == "tamsulosin" and h.strengths == [(0.4, "mg")] and h.modified_release


def test_reconcile_treats_a_different_variant_as_a_different_product():
    from dawa_buddy.reader import read_offline
    from dawa_buddy.reconcile import reconcile
    rx = read_offline("Tab Shelcal-XT 0-1-0 to continue\nTab Pantop 40 1-0-0 x 30 days")
    lines, _ = b.parse_bill_ex("SHELCAL 500MG TAB | 30 | 9.81 | 294.21 | tab\nPANTOP-D 40 | 1 | 120 | 120 | strip | 10")
    flags = reconcile(rx, lines)
    kinds = {(f.kind, f.subject) for f in flags}
    assert ("different_variant", "Shelcal-Xt -> SHELCAL 500MG TAB") in kinds and ("different_variant", "Pantop -> PANTOP-D 40") in kinds
    assert not any(k in ("not_billed", "not_prescribed") for k, _ in kinds)      # folded into the variant warning
    assert flags[0].kind == "different_variant"


def test_injection_per_vial_ceiling_and_generic():
    # ceftriaxone 250 mg: NPPA ceiling 29.02 per vial (x1.12 = 32.50); Jan Aushadhi 13.41
    f = one("AACEF 250 INJ | 1 | 90.00 | 90.00 | vial")
    assert f.tier == b.TIER_ABOVE_CEILING and f.ceiling == 29.02 and abs(f.possible_saving - 60.98) < 0.01
    assert one("AACEF 250 INJ | 1 | 26.00 | 26.00 | vial").tier == b.TIER_OK                # 1.9x the generic: under the 2x flag
    assert one("AACEF 250 INJ | 1 | 29.50 | 29.50 | vial").tier == b.TIER_GENERIC_GAP       # 2.2x: a question about the generic, though under the ceiling
    assert one("AMICAP 500 INJ | 1 | 150.00 | 150.00 | vial").tier == b.TIER_GENERIC_GAP     # amikacin 500 mg, no ceiling, JA 27.19


def test_injection_per_ml_ceiling_needs_the_ml_per_vial():
    # furosemide 10 mg/ml: ceiling 3.06 per ml. 5 ampoules of 2 ml at Rs 25 = 12.50 per ml
    f = one("LASIX INJ | 5 | 25.00 | 125.00 | vial | 2")
    assert f.tier == b.TIER_ABOVE_CEILING and abs(f.unit_price - 12.5) < 1e-6 and abs(f.possible_saving - 94.4) < 0.01
    assert one("LASIX INJ | 5 | 5.00 | 25.00 | vial | 2").tier == b.TIER_OK
    g = one("LASIX INJ | 5 | 25.00 | 125.00 | vial")                     # ml per ampoule unknown: must not guess
    assert g.tier == b.TIER_UNIT_UNCLEAR and "ml each vial" in g.note


def test_injection_strength_per_container_vs_per_ml_are_never_mixed_up():
    # 'Lasix 20' is 20 mg per ampoule; with 2 ml given it is 10 mg/ml and meets the per-ml ceiling, without ml it cannot
    assert one("LASIX 20 INJ | 1 | 3.00 | 3.00 | vial | 2").tier != b.TIER_ABOVE_CEILING   # 1.50 per ml
    assert one("LASIX 20 INJ | 1 | 30.00 | 30.00 | vial").tier == b.TIER_UNIT_UNCLEAR


def test_injection_with_unknown_unit_or_strength_gets_no_verdict():
    assert one("AACEF 250 INJ | 1 | 90.00 | 90.00 | tab").tier == b.TIER_UNIT_UNCLEAR
    assert one("ZYXOLEX 40 INJ | 1 | 90.00 | 90.00 | vial").tier in (b.TIER_NO_BENCHMARK, b.TIER_NEEDS_CONFIRM)


def test_variant_warning_says_what_actually_differs():
    from dawa_buddy.reconcile import compare_variants
    assert "adds amlodipine" in compare_variants("Concor 5", "CONCOR AM 5 TAB")
    assert "Same ingredients, different strength" in compare_variants("Telma 20", "TELMA 40 TAB")
    assert "could not look up" in compare_variants("Shelcal-XT", "SHELCAL 500MG TAB")          # not in the brand table: say so, don't guess


def test_variant_flag_carries_the_difference():
    from dawa_buddy.reader import read_offline
    from dawa_buddy.reconcile import reconcile
    rx = read_offline("Tab Concor 5 1-0-0 x 30 days")
    lines, _ = b.parse_bill_ex("CONCOR AM 5 TAB | 30 | 10 | 300 | tab")
    f = reconcile(rx, lines)[0]
    assert f.kind == "different_variant" and "adds amlodipine" in f.note



def test_generic_name_with_explicit_mg_prices_an_injection_and_nos_means_vials():
    f = one("ACYCLOTAS 500MG INJ ACYCLOVIR AEQUITAS HEALTHCARE PVT LTD | 13 | 568.14 | 7385.82 | vial | | 568.14")
    assert f.ingredients == "acyclovir" and f.ceiling == 541.14 and f.tier == b.TIER_OK     # 568.14 = ceiling + 5% GST
    from dawa_buddy import vision
    rows, _ = vision.clean_bill({"items": [{"description": "ACYCLOTAS 500MG INJ ACYCLOVIR", "qty": 13, "rate": 568.14,
                                            "amount": 7385.82, "unit": "NOS"}]})
    assert rows[0].unit == "vial"


def test_prescribed_generic_matches_a_bill_line_that_prints_it_after_the_brand():
    from dawa_buddy.reader import read_offline
    from dawa_buddy.reconcile import reconcile
    rx = read_offline("INJ.ACYCLOVIR, 500MG, IV, 1-1-1, AFTER FOOD X 7 DAYS")
    lines, _ = b.parse_bill_ex("ACYCLOTAS 500MG INJ ACYCLOVIR AEQUITAS HEALTHCARE PVT LTD | 13 | 568.14 | 7385.82 | vial")
    assert reconcile(rx, lines) == []


def test_iv_fluid_bill_naming_a_listed_special_features_maker_is_judged_against_that_ceiling():
    # NS 0.9% 100 ml: plain ceiling 20.15 non-glass / 22.36 glass; special-features pack (Denis Chem, Eurohead) 43.07.
    # The real bill charged 45.22 = 43.07 + 5% GST: within.
    f = one("NS EUROHEAD IV FLUIDS 0.9% 100ML DENIS HOUSE | 13 | 45.22 | 587.86")
    assert f.tier == b.TIER_OK and f.ceiling == 43.07 and "special-features" in f.note
    assert one("IV SET NOVOFUSION 30115 POLYMED | 2 | 265.00 | 530.00").tier == b.TIER_NOT_MEDICINE


def test_iv_fluid_between_the_two_ceilings_is_a_question_and_above_both_is_flagged():
    q = one("NS 0.9% 100ML | 13 | 45.22 | 587.86")                      # no maker named: which pack is it?
    assert q.tier == b.TIER_NEEDS_CONFIRM and "Which pack" in q.note and q.possible_saving == 0
    top = one("NS 0.9% 100ML | 13 | 60.00 | 780.00")                     # above even the special-features ceiling (x1.12 = 48.24)
    assert top.tier == b.TIER_ABOVE_CEILING and abs(top.possible_saving - (60 - 43.07) * 13) < 0.01
    assert one("NS 0.9% 100ML | 13 | 21.00 | 273.00").tier == b.TIER_OK
    assert one("RL 500ML | 4 | 57.00 | 228.00").tier == b.TIER_OK         # plain ringer lactate 500 ml ceiling 57.85


def test_special_features_lists_cover_more_fluids():
    assert one("METRONIDAZOLE 500MG/100ML IV | 3 | 25.00 | 75.00").tier == b.TIER_OK          # 0.25 per ml x 100 = 25.00
    assert one("RL 100ML EUROHEAD | 5 | 32.00 | 160.00").tier == b.TIER_OK                      # special RL 100 ml 30.62


def test_iv_fluid_container_named_on_the_bill_narrows_the_plain_ceiling():
    assert one("NS 0.9% 100ML GLASS | 1 | 24.00 | 24.00").tier == b.TIER_OK                      # 22.36 x 1.12 = 25.04
    n = one("NS 0.9% 100ML NON-GLASS | 1 | 24.00 | 24.00")                                       # 20.15 x 1.12 = 22.57 < 24 <= special
    assert n.tier == b.TIER_NEEDS_CONFIRM and "non-glass 20.15" in n.note


def test_substitution_of_the_same_salt_and_strength_is_not_a_mismatch():
    from dawa_buddy.reader import read_offline
    from dawa_buddy.reconcile import reconcile
    rx = read_offline("INJ.CEFTRIAXONE 250MG IV 1-0-1 X 2 DAYS\nTab Dolo 650 1-0-1 x 3 days")
    lines, _ = b.parse_bill_ex("AACEF 250 INJ | 4 | 29.00 | 116.00 | vial\nDOLO 650 TAB PARACETAMOL | 6 | 2.10 | 12.60 | tab")
    assert reconcile(rx, lines) == []        # different brand, same ingredients; and a bill that also prints the generic


def test_iv_fluid_prescribed_as_ns_matches_a_bill_line_with_brand_and_maker_words():
    from dawa_buddy.reader import read_offline
    from dawa_buddy.reconcile import reconcile
    rx = read_offline("INJ NS 100ML IV with each dose x 2 days")
    lines, _ = b.parse_bill_ex("NS EUROHEAD IV FLUIDS 0.9% 100ML NON-GLASS DENIS HOUSE | 13 | 45.22 | 587.86")
    assert not [f for f in reconcile(rx, lines) if f.kind in ("different_variant", "not_prescribed")]


def test_samples_show_the_results_they_promise():
    from dawa_buddy import samples
    from dawa_buddy.reader import read_offline
    from dawa_buddy.reconcile import reconcile
    out = {}
    for name, s in samples.SAMPLES.items():
        lines, rejected = b.parse_bill_ex(s["bill"])
        assert not rejected and abs(sum(l.amount for l in lines) - s["total"]) < 1.0           # totals add up
        out[name] = ({l.desc.split()[0]: b.audit_line(l).tier for l in lines},
                     {f.kind for f in reconcile(read_offline(s["rx"]), lines, s["total"])})
    t, kinds = out["Outpatient pharmacy bill"]
    assert t["TELMA"] == b.TIER_ABOVE_CEILING and t["AMLONG"] == b.TIER_ABOVE_MRP and t["ATORVA"] == b.TIER_GENERIC_GAP
    assert t["DOLO"] == b.TIER_GENERIC_GAP and t["SHELCAL"] == b.TIER_SUPPLEMENT and "different_variant" in kinds
    t, kinds = out["Hospital pharmacy bill"]
    assert t["AACEF"] == b.TIER_ABOVE_CEILING and t["LASIX"] == b.TIER_ABOVE_CEILING and t["ACYCLOTAS"] == b.TIER_OK
    assert t["SYRINGE"] == b.TIER_NOT_MEDICINE and "different_variant" not in kinds


def test_pack_size_is_only_suggested_when_the_brand_table_is_unambiguous():
    assert b.suggest_pack("VELTAM 0.4MG TAB") == 15 and b.suggest_pack("PANTOP 40 TAB") == 15
    assert b.suggest_pack("TELMA 40 TAB") is None          # sold in more than one pack size: never guess
    assert b.suggest_pack("SHELCAL 500MG TAB") is None     # not in the table


def test_a_consumable_billed_far_above_its_printed_mrp_is_caught_per_piece():
    """The Supreme Court heard a drip line with an MRP of 11 rupees sold for 270. A per-piece unit lets the printed MRP be compared with no pack size."""
    from dawa_buddy import bill as b
    line = b.BillLine(raw="IV SET", desc="IV INFUSION SET", qty=1, rate=270.0, amount=270.0, unit="each", pack=None, mrp=11.0)
    f = b.audit_line(line)
    assert f.tier == b.TIER_ABOVE_MRP and f.mrp_unit == 11.0 and f.possible_saving == 259.0
    ok = b.audit_line(b.BillLine(raw="IV SET", desc="IV SET", qty=1, rate=11.0, amount=11.0, unit="each", pack=None, mrp=11.0))
    assert ok.tier == b.TIER_NOT_MEDICINE and ok.mrp_pct == 100.0
    no_unit = b.audit_line(b.BillLine(raw="IV SET", desc="IV SET", qty=1, rate=270.0, amount=270.0, unit=None, pack=None, mrp=11.0))
    assert no_unit.tier != b.TIER_ABOVE_MRP                       # without a unit nothing is assumed: the note says the check could not be made


def test_the_hospital_sample_shows_the_consumable_markup():
    from dawa_buddy import bill as b, samples
    lines, _ = b.parse_bill_ex(samples.SAMPLES["Hospital pharmacy bill"]["bill"])
    iv = [b.audit_line(l) for l in lines if "IV SET" in l.desc][0]
    assert iv.tier == b.TIER_ABOVE_MRP and iv.line.unit == "each"


def test_prolonged_release_with_a_space_is_not_read_as_an_ingredient():
    """Jan Aushadhi writes 'Prolonged release' with a space; 'prolonged' was read as an ingredient so metformin SR never matched its own entry."""
    from dawa_buddy import benchmarks, bill as b
    assert benchmarks.parse_ingredients("Metformin Hydrochloride Prolonged release Tablets IP 500 mg") == frozenset({"metformin"})
    f = b.audit_line(b.BillLine(raw="g", desc="TAB.GLYCOMET-500 SR", qty=60, rate=3.6, amount=216.0, unit="tab", pack=20, mrp=72.0))
    assert f.tier == b.TIER_GENERIC_GAP and "1.08" in f.note              # the 500 mg prolonged-release generic is 10.79 for 10 tablets


# --- bills that print the tax-inclusive per-unit MRP, two values in one cell, and the maker under the name (two real bills, 29 Oct 2026) ---
def test_form_words_include_jelly():
    assert b.form_of_desc("LOX 2% JELLY") == "topical" and b.form_of_desc("LACTIHEP SYP") == "liquid" and b.form_of_desc("HIFENAC P TAB") == "tablet"
    assert b.resolve("LOX 2% JELLY")[:3] == ("lidocaine", [(2.0, "%")], "topical")        # the brand table has it; the tablet lookup could never find it


def test_combination_named_in_words_is_never_priced_as_one_salt():
    # "ACECLOFENAC + PARACETAMOL" was priced against plain paracetamol 500 mg and flagged above its ceiling: a false accusation
    f = b.audit_line(b.BillLine("x", "ACECLOFENAC + PARACETAMOL TAB", 10, 5.0, 50.0, "tab", 10, 50.0))
    assert f.tier not in (b.TIER_ABOVE_CEILING, b.TIER_ABOVE_MRP)
    f = b.audit_line(b.BillLine("x", "HIFENAC P TAB ACECLOFENAC +PARACETAMOL INTAS", 15, 5.53, 82.95, "tab", 1, 5.53))
    assert f.tier != b.TIER_ABOVE_CEILING and "aceclofenac" in (f.ingredients or "")


def test_vision_cleaning_handles_tax_inclusive_per_unit_bills():
    from dawa_buddy import vision
    rows, _ = vision.clean_bill({"items": [
        {"description": "DOLO 650MG TAB H/30049061/Aristo Pharmaceutica", "qty": 6, "rate": 2.24, "amount": 13.44, "unit": "tab", "mrp": 2.24, "mrp_per": "unit"},
        {"description": "LACTIHEP SYP", "qty": 1, "rate": 278, "amount": 278, "unit": None, "mrp": 278},
        {"description": "LOX 2% JELLY", "qty": 1, "rate": 35.5, "amount": 35.5, "unit": None},
        {"description": "X 10MG TAB", "qty": 2, "rate": 3, "amount": 6, "unit": "tab", "pack": 10, "mrp": 3, "mrp_per": "unit"}]})
    assert rows[0].description == "DOLO 650MG TAB" and rows[0].mrp_each and rows[0].pack is None and rows[0].mrp == 2.24      # per-tablet MRP kept as printed, no strip size invented
    assert rows[1].unit == "bottle" and rows[2].unit == "tube"                                      # the name states the form
    assert rows[3].mrp == 3.0 and rows[3].mrp_each and rows[3].pack == 10                          # known strip size: still the per-tablet MRP as printed
    f = b.audit_line(vision.rows_to_lines(rows)[0])
    assert f.tier != b.TIER_ABOVE_MRP                                                            # charged = MRP, never "above"


def test_bill_prompt_names_the_tax_inclusive_column():
    from dawa_buddy import vision
    assert "Taxable" in vision.BILL_PROMPT and "Val In-GST" in vision.BILL_PROMPT and "mrp_per" in vision.BILL_PROMPT


# --- arithmetic: pick the numbers that multiply out, as a person would (no model involved) ---
def test_solver_finds_quantity_price_and_value_on_a_two_value_cell_row():
    from dawa_buddy import vision as v
    cells = [2.24, 6, 12.0, 6, 0.72, 6, 0.72, 0, 0.0, 13.44, 2.24, 0]          # Dolo, second real bill: the Taxable column (12.00) is not the value
    best = v.row_candidates(cells, (6, 2.24))[0]
    assert best[:3] == (6.0, 2.24, 13.44)


def test_solver_uses_the_model_labels_to_break_a_6_by_11_tie():
    from dawa_buddy import vision as v
    assert v.row_candidates([11.0, 6, 58.92, 66.0, 11.0], (6, 11.0))[0][:3] == (6.0, 11.0, 66.0)


def test_solver_makes_the_lines_add_up_to_the_printed_total():
    from dawa_buddy import vision as v
    a = [(2.0, 5.0, 10.0, 0), (5.0, 2.0, 10.0, 0), (1.0, 12.0, 12.0, 1)]      # row 1 is ambiguous
    b = [(3.0, 4.0, 12.0, 0)]
    assert [c[2] for c in v.choose_rows([a, b], 22.0)] == [10.0, 12.0]
    assert [c[2] for c in v.choose_rows([a, b], 24.0)] == [12.0, 12.0]


def test_amount_before_tax_is_replaced_by_the_value_with_tax():
    from dawa_buddy import vision as v
    rows, _ = v.clean_bill({"items": [{"description": "X TAB", "qty": 6, "rate": 13.14, "amount": 88.3, "unit": "tab", "cells": [1, 6, 13.14, 78.84, 4.73, 4.73, 88.3]}]})
    assert rows[0].amount == 88.3 and rows[0].qty == 6 and abs(rows[0].rate * 6 - 88.3) < 0.01
    ok, _ = v.clean_bill({"items": [{"description": "Y TAB", "qty": 15, "rate": 5.53, "amount": 82.95, "unit": "tab", "cells": [5.53, 15, 0.0, 12, 8.89, 82.95]}]})
    assert ok[0].amount == 82.95                                                  # already the value with tax: left alone


def test_missing_rate_is_worked_out_and_mrp_per_tablet_or_per_strip_is_told_from_the_numbers():
    from dawa_buddy import vision as v
    rows, _ = v.clean_bill({"items": [
        {"description": "A TAB", "qty": 10, "rate": None, "amount": 50.0, "unit": "tab"},
        {"description": "B TAB", "qty": 30, "rate": 9.81, "amount": 294.3, "unit": "tab", "mrp": 163.45},       # strip MRP: many times a tablet's price
        {"description": "C TAB", "qty": 6, "rate": 11.0, "amount": 66.0, "unit": "tab", "mrp": 11.0}]})        # per-tablet MRP: about the price of one tablet
    assert rows[0].rate == 5.0
    assert rows[1].pack is None and rows[1].mrp == 163.45
    assert rows[2].mrp_each and rows[2].pack is None and not rows[1].mrp_each


def test_a_batch_code_or_date_in_the_numbers_list_does_not_break_the_json():
    from dawa_buddy import llm
    assert llm._extract_json('{"items":[{"cells":[1,K2100680,MAR-23,15.00]}]}')["items"][0]["cells"] == [1, "K2100680", "MAR-23", 15.0]


def test_a_composition_printed_on_the_bill_that_matches_the_table_is_trusted():
    # "HIFENAC P TAB ACECLOFENAC +PARACETAMOL INTAS" and "AUGMENTIN 625MG DUO TAB - AMOXICILLIN CLAVUNIC POTASSIUM" were sent to the user to identify although the bill names the
    # ingredients and the brand table agrees. A third ingredient the bill does not name still blocks it (Zerodol-SP).
    assert b.composition_stated("HIFENAC P TAB ACECLOFENAC +PARACETAMOL INTAS", "aceclofenac+paracetamol")
    assert b.composition_stated("AUGMENTIN 625MG DUO TAB - AMOXICILLIN CLAVUNIC POTASSIUM", "amoxicillin+clavulanic acid")        # a misspelling still counts
    assert not b.composition_stated("PARACIP-C TAB", "paracetamol+caffeine")                                                      # a brand name that contains 'parac' proves nothing
    assert not b.composition_stated("ZERODOL SP TAB ACECLOFENAC PARACETAMOL", "aceclofenac+paracetamol+serratiopeptidase")
    f = b.audit_line(b.BillLine("x", "AUGMENTIN 625MG DUO TAB - AMOXICILLIN CLAVUNIC POTASSIUM", 10, 20.17, 201.7, "tab", 1, 20.17))
    assert f.tier != b.TIER_NEEDS_CONFIRM


def test_online_matching_ignores_the_composition_and_maker_printed_after_the_form_word():
    from dawa_buddy import webcheck as w
    assert w.desc_brand("HIFENAC P TAB ACECLOFENAC +PARACETAMOL INTAS") == "HIFENAC P"
    assert w.same_product("Hifenac P Tablet - Uses, Side Effects, Price", "HIFENAC P TAB ACECLOFENAC +PARACETAMOL INTAS")
    assert not w.same_product("Hifenac Plus Tablet", "HIFENAC P TAB ACECLOFENAC +PARACETAMOL INTAS")                               # a different brand is still refused


def test_reference_rows_show_what_the_verdict_used():
    from dawa_buddy import transparency as t
    rupees = lambda x: f"₹{x:g}"
    f = b.audit_line(b.BillLine("x", "HIFENAC P TAB ACECLOFENAC +PARACETAMOL INTAS", 15, 5.53, 82.95, "tab", 1, 5.53))
    rows, foot = t.reference(f, rupees)
    d = dict(rows)
    assert d["Identified as"].startswith("aceclofenac+paracetamol") and "brand table" in d["Taken from"] and "your bill" in d["Taken from"]
    assert "Jan Aushadhi generic" in d
    assert d["NPPA ceiling"] == "none applies" and "1 April 2026" in foot                  # a missing ceiling is said out loud, with the date of the list
    over = b.audit_line(b.BillLine("x", "PARACETAMOL 500MG TAB", 10, 5.0, 50.0, "tab", 10, 50.0))
    rows, _ = t.reference(over, rupees)
    assert "NPPA ceiling" in dict(rows) and "with GST" in dict(rows)["NPPA ceiling"]
    iv = b.audit_line(b.BillLine("x", "IV SET", 2, 265.0, 530.0, "each", None, 11.0))
    assert "MRP on your bill (per piece)" in dict(t.reference(iv, rupees, lambda u: "piece")[0]) and any(k.startswith("You were charged") for k, _ in t.reference(iv, rupees, lambda u: "piece")[0])
    nm = b.audit_line(b.BillLine("x", "BED CHARGES", 1, 1000.0, 1000.0, "each", None, None))
    assert not any(k == "NPPA ceiling" for k, _ in t.reference(nm, rupees)[0])                  # a room is not a medicine: no ceiling line


def test_the_questions_ask_the_patient_to_compare_the_bill_mrp_with_the_strip():
    from dawa_buddy import report
    f = b.audit_line(b.BillLine("x", "PAN 40MG TAB", 6, 11.0, 66.0, "tab", 1, 11.0))
    text = report.questions([f])
    assert "## Check the MRP on the strip" in text and "the seller's own figure" in text and "PAN 40MG TAB" in text and "MRP of 11.00" in text
    assert "## Check the MRP on the strip" not in report.questions([b.audit_line(b.BillLine("x", "PAN 40MG TAB", 6, 11.0, 66.0, "tab", None, None))])      # no MRP printed, nothing to compare
