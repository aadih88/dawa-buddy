from dawa_buddy import benchmarks as b


def test_file_shape():
    idx = b.index()
    assert len(idx) == 2439 and len({r.code for r in idx}) == 2439


def test_zero_price_means_unavailable_not_free():
    idx = b.index()
    zero = [r for r in idx if r.mrp == 0]
    assert len(zero) == 343 and all(not r.available and r.price_per_unit is None for r in zero)


def test_per_unit_not_per_strip():
    r = b.find("telmisartan", [(40.0, "mg")])[0]
    assert r.unit_size == "10's" and abs(r.price_per_unit - r.mrp / 10) < 1e-6


def test_paracetamol_650_exists_with_15_pack():
    r = b.find("paracetamol", [(650.0, "mg")])[0]
    assert r.pack_units == 15 and r.available


def test_spelling_variants_resolve():
    assert b.find("amoxicillin+clavulanic acid", [(500.0, "mg"), (125.0, "mg")])
    assert b.find("thyroxine", [(100.0, "mcg")])


def test_combo_does_not_match_single():
    r = b.find("metformin", [(500.0, "mg")])
    assert all(len(x.ingredients) == 1 for x in r)


def test_enteric_coated_aspirin_matches():
    r = b.find("aspirin", [(75.0, "mg")])
    assert r and r[0].unit_size == "14's"


def test_genuine_gap_returns_nothing_not_a_wrong_match():
    # JA lists cetirizine only as syrup/combos (levocetirizine tablets are a different salt)
    assert b.find("cetirizine", [(10.0, "mg")]) == []


def test_indian_pharmacopoeia_spellings_map_to_common_names():
    assert b.find("furosemide", [(40.0, "mg")])            # JA lists it as 'Frusemide'
    assert b.find("torsemide", [(20.0, "mg")])             # JA lists it as 'Torasemide'
