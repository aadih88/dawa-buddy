"""Exercise the Ollama code path against a fake local server (no real model needed)."""
import json, os, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest


class Fake(BaseHTTPRequestHandler):
    reply = {}
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["format"] == "json" and body["stream"] is False
        user = body["messages"][-1]["content"]
        content = json.dumps(next((v for k, v in Fake.reply.items() if k in user), {"salt": None}))
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"message": {"role": "assistant", "content": content}}).encode())
    def log_message(self, *a): pass


@pytest.fixture()
def fake_ollama(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=srv.serve_forever, daemon=True).start()
    from dawa_buddy import llm
    monkeypatch.setattr(llm, "OLLAMA_HOST", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("DAWA_PROVIDER", "ollama"); monkeypatch.delenv("DAWA_OFFLINE", raising=False)
    yield Fake
    srv.shutdown()


def test_model_may_only_pick_from_real_candidates_at_the_printed_strength(fake_ollama):
    from dawa_buddy import bill
    assert "furosemide" in bill.candidate_salts([(40.0, "mg")])
    fake_ollama.reply = {"LASIX 40 TAB": {"salt": "furosemide"}}
    assert bill.resolve_with_model("LASIX 40 TAB")[0] == "furosemide"
    fake_ollama.reply = {"LASIX 40 TAB": {"salt": "losartan"}}            # losartan has no 40 mg product -> impossible
    assert bill.resolve_with_model("LASIX 40 TAB") is None
    fake_ollama.reply = {"ZYXOMAB 40 TAB": {"salt": "zyxomab"}}           # invented name
    assert bill.resolve_with_model("ZYXOMAB 40 TAB") is None
    fake_ollama.reply = {"CONCOR 5 TAB": {"salt": "concor"}}              # model echoing the brand back
    assert bill.resolve_with_model("CONCOR 5 TAB") is None


def test_unknown_brand_falls_back_to_model_and_is_marked(fake_ollama):
    from dawa_buddy import bill
    fake_ollama.reply = {"BRANDX 5 TAB": {"salt": "amlodipine"}}
    line = bill.BillLine("x", "BRANDX 5 TAB", 10, 9.0, 90.0, "tab")
    f = bill.audit_line(line)
    assert f.via_model and f.tier == bill.TIER_NEEDS_CONFIRM and f.possible_saving == 0   # a guess never accuses
    g = bill.audit_line(line, confirmed={"brandx 5 tab": "amlodipine"})                  # user confirmed from the strip
    assert not g.via_model and g.tier == bill.TIER_ABOVE_CEILING


def test_hybrid_reader_calls_model_only_for_lines_rules_cannot_finish(fake_ollama):
    from dawa_buddy import reader
    clean = "Tab Dolo 650 mg 1-0-1 x 5 days after food"
    vague = "Take Dolo 650 as directed by the doctor"            # no frequency, no duration: rules cannot finish this
    fake_ollama.reply = {vague: {"medications": [{"name": "Tab Dolo 650", "frequency": "BD", "duration_days": 5, "strength": "650 mg",
                                                  "timing": "bedtime"},
                                                 {"name": "Ghostol", "frequency": "1-0-1", "duration_days": 3}]}}
    rx = reader.read_prescription(clean + "\n" + vague)
    assert len(reader.LAST_MODEL_OUTPUT) == 1                       # only the vague line went to the model
    names = [m.name.lower() for m in rx.medications]
    assert names.count("dolo") == 2 and "ghostol" not in " ".join(names)   # prefix stripped; ungrounded drug dropped
    model_med = rx.medications[-1]
    assert model_med.frequency == "1-0-1"                           # 'BD' normalised to the canonical pattern
    assert model_med.timing is None                                 # 'bedtime' has no evidence in the source line -> dropped


def test_rules_now_parse_phrases_abbreviations_and_multi_drug_sentences():
    from dawa_buddy.reader import read_offline
    meds = read_offline("Take Augmentin 625 twice daily for 1 week. Also Pantop 40 once in the morning on empty stomach for 7 days.").medications
    assert [(m.name, m.frequency, m.duration_days) for m in meds] == [("Augmentin", "1-0-1", 7), ("Pantop", "1-0-0", 7)]
    assert meds[1].timing == "before food"
    m = read_offline("T. Metformin 500mg  b.i.d. p.c. x 1 month").medications[0]
    assert (m.frequency, m.timing, m.duration_days) == ("1-0-1", "after food", 30)


def test_salt_normalisation_accepts_salt_forms_but_not_inventions():
    from dawa_buddy import bill
    assert bill.canon_salt("Bisoprolol Fumarate") == "bisoprolol"
    assert bill.canon_salt("Frusemide") in ("furosemide", None) 
    assert bill.canon_salt("zyxomab") is None


def test_plausible_wrong_salt_still_cannot_create_a_price_accusation(fake_ollama):
    from dawa_buddy import bill
    # A brand in no table, where a model picks a real 40 mg drug. It is only a suggestion.
    fake_ollama.reply = {"ZYXOLEX 40 TAB": {"salt": "telmisartan"}}
    f = bill.audit_line(bill.BillLine("x", "ZYXOLEX 40 TAB", 10, 50.0, 500.0, "tab"))
    assert f.tier == bill.TIER_NEEDS_CONFIRM and f.possible_saving == 0
