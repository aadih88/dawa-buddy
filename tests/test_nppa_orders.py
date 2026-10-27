"""Rows below are copied (shortened) from real nppa.gov.in order lists returned by Tavily on 27 Oct 2026."""
from dawa_buddy import nppa_orders as N

LIST_A = ("# 14 Telmisartan and Bisoprolol Fumarate Tablets Each film coated tablet contains: Telmisartan IP 40mg Bisoprolol Fumarate IP 2.5mg "
          "1 Tablet M/s Ravenbhel Healthcare Pvt. Ltd. / M/s Emcure Pharmaceuticals Limited 10.97 "
          "# 15 Telmisartan and Bisoprolol Fumarate Tablets Each film coated tablet contains: Telmisartan IP 40mg Bisoprolol Fumarate IP 5mg "
          "1 Tablet M/s Ravenbhel Healthcare Pvt. Ltd. / M/s Emcure Pharmaceuticals Limited 12.62 # 16 Cetirizine")
LIST_B = ("6 Bisoprolol Fumarate & Telmisartan Tablets Each uncoated bilayered tablet contains: Bisoprolol Fumarate IP 5 mg Telmisartan IP 40 mg "
          "1 Tablet M/s Windlas Biotech Ltd./ M/s Alkem Wellness Ltd. 12.55 7 Cetirizine Ophthalmic Solution")
LIST_C = ("4(12) Bisoprolol Fumarate and Telmisartan Tablets Each Film Coated Tablet Contains: Bisoprolol Fumarate IP 5 mg Telmisartan IP 40 mg "
          "1 Tablet M/s Akums Drugs &Pharmaceuticals Ltd./ M/s Workcell Solutions Pvt. Ltd. 12.71 13 4(14) Cetirizine Hydrochloride Drops")
WANT = N.parse_wanted("bisoprolol 5 mg + telmisartan 40 mg")


def test_the_users_wording_and_an_order_row_have_the_same_shape():
    assert WANT == (("bisoprolol", 5.0), ("telmisartan", 40.0))
    assert N.parse_wanted("Bisoprolol Fumarate (5mg) + Telmisartan (40mg)") == WANT


def test_rows_are_read_with_company_and_price_and_only_the_exact_strength_matches():
    rows = N.parse(LIST_A)
    assert [(r.price, r.unit) for r in rows] == [(10.97, "tablet"), (12.62, "tablet")]
    five = N.matching(rows, WANT)
    assert len(five) == 1 and five[0].price == 12.62 and "Emcure" in five[0].company       # the 2.5 mg product is not the 5 mg one


def test_other_list_layouts_give_the_other_companies_prices():
    got = {(("Alkem" if "Alkem" in r.company else "Workcell"), r.price) for t in (LIST_B, LIST_C) for r in N.matching(N.parse(t), WANT)}
    assert got == {("Alkem", 12.55), ("Workcell", 12.71)}


def test_text_without_a_price_row_gives_nothing_rather_than_a_guess():
    assert N.parse("The Authority discussed the matter. Bisoprolol 5 mg + Telmisartan 40 mg was considered.") == []


def test_questions_file_carries_the_peer_price_lines_with_the_not_a_limit_warning():
    from dawa_buddy.report import questions
    text = questions([], None, ["CONCOR T: you paid ₹15.73 per tablet; others are ₹11.60 to ₹12.71 before GST."])
    assert "Other brands of the same medicine" in text and "not a legal limit on your brand" in text and "CONCOR T" in text
