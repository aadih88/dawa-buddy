"""Web evidence for a brand the tables cannot settle (Tavily search, optional).

Contract: this returns EVIDENCE, never a verdict. It reads composition strings off pharmacy and drug-information pages,
reports which pages said what, and flags a consensus only when two different sites agree. The user still confirms from
the strip before bill.audit_line will judge a price (the `confirmed` argument). Only the brand text is ever sent out:
no quantities, prices, patient or hospital details.
"""
from __future__ import annotations
import os, re
from collections import Counter
from . import llm
from dataclasses import dataclass, field
from urllib.parse import urlparse
from .brand_table import norm_salt, lookup

BASE_URL = os.environ.get("TAVILY_BASE_URL", "https://api.tavily.com")
TRUSTED = ["1mg.com", "pharmeasy.in", "apollopharmacy.in", "netmeds.com", "truemeds.in", "practo.com", "medindia.net"]
NAME_NOISE = {"contains", "composition", "each", "tablet", "tablets", "capsule", "capsules", "is", "a", "combination", "of",
              "and", "with", "the", "uses", "used", "for", "in", "by", "containing", "salt", "ip"}
COMP = re.compile(r"([A-Za-z][A-Za-z\- ]*?)\s*\(\s*(\d+(?:\.\d+)?)\s*(mg|mcg|g|iu)\s*\)", re.I)
JOINER = re.compile(r"^\s*(\+|,|&|and)\s*$", re.I)       # components group only across an explicit joiner
ACID_FIRST = {"clavulanic", "folic", "ascorbic", "tranexamic", "mefenamic", "valproic", "acetylsalicylic", "salicylic",
              "fusidic", "nalidixic", "zoledronic", "ursodeoxycholic", "ibandronic"}


def available() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY")) and not llm.restricted()


def _salt_name(raw: str) -> str:
    words = [w for w in re.findall(r"[a-z]+", raw.lower()) if w not in NAME_NOISE]
    if len(words) > 1 and words[-2] in ACID_FIRST:
        return norm_salt(" ".join(words[-2:]))
    return norm_salt(words[-1]) if words else ""


def parse_compositions(text: str) -> list[frozenset]:
    """'Aceclofenac (100mg)+ Paracetamol (325mg)' -> [frozenset({('aceclofenac', '100mg'), ('paracetamol', '325mg')})].
    Components group only across + , & or 'and'; stray words ('Contains', brand names) before a component are dropped."""
    groups, cur, last_end = [], [], None
    for m in COMP.finditer(text):
        name = _salt_name(m[1])
        if not name:
            continue
        comp = (name, f"{float(m[2]):g}{m[3].lower()}")
        if cur and JOINER.match(text[last_end:m.start(1)]):
            cur.append(comp)
        else:
            if cur:
                groups.append(frozenset(cur))
            cur = [comp]
        last_end = m.end()
    if cur:
        groups.append(frozenset(cur))
    return groups


@dataclass
class Source:
    url: str
    title: str
    composition: frozenset | None


@dataclass
class Evidence:
    query: str
    sources: list = field(default_factory=list)
    consensus: frozenset | None = None
    best: frozenset | None = None          # the one composition the matching pages state when no second site confirms it (still only a suggestion)
    skipped: int = 0                       # pages dropped because they are a different product (Veltam Plus is not Veltam)
    agrees_with_table: bool | None = None
    note: str = ""


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def show(comp: frozenset) -> str:
    return " + ".join(f"{n} {s}" for n, s in sorted(comp))


_FORM_WORDS = {"tab", "tablet", "tablets", "cap", "caps", "capsule", "capsules", "syp", "syrup", "inj", "injection", "mg", "mcg", "ml", "gm", "g",
               "iu", "ip", "buy", "online", "strip", "of", "po"}
_RELEASE = {"mr", "sr", "xr", "er", "pr", "cr", "od"}      # sites add or drop these freely; they do not make a different brand
_TITLE_CUT = re.compile(r"\b(?:tablets?|capsules?|syrup|injection|suspension|drops|cream|gel|jelly|ointment|online|strip|price|uses?)\b|[:|\u2013\u2014]| - ", re.I)


def _brand_part(title: str) -> str:
    return _TITLE_CUT.split(re.sub(r"(?i)^\s*buy\s+", "", title or ""), maxsplit=1)[0]


_DESC_CUT = re.compile(r"\b(?:tab|tablets?|caps?|capsules?|syp|syrup|inj|injection|gel|jelly|cream|oint|ointment|lotion)\b| - ", re.I)


def desc_brand(desc: str) -> str:
    """'HIFENAC P TAB ACECLOFENAC +PARACETAMOL INTAS' -> 'HIFENAC P ': the brand is the part before the form word; what follows is composition and maker, and no
    pharmacy page title repeats it, so it must not take part in matching or in the search."""
    return _DESC_CUT.split(desc or "", maxsplit=1)[0].strip() or (desc or "")


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if w not in _FORM_WORDS | _RELEASE}


def _numbers(text: str) -> set[float]:
    return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)}


