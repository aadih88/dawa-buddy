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
{"document":"bill"|"prescription"|"other","items":[{"description":str,"qty":number|null,"rate":number|null,"amount":number|null,
"unit":"tab"|"strip"|"bottle"|"tube"|"vial"|null,"pack":number|null,"mrp":number|null,"mrp_per":"unit"|"pack"|null,"cells":[number],"unsure":bool}],"subtotal":number|null,"discount":number|null,"total":number|null}
Rules: document says what the photo shows: "bill" (a pharmacy or hospital bill or invoice), "prescription" (a doctor's prescription) or "other" (anything else, a person, a place, a report, a blurred or blank page). When it is not a bill, set items to [].
Copy text exactly as printed; one object per bill line; do not calculate or correct any number;
amount is the final value of the line as charged, TAX INCLUDED: the column called Net Amt, Amount, Total, Value or Val In-GST. Never use a column called Taxable or Taxable Value.
qty is the number of units sold; rate is the price per unit as printed (MRP/Unit or Rate or MRP). Some bills print two values in one cell, one above the other (for example qty above discount %, or MRP above net rate): take the top value for qty and the MRP, and ignore the discount %.
mrp_per: "unit" if the printed MRP is for ONE tablet/unit (the column says MRP/Unit, or the bill prints one per-unit price, labelled MRP, which is also the rate); "pack" if it is for a strip, bottle or box; null if unclear. If the only per-unit price column is labelled MRP, set both rate and mrp to it.
cells: EVERY number printed in that line's row (skip batch codes, dates and HSN codes: they are text, not numbers), left to right, one entry per printed value, copied exactly (include tax and discount percentages as plain numbers: write 12 for "GST 12 %", never text inside the list; and list both values of a cell that holds two stacked values, top first). Do not skip any column, and do not work anything out: the numbers are checked afterwards.
A line named Discount, Less Dis, Rebate, Round off, Delivery, Packing or similar is NOT an item: leave it out of the items. discount is the rupee amount taken off the WHOLE bill (a positive number), subtotal is the total before it, and total is the final amount payable (Net Amt). pack is the Pack column ("10TAB" means 10).
description is only the medicine name and strength: leave out manufacturer names, HSN codes, batch numbers and codes like "H/30049061/Aristo".
use null for anything you cannot read or that is not printed; set unit ONLY if the bill states it (e.g. "STRIP", "TAB", "10's", "BOTTLE", "TUBE"); pack is tablets per strip, ml per bottle or gm per tube;
set mrp ONLY if an MRP is printed for that line, copied exactly as printed (it is usually per strip, even when the sale price is per tablet); set unsure true if any digit on that line is hard to read. Include non-medicine lines (rooms, consumables) too.
Ignore patient name, address and phone."""

RX_PROMPT = """You are transcribing a photo of an Indian doctor's prescription. Reply with ONLY JSON:
{"document":"prescription"|"bill"|"other","lines":[str]}
document says what the photo shows: "prescription" (a doctor's prescription), "bill" (a pharmacy or hospital bill or invoice) or "other" (anything else); when it is not a prescription, set lines to [].
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
    mrp_each: bool = False           # the printed MRP is for one tablet, not a strip
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
    return clean_bill_ex(data)[:2]


def clean_bill_ex(data) -> tuple[list[Row], float | None, dict]:
    """(rows, printed total, bill-level facts). The facts are the discount taken off the whole bill and the subtotal before it, when the bill prints them."""
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
            r.mrp_each = True        # kept as printed (per tablet, tax included); the audit does not need a strip size for it
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
    total = _num(data.get("total")) if isinstance(data, dict) else None
    _settle_numbers(rows, [d for d in items if isinstance(d, dict) and str(d.get("description") or "").strip()], total)
    for r in rows:
        settle_mrp(r)
    disc = _num(data.get("discount")) if isinstance(data, dict) else None
    sub_total = _num(data.get("subtotal")) if isinstance(data, dict) else None
    return rows, total, {"discount": disc if disc and disc > 0 else None, "subtotal": sub_total}


# ----------------------------------------------------------------------------- arithmetic: which printed numbers are quantity, price and line value
def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.06, 0.006 * max(a, b))      # a rate printed to 2 decimals times a quantity can be a few paise off the printed value


def consistent(r) -> bool:
    return None not in (r.qty, r.rate, r.amount) and _close(r.qty * r.rate, r.amount)


def row_candidates(cells, hint: tuple = (None, None)) -> list[tuple[float, float, float, int]]:
    """Every (qty, price, line value, penalty) among the numbers printed in a row where qty x price equals the value. Which columns they are does not matter:
    a human also looks for the numbers that multiply out. The penalty prefers whole quantities and no discount, and numbers the reader itself labelled
    quantity or price (`hint`): 6 x 11 and 11 x 6 multiply alike, so the column labels it saw break the tie."""
    vals = [float(v) for v in cells if isinstance(v, (int, float)) and v > 0]
    out = {}
    for i, q in enumerate(vals):
        if q > 999 or not float(q * 2).is_integer():
            continue
        for j, p in enumerate(vals):
            if j == i:
                continue
            for k, a in enumerate(vals):
                if k in (i, j):
                    continue
                pen = (0 if float(q).is_integer() else 1) + (3 if q > 200 else 0) + (2 if p == a and q != 1 else 0) \
                    - (3 if q == hint[0] else 0) - (3 if p == hint[1] else 0)
                if _close(q * p, a):
                    out.setdefault((q, p, a), pen)
                else:               # a discount printed as a percentage: value = qty x price x (1 - d/100)
                    for m, d in enumerate(vals):
                        if m not in (i, j, k) and 0 < d <= 60 and _close(q * p * (1 - d / 100), a):
                            out.setdefault((q, p, a), pen + 3)
    return sorted(((q, p, a, pen) for (q, p, a), pen in out.items()), key=lambda t: (t[3], -t[2]))


def choose_rows(cands: list[list[tuple]], target: float | None) -> list[tuple | None]:
    """One candidate per row. With a printed total, take the combination whose line values add up to it (nearest, then fewest penalties)."""
    import itertools
    lists = [c[:4] for c in cands]
    live = [i for i, l in enumerate(lists) if l]
    space = 1
    for i in live:
        space *= len(lists[i])
    if not live or target is None or space > 60000:
        return [l[0] if l else None for l in lists]
    best, best_key = None, None
    for combo in itertools.product(*[lists[i] for i in live]):
        key = (round(abs(sum(c[2] for c in combo) - target), 2), sum(c[3] for c in combo))
        if best_key is None or key < best_key:
            best, best_key = combo, key
    out = [None] * len(lists)
    for i, c in zip(live, best):
        out[i] = c
    return out


def _with_tax(amount, cells) -> float | None:
    """A number in the row equal to `amount` plus a printed tax percentage (once, or twice for CGST + SGST printed separately), if there is one."""
    if not amount:
        return None
    vals = [v for v in cells if isinstance(v, float) and v > 0]
    top = max(vals, default=0)             # the final value is the biggest number on the row
    if top <= amount * 1.02:
        return None
    by_percent = any(0 < g <= 28 and g == int(g) and _close(amount * (1 + k * g / 100), top) for g in vals for k in (1, 2))
    by_amounts = any(0 < x <= 0.3 * amount and _close(amount + k * x, top) for x in vals for k in (1, 2))      # CGST and SGST printed as amounts
    return top if by_percent or by_amounts else None


def _derive(r, cells) -> None:
    """No numbers multiply out. A bill that prints no rate: the price is the value over the quantity. A bill that prints the price before tax and a taxable
    amount, the tax and a total with tax: the line value is the total (taxable plus its tax), which is what the patient paid."""
    vals = [v for v in cells if isinstance(v, float) and v > 0]
    if r.qty and r.amount and not r.rate:
        r.rate = round(r.amount / r.qty, 4)
        r.unsure, r.notes = False, [n for n in r.notes if n != "Missing number."] + ["Price per unit worked out as the line value divided by the quantity."]
        return
    best = None
    for t in vals:
        for g in vals:
            if 0 < g <= 28 and g == int(g):
                for a in vals:
                    if a > t and any(_close(t * (1 + k * g / 100), a) for k in (1, 2)) and (best is None or a > best):
                        best = a
    if best and r.qty:
        r.amount, r.rate = best, round(best / r.qty, 4)
        r.unsure, r.notes = False, [n for n in r.notes if "does not equal" not in n and n != "Missing number."] + \
            ["The line value is the total with tax; the price per unit is that value divided by the quantity."]


def settle_mrp(r) -> None:
    """A bill's MRP may be per tablet or per strip; say which from the numbers, as a person would. A per-strip MRP is several times the price of one tablet,
    so one that is under twice the price is per tablet. The result is kept as its own fact (mrp_each); no strip size is invented for it."""
    if r.unit != "tab" or not r.mrp or not r.rate:
        return
    if r.mrp < 2 * r.rate and not r.mrp_each:
        r.mrp_each, r.notes = True, r.notes + ["MRP read as per tablet (it is under twice the price of a tablet), tax included."]


def _solve_bad(rows, items, bad, total) -> None:
    """Rows whose quantity x price is not the value: find the printed numbers that do multiply out, and make the lines add up to the printed total."""
    cands = [row_candidates([_num(c) for c in (items[i].get("cells") or [])], (rows[i].qty, rows[i].rate))
             if isinstance(items[i].get("cells"), list) else [] for i in bad]
    kept = sum(r.amount or 0 for i, r in enumerate(rows) if i not in bad)
    picks = choose_rows(cands, None if total is None else total - kept)
    for i, c, it in zip(bad, picks, [items[i] for i in bad]):
        if not c:
            _derive(rows[i], [_num(x) for x in (it.get("cells") or []) if isinstance(it.get("cells"), list)])
        if c:
            rows[i].qty, rows[i].rate, rows[i].amount = c[0], c[1], c[2]
            rows[i].unsure = False
            rows[i].notes = [n for n in rows[i].notes if "does not equal" not in n and n != "Missing number."] + \
                ["Quantity, price and value were picked from the printed numbers so that they multiply out."]



PACK_SIZES = {2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 15, 16, 20, 24, 25, 28, 30, 32, 40, 50, 60, 100}


def _per_pack_rate(r) -> None:
    """A rate printed per STRIP while the quantity counts TABLETS ('6 | 10TAB | CIFRAN CT | rate 191.00 | amount 114.60'): quantity x rate is ten times the amount, because
    six tablets are six tenths of a strip. A person divides by the strip size. The printed rate is then the strip's price (taken as its MRP when none is printed) and
    the price per tablet is the amount over the quantity."""
    if None in (r.qty, r.rate, r.amount) or not r.qty or not r.amount or consistent(r):
        return
    ratio = r.qty * r.rate / r.amount
    k = round(ratio)
    if k in PACK_SIZES and abs(ratio - k) <= 0.01 * k and (not r.pack or r.pack == k):
        r.pack, r.mrp, r.mrp_each, r.unit = float(k), r.mrp or r.rate, False, "tab"
        r.rate = round(r.amount / r.qty, 4)
        r.unsure = False
        r.notes = [n for n in r.notes if "does not equal" not in n and "MRP per tablet" not in n] + \
            [f"The bill prints the rate per strip of {k}; the price per tablet is the amount divided by the quantity."]


def _settle_numbers(rows, items, total) -> None:
    """Keep the model's qty/rate/amount where they multiply out; otherwise find the numbers in the row that do, and make the lines add up to the printed total."""
    for r in rows:
        _per_pack_rate(r)
    bad = [i for i, r in enumerate(rows) if not consistent(r)]
    if bad:
        _solve_bad(rows, items, bad, total)
    for r, it in zip(rows, items):          # a "value" that is only the taxable amount: the same row holds that amount plus its tax, and that is what was paid
        cells = [_num(x) for x in it.get("cells")] if isinstance(it.get("cells"), list) else []
        up = _with_tax(r.amount, cells)
        if up and r.qty:
            r.amount, r.rate = up, round(up / r.qty, 4)
            r.notes = [n for n in r.notes if "does not equal" not in n] + ["The amount before tax was on the bill; the line value with tax is used, as that is what was paid."]


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


class WrongDocument(Exception):
    """The photo is not what the box asked for. kind is what the reader says it is: 'bill', 'prescription' or 'other'."""
    def __init__(self, kind: str, wanted: str):
        super().__init__(f"expected a {wanted}, got {kind}")
        self.kind, self.wanted = kind, wanted


def _document(data) -> str | None:
    kind = str(data.get("document") or "").strip().lower() if isinstance(data, dict) else ""
    return kind if kind in ("bill", "prescription", "other") else None


KIND_PROMPT = """What does this photo show? Answer with exactly one word and nothing else: bill (a pharmacy or hospital bill or invoice), prescription (a doctor's prescription, clinical note or discharge advice listing medicines), or other (anything else)."""


def classify(img_b64: str, mime: str) -> str | None:
    """Used only after a read that came back as prose instead of data: ask what the photo is, in one word. None if that fails too."""
    try:
        text = llm.chat_vision_text_short(img_b64, mime, KIND_PROMPT)
    except Exception:
        return None
    word = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip().lower()
    for kind in ("prescription", "bill", "other"):
        if re.match(rf"\W*{kind}\b", word):
            return kind
    return None


def _read(img: bytes, mime: str, prompt: str, wanted: str):
    """The model's JSON for a photo; a photo of the wrong kind raises WrongDocument, even when the model explained itself in words."""
    img, mime = prepare(img, mime)
    b64 = _b64(img)
    try:
        data = llm.chat_vision_json(b64, mime, prompt)
    except ValueError:
        kind = classify(b64, mime)
        if kind and kind != wanted:
            raise WrongDocument(kind, wanted)
        raise
    kind = _document(data)
    if kind and kind != wanted:
        raise WrongDocument(kind, wanted)
    return data


def read_bill_photo(img: bytes, mime: str):
    return read_bill_photo_ex(img, mime)[:2]


def read_bill_photo_ex(img: bytes, mime: str):
    """(rows, printed total, bill-level facts such as a discount on the whole bill)."""
    return clean_bill_ex(_read(img, mime, BILL_PROMPT, "bill"))


def read_rx_photo(img: bytes, mime: str) -> str:
    return clean_rx(_read(img, mime, RX_PROMPT, "prescription"))


def rows_to_lines(rows: list[Row]) -> list[BillLine]:
    """Only complete rows become audit lines; incomplete ones are reported back, never guessed."""
    out = []
    for r in rows:
        if r.qty is None or r.rate is None or r.amount is None or not r.description:
            continue
        out.append(BillLine(raw=r.description, desc=r.description, qty=r.qty, rate=r.rate, amount=r.amount,
                            unit=r.unit, pack=r.pack, mrp=r.mrp, mrp_each=bool(r.mrp_each)))
    return out
