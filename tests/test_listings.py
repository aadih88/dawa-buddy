"""Fixtures are copied (shortened) from the real pages Tavily returned on 27 Oct 2026."""
from dawa_buddy import listings as L

PHARMEASY = ("# Concor T 5 Tablet  10 Tablet(s) in Strip  MRP₹174.75  ₹132.81  24% OFF  ₹13.28/tablet (Inclusive of all taxes)  15 days return policy")
ONE_MG = ("Cold Storaged Medication  ₹166  MRP ₹174.75  5% off  (Inclusive of applicable taxes)  Get for  ₹141  10 tablets  MRP may vary by batch. "
          "Any additional charges, including packaging, handling, shipping or...")
TRUEMEDS = "[x](#introduction)  MRP ~~₹174.75~~  20% off  \\*MRP inclusive of all taxes  100% genuine medicines"
NETMEDS = "[Hypertension](/collection/hypertension-medicines)  MRP  ₹155.53 (Inclusive of all taxes)  Deliver to"
APOLLO = "Durex Extra Time Condoms, 10 Count  MRP ₹356  25% off  Dabur Shilajit Gold, 20 Capsules  MRP ₹560  12% off"


def fake_search(results):
    return lambda q: results


def r(url, title, text):
    return {"url": url, "title": title, "raw_content": text}


CONCOR = [r("https://pharmeasy.in/online-medicine-order/concor-t-5-strip-of-10-tablets-1", "Concor T 5 Tablet: Uses, Side Effects, Price, Dosage & More", PHARMEASY),
          r("https://www.1mg.com/drugs/concor-t-5mg-40mg-tablet-1", "Buy Concor T 5mg/40mg Tablet Online: View Uses, Side Effects, Price", ONE_MG),
          r("https://www.truemeds.in/medicine/concor-t-405-mg-tablet-10", "Concor T 5 Tablet 10: Uses, Side Effects, Price & Substitute", TRUEMEDS),
          r("https://www.netmeds.com/prescriptions/concor-t-5-tablet-10s", "CONCOR T 5 Tablet 10's : Price, Uses, Side Effects | Netmeds", NETMEDS),
          r("https://www.1mg.com/drugs/concor-5-tablet-2", "Buy CONcor 5 Tablet Online: View Uses, Side Effects, Price", "MRP ₹145.39  10 tablets"),      # a different product
          r("https://www.apollopharmacy.in/medicine/concor-t-5", "Buy Concor T 5 Tablet online | Uses, Side Effects, Price", APOLLO)]


def test_only_the_same_product_matches_by_name_and_strength():
    want = ["telma", "40"]
    assert L.title_matches(want, "Telma 40 Tablet: Uses, Side Effects, Price")
    assert not L.title_matches(want, "Telma H 40mg Strip Of 30 Tablets")           # a different combination
    assert not L.title_matches(want, "Telma Am 40/5mg Strip Of 30 Tablets")
    assert not L.title_matches(["concor", "t", "5"], "Buy CONcor 5 Tablet Online")  # Concor 5 is not Concor T 5
    assert L.title_matches(["veltam", "0.4"], "Veltam 0.4 Tablet MR Online: View Uses")


def test_pack_size_and_first_mrp_are_read_from_each_sites_own_layout():
    got = {p.domain: (p.pack, p.mrp) for p in map(lambda x: L.parse_page(x["url"], x["title"], x["raw_content"]), CONCOR[:4])}
    assert got["pharmeasy.in"] == (10, 174.75) and got["1mg.com"] == (10, 174.75) and got["truemeds.in"] == (10, 174.75) and got["netmeds.com"] == (10, 155.53)


def test_apollo_prices_are_never_read_because_its_pages_list_other_products():
    p = L.parse_page(CONCOR[5]["url"], CONCOR[5]["title"], APOLLO)
    assert p.mrp is None


def test_listing_agrees_a_pack_only_when_two_sites_do_and_uses_the_highest_mrp_per_tablet():
    lst = L.search("CONCOR T 5MG TAB", fake_search(CONCOR))
    assert lst.pack == 10 and set(lst.pack_sites) >= {"pharmeasy.in", "1mg.com"}
    assert abs(lst.per_tablet_max - 17.475) < 1e-9                       # 174.75 / 10, backed by three sites; the stale Netmeds 155.53 does not lower it
    assert all("concor-5-tablet" not in p.url for p in lst.pages)         # the wrong product was filtered out
    one_site = L.search("CONCOR T 5MG TAB", fake_search(CONCOR[:1]))
    assert one_site.pack is None                                          # one site alone is not agreement


def test_a_bill_mrp_that_agrees_is_fine_and_one_far_above_every_listing_is_only_a_question():
    lst = L.search("CONCOR T 5MG TAB", fake_search(CONCOR))
    assert L.judge(lst, 15.73, 17.475)["kind"] == "agrees"
    assert L.judge(lst, 15.73, 17.475 * 1.25)["kind"] == "printed_above_listings"
    assert L.judge(lst, 15.73, 17.475 * 1.08)["kind"] == "agrees"           # within the 10% a year NPPA allows
    assert L.judge(lst, 20.0, None)["kind"] == "charged_above_listed_mrp" and L.judge(lst, 15.73, None)["kind"] == "within_listed_mrp"


def test_no_key_means_no_lookup(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert L.search("CONCOR T 5MG TAB") is None


def test_one_odd_listing_cannot_set_the_reference_and_no_agreement_means_no_reference():
    def page(dom, mrp, pack):
        return L.Page(dom, "https://" + dom, "x", pack, mrp)
    dolo = [page("truemeds.in", 33.6, 10), page("pharmeasy.in", 32.28, 15), page("1mg.com", 32.28, 15), page("netmeds.com", 20.16, 10)]
    assert abs(L.combine("dolo", dolo).per_tablet_max - 32.28 / 15) < 1e-9          # the 10's listing at 3.36 per tablet is an outlier
    pantop = [page("pharmeasy.in", 499.0, 15), page("1mg.com", 174.45, 15), page("netmeds.com", 155.26, 15), page("truemeds.in", 47.53, 15)]
    assert L.combine("pantop", pantop).per_tablet_max is None                       # no two sites within 10%: say nothing rather than guess
    assert L.judge(L.combine("pantop", pantop), 12.0, None) is None
    same_site = [page("pharmeasy.in", 100.0, 10), page("pharmeasy.in", 100.0, 10)]
    assert L.combine("x", same_site).per_tablet_max is None                         # the same site twice is not two sites
