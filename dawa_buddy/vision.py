"""Photo -> structured rows. The model only TRANSCRIBES; it never judges prices.

Everything it returns is normalised and then shown to the user in an editable table before any audit runs,
because a misread digit would otherwise become a false accusation.
"""
from __future__ import annotations
import base64, re
from dataclasses import dataclass, field
from . import llm
from .bill import form_of_desc, BillLine, TAB_UNITS, STRIP_UNITS, BOTTLE_UNITS, TUBE_UNITS, VIAL_UNITS

BILL_PROMPT = """You are transcribing a photo of an Indian pharmacy or hospital bill. Reply with ONLY JSON:
{"items":[{"description":str,"qty":number|null,"rate":number|null,"amount":number|null,
"unit":"tab"|"strip"|"bottle"|"tube"|"vial"|null,"pack":number|null,"mrp":number|null,"mrp_per":"unit"|"pack"|null,"unsure":bool}],"total":number|null}
Rules: copy text exactly as printed; one object per bill line; do not calculate or correct any number;
amount is the final value of the line as charged, TAX INCLUDED: the column called Net Amt, Amount, Total, Value or Val In-GST. Never use a column called Taxable or Taxable Value.
qty is the number of units sold; rate is the price per unit as printed (MRP/Unit or Rate or MRP). Some bills print two values in one cell, one above the other (for example qty above discount %, or MRP above net rate): take the top value for qty and the MRP, and ignore the discount %.
mrp_per: "unit" if the printed MRP is for ONE tablet/unit (the column says MRP/Unit, or the bill prints one per-unit price, labelled MRP, which is also the rate); "pack" if it is for a strip, bottle or box; null if unclear. If the only per-unit price column is labelled MRP, set both rate and mrp to it.
description is only the medicine name and strength: leave out manufacturer names, HSN codes, batch numbers and codes like "H/30049061/Aristo".
use null for anything you cannot read or that is not printed; set unit ONLY if the bill states it (e.g. "STRIP", "TAB", "10's", "BOTTLE", "TUBE"); pack is tablets per strip, ml per bottle or gm per tube;
set mrp ONLY if an MRP is printed for that line, copied exactly as printed (it is usually per strip, even when the sale price is per tablet); set unsure true if any digit on that line is hard to read. Include non-medicine lines (rooms, consumables) too.
Ignore patient name, address and phone."""

RX_PROMPT = """You are transcribing a photo of an Indian doctor's prescription. Reply with ONLY JSON:
{"lines":[str]}
One string per medicine, written as the doctor wrote it (name, strength, dose pattern like 1-0-1, days, before/after food).
Copy dose patterns character by character, keeping every digit and every dash exactly as printed (for example 0---1---0 stays 0---1---0, never 0---0).
Do not add, correct or guess anything. Skip lines you cannot read. Ignore patient name and doctor details."""


@dataclass
class Row:
    description: str = ""
    qty: float | None = None
    rate: float | None = None
    amount: float | None = None
    unit: str | None = None          # 'tab' | 'strip' | 'bottle' | 'tube' | None (user must choose)
    pack: float | None = None
    mrp: float | None = None
    unsure: bool = False
    notes: list = field(default_factory=list)


def _num(x):
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        m = re.sub(r"[^\d.]", "", x.replace(",", ""))
        try:
            return float(m) if m else None
        except ValueError:
            return None
    return None


def _name_only(desc: str) -> str:
    """'DOLO 650MG TAB H/30049061/Aristo Pharmaceutica' -> 'DOLO 650MG TAB': drop the schedule/HSN/manufacturer line some bills print under the name."""
    return re.sub(r"\s+[A-Z]{0,2}/?\d{6,8}/.*$|\s+[A-Z]/\d{6,8}\b.*$", "", desc.strip()).strip() or desc.strip()


