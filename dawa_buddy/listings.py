"""Pack size and MRP from pharmacy websites (via Tavily): evidence for the user, never a legal limit.

What the test on a real bill showed (27 Oct 2026): the product page of PharmEasy, 1mg, Truemeds and Netmeds states the strip size and
the current MRP, and for Concor T and Shelcal the listed MRP equalled the MRP printed on the strip exactly. But sites disagree with each
other (a stale Netmeds listing, a 10-tablet pack next to a 15-tablet one), 1mg itself says "MRP may vary by batch", and Apollo pages
contain other products' prices. So:
  * the product must match by NAME and STRENGTH ('Telma 40' must not become 'Telma H 40' or 'Telma Am 40/5');
  * only the first MRP on a trusted site's page is read, and per tablet, so different pack sizes compare;
  * a pack size is suggested only when two different sites agree;
  * the reference is the highest MRP per tablet that two different sites support within 10%: one odd listing cannot set it and a stale low
    listing cannot lower it, and with no agreement there is no reference at all;
  * results are questions ('ask to see the strip'), never a violation: the legal limit is the MRP on the pack itself.
"""
from __future__ import annotations
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from .brand_table import tokens

DOMAINS = ["1mg.com", "pharmeasy.in", "truemeds.in", "netmeds.com", "apollopharmacy.in", "medplusmart.com"]
TRUST_MRP = {"1mg.com", "pharmeasy.in", "truemeds.in", "netmeds.com"}      # first MRP on the page is the product's own; Apollo's pages list other products
SITE_WORDS = {"buy", "online", "uses", "side", "effects", "price", "dosage", "more", "view", "best", "india", "strip", "substitute", "substitutes",
              "composition", "review", "reviews", "order", "tablet", "tablets", "tab", "capsule", "capsules", "mr", "sr", "xr", "of", "in", "the", "and", "mg", "ml",
              "pharmeasy", "netmeds", "truemeds", "apollo", "pharmacy", "medplus", "tata", "faqs", "how", "to", "use", "work", "works", "s"}
# Each source gets only the patterns that are safe for it: a title may end in the pack ('Tablet 15', "10's"), a URL only says 'strip-of-N'
# (its other digits are product ids), page text states it in words. The product's own MRP is the FIRST one on a trusted page, but it sits deep
# in the text, after the site's menus, so the whole text is read, not a prefix.
PACK_IN_TITLE = [re.compile(p, re.I) for p in (r"\bTablet\s+(\d{1,3})\b", r"\bCapsule\s+(\d{1,3})\b", r"\b(\d{1,3})\s*'\s*s\b", r"strip\s+of\s+(\d+)\s*(?:tablets?|capsules?)")]
PACK_IN_URL = [re.compile(r"strip[- ]of[- ](\d+)", re.I)]
PACK_IN_TEXT = [re.compile(p, re.I) for p in (r"(\d+)\s*Tablet\(s\)\s+in\s+Strip", r"(\d+)\s*(?:tablets?|capsules?)\s+in\s+(?:a\s+)?strip",
                                              r"strip\s+of\s+(\d+)\s*(?:tablets?|capsules?)", r"(\d{1,3})\s*tablets?(?:\s+mr)?\s+MRP may vary")]
MRP_FIRST = re.compile(r"\bMRP\s*(?:~~)?\s*₹\s*([\d,]+(?:\.\d+)?)", re.I)


@dataclass
class Page:
    domain: str
    url: str
    title: str
    pack: int | None
    mrp: float | None            # per pack, as the page states it

    @property
    def per_tablet(self) -> float | None:
        return self.mrp / self.pack if self.mrp and self.pack else None


@dataclass
class Listing:
    query: str
    pages: list = field(default_factory=list)
    pack: int | None = None                       # agreed by at least two different sites
    pack_sites: list = field(default_factory=list)
    per_tablet_max: float | None = None           # reference MRP per tablet: the highest value two different sites agree on (within 10%)
    mrp_sites: list = field(default_factory=list)  # (domain, mrp per pack, pack)


def title_matches(want: list[str], title: str) -> bool:
    """The page is for THIS product: its name and strength appear together in the title, and no variant letter follows ('Telma H 40' is not 'Telma 40')."""
    t = tokens(title)
    n = len(want)
    for i in range(len(t) - n + 1):
        if t[i:i + n] == want:
            before_ok = all(x in SITE_WORDS for x in t[:i])
            nxt = t[i + n] if i + n < len(t) else ""
            return before_ok and (not nxt or nxt in SITE_WORDS or nxt[0].isdigit())
    return False


