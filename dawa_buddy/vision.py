"""Photo -> structured rows. The model only TRANSCRIBES; it never judges prices.

Everything it returns is normalised and then shown to the user in an editable table before any audit runs,
because a misread digit would otherwise become a false accusation.
"""
from __future__ import annotations
import base64, re
from dataclasses import dataclass, field
from . import llm
from .bill import BillLine, TAB_UNITS, STRIP_UNITS, BOTTLE_UNITS, TUBE_UNITS, VIAL_UNITS

BILL_PROMPT = """You are transcribing a photo of an Indian pharmacy or hospital bill. Reply with ONLY JSON:
{"items":[{"description":str,"qty":number|null,"rate":number|null,"amount":number|null,
"unit":"tab"|"strip"|"bottle"|"tube"|"vial"|null,"pack":number|null,"mrp":number|null,"unsure":bool}],"total":number|null}
Rules: copy text exactly as printed; one object per bill line; do not calculate or correct any number;
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


def clean_bill(data) -> tuple[list[Row], float | None]:
    rows: list[Row] = []
    items = data.get("items", []) if isinstance(data, dict) else []
    for d in items:
        if not isinstance(d, dict) or not str(d.get("description") or "").strip():
            continue
        r = Row(description=str(d["description"]).strip(), qty=_num(d.get("qty")), rate=_num(d.get("rate")),
                amount=_num(d.get("amount")), mrp=_num(d.get("mrp")), unsure=bool(d.get("unsure")))
        u = str(d.get("unit") or "").lower()
        r.unit = ("tab" if u in TAB_UNITS else "strip" if u in STRIP_UNITS else "bottle" if u in BOTTLE_UNITS else
                  "tube" if u in TUBE_UNITS else "vial" if u in VIAL_UNITS else None)
        if r.unit == "tab" and re.search(r"\binj", r.description, re.I):
            r.unit = "vial"      # 'NOS.' on an injection line means pieces = vials/ampoules, never tablets
        pk = _num(d.get("pack"))
        r.pack = pk if pk and pk > 0 else None
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
