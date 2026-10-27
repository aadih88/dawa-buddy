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
        out = {"results": [res("https://www.1mg.com/x", "Zerodol-SP: Aceclofenac (100mg)+ Paracetamol (325mg)+ Serratiopeptidase (15mg)"),
                           res("https://www.apollopharmacy.in/y", "ACECLOFENAC (100mg) + PARACETAMOL (325mg) + SERRATIOPEPTIDASE (15mg)")]}
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
    assert "ZERODOL" in sent.upper() and set(FakeTavily.seen["body"]) == {"query", "search_depth", "max_results", "include_domains"}
