import json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from dawa_buddy import webcheck


def test_parse_groups_only_across_explicit_joiners_and_drops_stray_words():
    g = webcheck.parse_compositions("Clopidogrel (75mg) Contains Aspirin (75mg)+ Atorvastatin (10mg)+ Clopidogrel (75mg) is used")
    assert max(g, key=len) == frozenset({("aspirin", "75mg"), ("atorvastatin", "10mg"), ("clopidogrel", "75mg")})
    assert frozenset({("clopidogrel", "75mg")}) in g
    c = webcheck.parse_compositions("Augmentin: Amoxycillin (500mg) + Clavulanic Acid (125mg)")[0]
    assert c == frozenset({("amoxicillin", "500mg"), ("clavulanic acid", "125mg")})


def res(url, content):
    return {"url": url, "title": "", "content": content}


def page(url, title, content="", raw=""):
    return {"url": url, "title": title, "content": content, "raw_content": raw}


def test_consensus_needs_two_different_sites_and_no_equal_rival():
    one_site = webcheck.gather([res("https://www.1mg.com/a", "Telmisartan (40mg)"), res("https://www.1mg.com/b", "Telmisartan (40mg)")])
    assert one_site.consensus is None                           # same site twice is not independent
    two = webcheck.gather([res("https://www.1mg.com/a", "Telmisartan (40mg)"), res("https://pharmeasy.in/b", "contains Telmisartan (40mg)")])
    assert two.consensus == frozenset({("telmisartan", "40mg")})
    split = webcheck.gather([res("https://www.1mg.com/a", "Telmisartan (40mg)"), res("https://pharmeasy.in/b", "Telmisartan (80mg)")])
    assert split.consensus is None and "Read the composition off the strip" in split.note


def test_agreement_with_the_brand_table_is_reported():
    from dawa_buddy.brand_table import lookup
    ev = webcheck.gather([res("https://www.1mg.com/a", "Telmisartan (40mg)"), res("https://pharmeasy.in/b", "Telmisartan (40mg)")],
                         lookup("TELMA 40 TAB"))
    assert ev.agrees_with_table is True


def test_no_key_means_no_lookup_and_no_network(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert webcheck.lookup_brand("TELMA 40 TAB") is None


class FakeTavily(BaseHTTPRequestHandler):
    seen = {}
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeTavily.seen = {"path": self.path, "auth": self.headers["Authorization"], "body": body}
        out = {"results": [page("https://www.1mg.com/x", "Buy Zerodol-SP Tablet Online: Uses, Price", "Aceclofenac (100mg)+ Paracetamol (325mg)+ Serratiopeptidase (15mg)"),
                           page("https://www.apollopharmacy.in/y", "Zerodol SP Tablet 15's Substitute", "ACECLOFENAC (100mg) + PARACETAMOL (325mg) + SERRATIOPEPTIDASE (15mg)"),
                           page("https://www.1mg.com/z", "Buy Zerodol-P Tablet Online", "Aceclofenac (100mg) + Paracetamol (325mg)")]}
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(out).encode())
    def log_message(self, *a): pass