def clean_bill(data) -> tuple[list[Row], float | None]:
    rows: list[Row] = []
    items = data.get("items", []) if isinstance(data, dict) else []
    for d in items:
        if not isinstance(d, dict) or not str(d.get("description") or "").strip():
            continue
        r = Row(description=_name_only(str(d["description"])), qty=_num(d.get("qty")), rate=_num(d.get("rate")),
                amount=_num(d.get("amount")), mrp=_num(d.get("mrp")), unsure=bool(d.get("unsure")))
        u = str(d.get("unit") or "").lower()
        r.unit = ("tab" if u in TAB_UNITS else "strip" if u in STRIP_UNITS else "bottle" if u in BOTTLE_UNITS else
                  "tube" if u in TUBE_UNITS else "vial" if u in VIAL_UNITS else None)
        if r.unit is None:         # the name itself states the form ("LACTIHEP SYP", "LOX 2% JELLY"): that is the unit a single piece is sold in
            form = form_of_desc(r.description)
            r.unit = "bottle" if form == "liquid" else "tube" if form == "topical" else "vial" if form == "injection" else \
                     "tab" if re.search(r"\b(tab|tablet|cap|capsule)s?\b", r.description, re.I) else None
        if r.unit == "tab" and re.search(r"\binj", r.description, re.I):
            r.unit = "vial"      # 'NOS.' on an injection line means pieces = vials/ampoules, never tablets
        pk = _num(d.get("pack"))
        r.pack = pk if pk and pk > 0 else None
        if r.unit == "tab" and r.mrp and str(d.get("mrp_per") or "").lower() == "unit":
            # The bill prints the MRP per tablet (tax included). The audit divides a printed MRP by tablets per strip, so express it per
            # strip when the strip size is known; otherwise treat the "pack" as one tablet, which gives the same per-tablet MRP.
            r.mrp, r.pack = (r.mrp * r.pack, r.pack) if r.pack else (r.mrp, 1.0)
            r.notes.append("The bill prints the MRP per tablet, tax included.")
        if r.unit is None:
            r.notes.append("Unit not read: choose tab, strip, bottle, tube or vial.")
        if None not in (r.qty, r.rate, r.amount) and abs(r.qty * r.rate - r.amount) > max(1.0, 0.01 * r.amount):
            r.unsure = True
            r.notes.append("qty x rate does not equal amount: check the digits.")
        if r.qty is None or r.rate is None or r.amount is None:
            r.unsure = True
            r.notes.append("Missing number.")
        rows.append(r)
    return rows, _num(data.get("total")) if isinstance(data, dict) else None


def clean_rx(data) -> str:
    lines = data.get("lines", []) if isinstance(data, dict) else []
    return "\n".join(str(l).strip() for l in lines if isinstance(l, str) and l.strip())


def _b64(img: bytes) -> str:
    return base64.b64encode(img).decode()


def prepare(img: bytes, mime: str, max_side: int = 1800) -> tuple[bytes, str]:
    """Phone photos are 4 MB and often rotated by EXIF only: fix orientation and shrink before upload. Falls back to the
    original bytes if Pillow is missing or the file cannot be decoded."""
    try:
        import io
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(img))).convert("RGB")
        im.thumbnail((max_side, max_side))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=88)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return img, mime


def read_bill_photo(img: bytes, mime: str):
    img, mime = prepare(img, mime)
    return clean_bill(llm.chat_vision_json(_b64(img), mime, BILL_PROMPT))


def read_rx_photo(img: bytes, mime: str) -> str:
    img, mime = prepare(img, mime)
    return clean_rx(llm.chat_vision_json(_b64(img), mime, RX_PROMPT))


def rows_to_lines(rows: list[Row]) -> list[BillLine]:
    """Only complete rows become audit lines; incomplete ones are reported back, never guessed."""
    out = []
    for r in rows:
        if r.qty is None or r.rate is None or r.amount is None or not r.description:
            continue
        out.append(BillLine(raw=r.description, desc=r.description, qty=r.qty, rate=r.rate, amount=r.amount,
                            unit=r.unit, pack=r.pack, mrp=r.mrp))
    return out