def same_product(title: str, desc: str) -> bool:
    """Is this page about the product on the bill? 'Veltam Plus' is not 'Veltam', 'Concor 5' is not 'Concor T', 'Concor T 2.5/40' is not 'Concor T 5/40'.
    The brand words must be identical (SR/MR ignored) and any strength in the page title must be one the bill also prints."""
    part = _brand_part(title)
    return _words(part) == _words(desc_brand(desc)) and _numbers(part) <= _numbers(desc)


COMPOSITION_BLOCK = re.compile(r"(?is)composition\W{0,12}(.{0,240})")


def composition_text(raw: str) -> str:
    """The 'Composition:' paragraphs of a full page (the short search snippet usually leaves them out)."""
    return " ".join(m.group(1) for m in COMPOSITION_BLOCK.finditer(raw or ""))[:1200]


def gather(results: list[dict], table_hit=None, desc: str | None = None) -> Evidence:
    """Pure part: turn search results into evidence (separate from the network call so it is testable).
    With `desc` (the bill line), pages about a different product are dropped before anyone gets to vote."""
    ev = Evidence(query="")
    by_domain: dict[str, Counter] = {}
    for r in results:
        if desc is not None and not same_product(r.get("title", ""), desc):
            ev.skipped += 1
            continue
        d = _domain(r.get("url", ""))
        groups = parse_compositions(f'{r.get("title", "")}. {r.get("content", "")}. {composition_text(r.get("raw_content", ""))}')
        comp = max(groups, key=len) if groups else None
        ev.sources.append(Source(r.get("url", ""), r.get("title", ""), comp))
        if comp:
            by_domain.setdefault(d, Counter())[comp] += 1
    votes = Counter(c.most_common(1)[0][0] for c in by_domain.values())
    if votes:
        comp, n = votes.most_common(1)[0]
        if n >= 2 and sum(1 for v in votes.values() if v == n) == 1:      # two sites agree and no equally popular rival
            ev.consensus = comp
    if ev.consensus and table_hit and not any("/" in u or u == "%" for _, u in table_hit.strengths):
        want = frozenset((norm_salt(s), f"{v:g}{u}") for s, (v, u) in zip(table_hit.salts.split("+"), table_hit.strengths))
        ev.agrees_with_table = want == ev.consensus
    distinct = {c for counter in by_domain.values() for c in counter}
    if not ev.consensus and len(distinct) == 1:
        ev.best = next(iter(distinct))
    if ev.consensus:
        ev.note = "Two different sites agree. Check this against the composition printed on your strip."
    elif ev.best:
        ev.note = "Only one site states this and no page disagrees. Check it against the composition printed on your strip before using it."
    elif distinct:
        ev.note = "The sites disagree. Read the composition off the strip yourself."
    else:
        ev.note = "No page for this exact product stated its composition. Read the composition off the strip yourself."
    return ev


def lookup_brand(desc: str, form: str = "tablet") -> Evidence | None:
    """Search the web for a brand's composition. Returns None when no Tavily key is configured."""
    if not available():
        return None
    import httpx
    brand = " ".join(re.findall(r"[A-Za-z0-9.]+", desc_brand(desc)))[:80]
    named = _DESC_CUT.search(desc or "")                       # the form word the bill itself uses ("jelly", "syp") searches better than our class name ("topical")
    query = f"{brand} {named.group(0).strip(' -').lower() if named and named.group(0).strip(' -') else form} composition salt strength India"
    r = httpx.post(BASE_URL.rstrip("/") + "/search", timeout=60,
                   headers={"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"},
                   json={"query": query, "search_depth": "basic", "max_results": 8, "include_raw_content": True, "include_domains": TRUSTED})
    r.raise_for_status()
    ev = gather(r.json().get("results", []), lookup(desc, form), desc=desc)
    ev.query = query
    return ev


def lookup_orders(wanted_text: str):
    """NPPA retail-price orders for a combination, found with Tavily on nppa.gov.in only. Returns (rows, source urls) or None without a key.
    The answer is context for the user (other companies' prices), never a verdict; see nppa_orders."""
    if not available():
        return None
    import httpx
    from . import nppa_orders
    wanted = nppa_orders.parse_wanted(wanted_text)
    if not wanted:
        return [], []
    # Phrase the query the way NPPA's own order lists are written; plain wording finds news and blogs instead.
    ip = " ".join(f"{n.title()} IP {v:g} mg" for n, v in wanted)
    plain = " and ".join(n.title() for n, _ in wanted)
    queries = [f"{ip} tablet retail price NPPA order", f"{plain} Tablets retail price 1 Tablet M/s Ltd."]
    rows, urls = [], []
    for q in queries:
        r = httpx.post(BASE_URL.rstrip("/") + "/search", timeout=60, headers={"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"},
                       json={"query": q, "search_depth": "advanced", "max_results": 8, "include_raw_content": True, "include_domains": ["nppa.gov.in"]})
        r.raise_for_status()
        for x in r.json().get("results", []):
            found = nppa_orders.matching(nppa_orders.parse(x.get("raw_content") or x.get("content") or "", x.get("url", "")), wanted)
            if found:
                rows += found
                urls.append(x["url"])
    rows = sorted({(o.company, o.price): o for o in rows}.values(), key=lambda o: o.price)
    return rows, sorted(set(urls))
