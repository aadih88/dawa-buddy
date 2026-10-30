from dawa_buddy import vision, llm, bill as b


def test_vision_output_is_normalised_and_never_invents_a_unit():
    data = {"items": [{"description": "TELMA 40", "qty": "3", "rate": "124.00", "amount": "372.00", "unit": None, "pack": None},
                      {"description": "ATORVA 10", "qty": 6, "rate": 105, "amount": 900, "unit": "strip", "pack": 10},
                      {"description": ""}], "total": "1,272"}
    rows, total = vision.clean_bill(data)
    assert len(rows) == 2 and total == 1272.0
    assert rows[0].unit is None and any("Unit" in n for n in rows[0].notes)
    assert rows[1].unsure and any("amount" in n for n in rows[1].notes)       # 6x105 != 900


def test_incomplete_rows_are_not_audited_and_missing_unit_is_flagged_not_guessed():
    rows, _ = vision.clean_bill({"items": [{"description": "TELMA 40", "qty": 3, "rate": 124, "amount": 372},
                                           {"description": "X", "qty": None, "rate": 5, "amount": 5}]})
    lines = vision.rows_to_lines(rows)
    assert len(lines) == 1 and b.audit_line(lines[0]).tier == b.TIER_UNIT_UNCLEAR


def test_photo_path_uses_the_vision_client(monkeypatch):
    monkeypatch.setattr(llm, "chat_vision_json", lambda img, mime, prompt: {"lines": ["Tab Telma 40 1-0-0 x 30 days", "", 5]})
    assert vision.read_rx_photo(b"x", "image/png") == "Tab Telma 40 1-0-0 x 30 days"


def test_nebius_defaults_and_reasoning_off_with_fallback(monkeypatch):
    calls = []

    class Comp:
        def create(self, **kw):
            calls.append(kw)
            if "extra_body" in kw:
                raise RuntimeError("Unknown field reasoning_effort")
            class M: content = '{"lines": ["x"]}'
            class C: message = M()
            class R: choices = [C()]
            return R()

    class Cl:
        class chat: completions = Comp()

    monkeypatch.delenv("DAWA_OFFLINE", raising=False); monkeypatch.setenv("DAWA_PROVIDER", "nebius"); monkeypatch.setenv("NEBIUS_API_KEY", "k")
    monkeypatch.setattr(llm, "VISION_MODEL", ""); monkeypatch.setattr(llm, "_client", lambda: Cl())
    assert llm.vision_model() == "nvidia/Nemotron-3.5-Super-VL" and llm.vision_available()
    assert llm.chat_vision_json("aa", "image/png", "p") == {"lines": ["x"]}
    assert calls[0]["extra_body"] == {"reasoning_effort": "none"} and "extra_body" not in calls[1]
    assert calls[1]["model"] == "nvidia/Nemotron-3.5-Super-VL"


# ---- the wrong photo in a box: a clear answer, never a parse error
import pytest
from dawa_buddy import llm


def _reader_says(monkeypatch, answer):
    monkeypatch.setattr(llm, "chat_vision_json", lambda *a, **k: answer)


def test_a_prescription_in_the_bill_box_is_named_as_one(monkeypatch):
    _reader_says(monkeypatch, {"document": "prescription", "items": []})
    with pytest.raises(vision.WrongDocument) as e:
        vision.read_bill_photo_ex(b"not an image", "image/jpeg")
    assert (e.value.kind, e.value.wanted) == ("prescription", "bill")


def test_a_random_photo_in_either_box_is_named_as_other(monkeypatch):
    _reader_says(monkeypatch, {"document": "other", "items": [], "lines": []})
    with pytest.raises(vision.WrongDocument) as e:
        vision.read_bill_photo_ex(b"x", "image/jpeg")
    assert e.value.kind == "other"
    with pytest.raises(vision.WrongDocument) as e:
        vision.read_rx_photo(b"x", "image/jpeg")
    assert (e.value.kind, e.value.wanted) == ("other", "prescription")


def test_a_bill_in_the_prescription_box_is_named_as_one(monkeypatch):
    _reader_says(monkeypatch, {"document": "bill", "lines": []})
    with pytest.raises(vision.WrongDocument) as e:
        vision.read_rx_photo(b"x", "image/jpeg")
    assert (e.value.kind, e.value.wanted) == ("bill", "prescription")


def test_a_reply_without_the_document_field_still_reads_as_before(monkeypatch):
    _reader_says(monkeypatch, {"items": [{"description": "DOLO 650 TAB", "qty": 10, "rate": 2.0, "amount": 20.0}]})
    rows, _, _ = vision.read_bill_photo_ex(b"x", "image/jpeg")
    assert rows and rows[0].description.startswith("DOLO")
    _reader_says(monkeypatch, {"lines": ["Dolo 650 1-0-1 5 days"]})
    assert "Dolo" in vision.read_rx_photo(b"x", "image/jpeg")


def test_a_reply_in_words_is_classified_so_the_user_hears_what_the_photo_is(monkeypatch):
    def prose(*a, **k):
        raise ValueError("the model explained instead of answering in JSON")
    monkeypatch.setattr(llm, "chat_vision_json", prose)
    monkeypatch.setattr(llm, "chat_vision_text_short", lambda *a, **k: "Prescription.")
    with pytest.raises(vision.WrongDocument) as e:
        vision.read_bill_photo_ex(b"x", "image/jpeg")
    assert e.value.kind == "prescription"
    monkeypatch.setattr(llm, "chat_vision_text_short", lambda *a, **k: "bill")           # a bill that simply could not be read stays a read failure
    with pytest.raises(ValueError):
        vision.read_bill_photo_ex(b"x", "image/jpeg")