def domain_of(url: str) -> str:
    host = url.split("/")[2].lower() if "//" in url else url.lower()
    return re.sub(r"^www\.", "", host)


def parse_page(url: str, title: str, text: str) -> Page:
    dom = domain_of(url)
    pack = None
    for src, pats in ((title, PACK_IN_TITLE), (url, PACK_IN_URL), (text, PACK_IN_TEXT)):
        for pat in pats:
            m = pat.search(src)
            if m and 2 <= int(m[1]) <= 500:
                pack = int(m[1])
                break
        if pack:
            break
    mrp = None
    if dom in TRUST_MRP:
        m = MRP_FIRST.search(text)
        mrp = float(m[1].replace(",", "")) if m else None
    return Page(dom, url, title, pack, mrp)


def combine(query: str, pages: list[Page]) -> Listing:
    out = Listing(query, pages)
    by_pack: dict[int, set] = {}
    for p in pages:
        if p.pack:
            by_pack.setdefault(p.pack, set()).add(p.domain)
    agreed = [(len(d), n) for n, d in by_pack.items() if len(d) >= 2]
    if agreed:
        top = max(agreed)
        out.pack = top[1]
        out.pack_sites = sorted(by_pack[out.pack])
    prices = [p for p in pages if p.per_tablet]
    ref = agreed_reference(prices)
    if ref:
        out.per_tablet_max = ref
        out.mrp_sites = sorted({(p.domain, p.mrp, p.pack) for p in prices if ref / 1.10 <= p.per_tablet <= ref}, key=lambda x: -x[1] / x[2])
    return out


def agreed_reference(prices: list, band: float = 1.10) -> float | None:
    """The highest MRP per tablet that at least TWO different sites support within 10% (the most NPPA lets a price rise in a year).
    One odd listing (a different pack, a bundle, a stale page) cannot set the reference; with no agreement there is none."""
    for cand in sorted({p.per_tablet for p in prices}, reverse=True):
        if len({p.domain for p in prices if cand / band <= p.per_tablet <= cand}) >= 2:
            return cand
    return None


def search(desc: str, search_fn=None) -> Listing | None:
    """Look up one bill line on the pharmacy sites. Returns None without a Tavily key. Only the brand and strength are sent."""
    want = [t for t in tokens(desc) if t not in SITE_WORDS or t[0].isdigit()]
    if not want:
        return None
    query = " ".join(want)
    if search_fn is None:
        if not os.environ.get("TAVILY_API_KEY"):
            return None
        search_fn = _tavily
    pages = []
    for x in search_fn(f"{query} tablet price MRP strip of tablets"):
        if title_matches(want, x["title"]):
            pages.append(parse_page(x["url"], x["title"], x.get("raw_content") or x.get("content") or ""))
    return combine(query, pages)


def _tavily(q: str) -> list[dict]:
    import httpx
    from .webcheck import BASE_URL
    r = httpx.post(BASE_URL.rstrip("/") + "/search", timeout=60, headers={"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"},
                   json={"query": q, "search_depth": "advanced", "max_results": 8, "include_domains": DOMAINS, "include_raw_content": True})
    r.raise_for_status()
    return r.json().get("results", [])


def judge(listing: Listing, rate_per_tablet: float | None, printed_per_tablet: float | None) -> dict | None:
    """What the listings say about this bill line, as a QUESTION. printed_per_tablet is the MRP printed on the bill per tablet (if any).
    The reference is the highest listed MRP per tablet: a stale low listing can never create a false alarm."""
    ref = listing.per_tablet_max
    if not ref:
        return None
    if printed_per_tablet is not None:
        if printed_per_tablet > ref * 1.10:          # NPPA allows a non-scheduled MRP to rise at most 10% a year
            return {"kind": "printed_above_listings", "ref": ref, "value": printed_per_tablet}
        return {"kind": "agrees", "ref": ref, "value": printed_per_tablet}
    if rate_per_tablet is not None and rate_per_tablet > ref * 1.01:
        return {"kind": "charged_above_listed_mrp", "ref": ref, "value": rate_per_tablet}
    return {"kind": "within_listed_mrp", "ref": ref, "value": rate_per_tablet} if rate_per_tablet is not None else None
