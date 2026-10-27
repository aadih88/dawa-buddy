"""NPPA retail-price orders found on the web: price CONTEXT for a medicine that has no ceiling of its own.

NPPA fixes the retail price of a new combination (Bisoprolol 5 mg + Telmisartan 40 mg, say) company by company: each order names a
manufacturer and a marketer, and the price binds only that company's product. Another brand of the same combination (Concor T, by a
company with no order) is NOT limited by those prices. So these rows are shown as context, never as a legal limit: "other companies'
versions are price-controlled at X to Y; ask your doctor or pharmacist whether an equivalent is suitable".
Rows are read from the text of official nppa.gov.in order lists; a row is kept only if its composition matches exactly.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from .brand_table import norm_salt

# '... Each film coated tablet contains: Telmisartan IP 40mg Bisoprolol Fumarate IP 5mg 1 Tablet M/s A Ltd. / M/s B Ltd. 12.62'
ROW = re.compile(r"[Cc]ontains?:?\s*(?P<body>[^#]{8,360}?)\s+(?P<unit>1\s+(?:Tablet|Capsule))\s+(?P<co>M/s\s[^#]{4,220}?)\s+(?P<price>\d{1,4}\.\d{2})(?=\s|$)")
PART = re.compile(r"([A-Za-z][A-Za-z ]*?)\s+(?:IP\s+)?(?:(?:eq\.?|equivalent)\s+to\s+[A-Za-z ]+?\s+)?(\d+(?:\.\d+)?)\s*(mg|mcg|g)\b")
STOP = {"each", "film", "coated", "uncoated", "bilayered", "bi", "layered", "tablet", "tablets", "capsule", "ip", "bp", "eq", "equivalent", "to"}


@dataclass
class OrderRow:
    composition: tuple          # sorted ((salt, strength_mg), ...)
    unit: str
    company: str
    price: float                # per unit, excluding GST
    source: str = ""


def _salt(raw: str) -> str:
    return norm_salt(" ".join(w for w in re.findall(r"[A-Za-z]+", raw) if w.lower() not in STOP))


def composition_of(text: str) -> tuple:
    """'Telmisartan IP 40mg Bisoprolol Fumarate IP 5mg' -> (('bisoprolol', 5.0), ('telmisartan', 40.0))."""
    parts = []
    for name, v, u in PART.findall(text):
        s = _salt(name)
        if s:
            parts.append((s, round(float(v) * (1000 if u == "g" else 1), 4)))
    return tuple(sorted(parts))


def parse(text: str, source: str = "") -> list[OrderRow]:
    """Every 'composition | unit | company | price' row in an NPPA order list."""
    text = re.sub(r"\s+", " ", text)
    out, seen = [], set()
    for m in ROW.finditer(text):
        comp = composition_of(m["body"])
        company = re.sub(r"\s+", " ", m["co"]).strip(" /")
        key = (comp, company, m["price"])
        if comp and key not in seen:
            seen.add(key)
            out.append(OrderRow(comp, m["unit"].split()[-1].lower(), company, float(m["price"]), source))
    return out


def parse_wanted(text: str) -> tuple:
    """The user's own wording, 'bisoprolol 5 mg + telmisartan 40 mg', in the same shape as an order row."""
    parts = []
    for chunk in re.split(r"\+|,|\band\b|&", text.lower()):
        m = re.match(r"\s*([a-z][a-z ]*?)\s*\(?\s*(\d+(?:\.\d+)?)\s*(mg|mcg|g)\b", chunk)
        if m and _salt(m[1]):
            parts.append((_salt(m[1]), round(float(m[2]) * (1000 if m[3] == "g" else 1), 4)))
    return tuple(sorted(parts))


def matching(rows: list[OrderRow], wanted: tuple) -> list[OrderRow]:
    return sorted((r for r in rows if r.composition == wanted), key=lambda r: r.price)
