from dawa_buddy import benchmarks as ja, ceilings as nc


def test_row_counts_match_poster_headlines():
    cats = {}
    for c in nc.index():
        cats[c.category] = cats.get(c.category, 0) + 1
    # three gazette notifications of 25.03.2026 (serials checked contiguous by the parser) ...
    assert cats["nlem2022"] == 767 and cats["nlem2015"] == 138 and cats["nlem2011"] == 6
    # ... plus the March 2026 poster rows none of them contain (233 of 267 poster rows matched with identical prices)
    assert sum(cats.values()) - 911 == 34


def test_known_ceilings():
    assert nc.find("atorvastatin", [(10.0, "mg")])[0].price == 5.09
    assert nc.find("telmisartan", [(40.0, "mg")])[0].price == 6.92
    assert nc.find("metformin", [(500.0, "mg")])[0].price == 2.07


def test_modified_release_is_separate_from_immediate_release():
    assert nc.find("metformin", [(1000.0, "mg")])[0].price == 3.57
    assert nc.find("metformin", [(1000.0, "mg")], modified_release=True)[0].price == 4.15


def test_missing_ceiling_is_empty_not_zero():
    assert nc.find("nonexistentium", [(650.0, "mg")]) == []
    assert nc.find("paracetamol", [(650.0, "mg")])[0].price == 2.05


def test_legal_ceiling_is_far_above_generic_benchmark():
    c = nc.find("glimepiride", [(1.0, "mg")])[0].price
    g = ja.find("glimepiride", [(1.0, "mg")])[0].price_per_unit
    assert c / g > 5


def test_aspirin_synonym_links_ceiling_and_generic():
    assert nc.find("aspirin", [(75.0, "mg")])[0].price == 0.36   # listed as 'Acetylsalicylic acid' by NPPA
    assert ja.find("aspirin", [(75.0, "mg")])
