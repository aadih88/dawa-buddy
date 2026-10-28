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
    assert f.tier == b.TIER_SUPPLEMENT and "within the printed MRP" in f.note
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
    assert f.tier == b.TIER_SUPPLEMENT and abs(f.mrp_pct - 90.0) < 0.1 and "within the printed MRP" in f.note
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
    assert one("AACEF 250 INJ | 1 | 29.50 | 29.50 | vial").tier == b.TIER_OK
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
    assert t["DOLO"] == b.TIER_OK and t["SHELCAL"] == b.TIER_SUPPLEMENT and "different_variant" in kinds
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