def test_lookup_sends_only_the_brand_and_returns_evidence(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), FakeTavily)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(webcheck, "BASE_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    ev = webcheck.lookup_brand("ZERODOL-SP TAB")
    assert len(ev.consensus) == 3 and FakeTavily.seen["auth"] == "Bearer tvly-test"
    sent = json.dumps(FakeTavily.seen["body"])
    assert "ZERODOL" in sent.upper() and set(FakeTavily.seen["body"]) == {"query", "search_depth", "max_results", "include_raw_content", "include_domains"}


@pytest.mark.parametrize("title,desc,ok", [
    ("Buy Veltam 0.4 Tablet MR Online: View Uses, Side Effects, Price", "VELTAM 0.4MG TAB", True),
    ("Buy Veltam Plus Tablet MR Online: View Uses", "VELTAM 0.4MG TAB", False),            # a different product
    ("Buy Veltam-F Tablet MR Online", "VELTAM 0.4MG TAB", False),
    ("Concor T 5 Tablet 10's Substitute - Alternatives, Uses", "TAB.CONCOR T 5MG/40", True),
    ("Concor 5 Tablet: Uses, Side Effects, Price", "TAB.CONCOR T 5MG/40", False),         # Concor is not Concor T
    ("Buy Concor T 2.5mg/40mg Tablet Online", "TAB.CONCOR T 5MG/40", False),              # a different strength
    ("Buy Concor T 5mg/40mg Tablet Online: View Uses", "TAB.CONCOR T 5MG/40", True),
    ("Roseday-Gold Capsule 10's Substitute", "TAB.ROSEDAY GOLD, 75MG/75MG/10MG", True),
    ("Buy Roseday-A 10 Capsule Online", "TAB.ROSEDAY GOLD, 75MG/75MG/10MG", False),
])
def test_a_page_counts_only_if_it_is_the_same_product(title, desc, ok):
    assert webcheck.same_product(title, desc) is ok


def test_pages_about_other_products_do_not_vote_and_one_clear_answer_is_offered_as_a_suggestion():
    pages = [page("https://www.1mg.com/a", "Buy Veltam 0.4 Tablet MR Online", raw="Marketer\nComposition:\n\n[Tamsulosin (0.4mg)](https://x)\n\nUses"),
             page("https://www.apollopharmacy.in/b", "Veltam 0.4 Tablet 15's Substitute"),                      # says nothing readable
             page("https://www.1mg.com/c", "Buy Veltam Plus Tablet MR Online", "Dutasteride (0.5mg) + Tamsulosin (0.4mg)")]   # other product
    ev = webcheck.gather(pages, desc="VELTAM 0.4MG TAB")
    assert ev.skipped == 1 and ev.consensus is None
    assert ev.best == frozenset({("tamsulosin", "0.4mg")}) and "Only one site" in ev.note        # a suggestion, labelled as such


def test_the_composition_paragraph_of_a_full_page_is_read_when_the_snippet_leaves_it_out():
    raw = "Home > Drugs\nComposition:\n\n[Bisoprolol (5mg) + Telmisartan (40mg)](https://www.1mg.com/generics/x)\n\nMarketer detail"
    assert "Bisoprolol (5mg) + Telmisartan (40mg)" in webcheck.composition_text(raw)
    ev = webcheck.gather([page("https://www.1mg.com/a", "Buy Concor T 5mg/40mg Tablet Online", raw=raw),
                          page("https://www.truemeds.in/b", "Concor T 5 Tablet 10's: Uses", "bisoprolol (5mg) + telmisartan (40mg)")], desc="TAB.CONCOR T 5MG/40")
    assert ev.consensus == frozenset({("bisoprolol", "5mg"), ("telmisartan", "40mg")})


def test_disagreement_and_empty_results_are_worded_differently():
    d = webcheck.gather([page("https://www.1mg.com/a", "Telma 40 Tablet", "Telmisartan (40mg)"), page("https://pharmeasy.in/b", "Telma 40 Tablet", "Telmisartan (80mg)")], desc="TELMA 40 TAB")
    assert d.best is None and "disagree" in d.note
    n = webcheck.gather([page("https://www.1mg.com/a", "Telma 40 Tablet")], desc="TELMA 40 TAB")
    assert n.best is None and "No page for this exact product" in n.note


def test_a_label_run_into_the_salt_name_is_not_part_of_the_name():
    # PharmEasy's snippet reads "Salt ContentTinidazole(600.0 Mg)+Ciprofloxacin(500.0 Mg)": "content" must not become "contenttinidazole" (Cifran CT, 29 Oct 2026)
    want = [frozenset({("tinidazole", "600mg"), ("ciprofloxacin", "500mg")})]
    for text in ("Salt ContentTinidazole(600.0 Mg)+Ciprofloxacin(500.0 Mg)", "Salt Content[Tinidazole(600.0 Mg)+Ciprofloxacin(500.0 Mg)",
                 "Salt Content, Tinidazole(600.0 Mg)+Ciprofloxacin(500.0 Mg)"):
        assert webcheck.parse_compositions(text) == want, text


def test_apollos_upper_case_hyphen_format_is_read_but_a_brand_and_strength_title_is_not():
    from dawa_buddy import webcheck as w
    assert w.parse_compositions("CIPROFLOXACIN-500MG+TINIDAZOLE-600MG](https://www.apollopharmacy.in/salt/x)") == [frozenset({("ciprofloxacin", "500mg"), ("tinidazole", "600mg")})]
    assert w.parse_compositions("SHELCAL-500MG Tablet") == []            # 'Shelcal' is a brand, not a salt
