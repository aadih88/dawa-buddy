"""Bill audit core: parse bill lines -> resolve to salt/strength/form -> compare per-unit price with
(1) the NPPA legal ceiling and (2) the Jan Aushadhi generic benchmark -> assign an evidence tier.

Principles: never accuse. Only 'above ceiling' (with a GST allowance) is a possible violation; everything
else is a question to ask. Unknown units or unresolved items are reported as such, never guessed.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional
from . import benchmarks as ja, ceilings as nppa, injectables, liquids, llm
from .brand_table import NOISE, SALT_ALIAS, SALT_SUFFIX, lookup as brand_lookup
from .knowledge import BRANDS

GST_ALLOWANCE = 1.12          # ceilings exclude GST; allow the highest medicine slab before flagging
GENERIC_GAP_RATIO = 2.0       # flag 'ask for generic' when unit price >= 2x the JA benchmark
GENERIC_MENTION_RATIO = 1.5   # below the flag, but a generic at under two-thirds of the price is still worth saying out loud
# Switching these needs the prescriber's say-so, so we never nudge a swap.
DOCTOR_ONLY = {"warfarin", "thyroxine", "phenytoin", "carbamazepine", "valproate", "levetiracetam",
               "tacrolimus", "cyclosporine", "digoxin", "lithium", "clozapine"}
MCG_DRUGS = {"thyroxine", "digoxin", "cyanocobalamin"}

TIER_ABOVE_CEILING = "above_ceiling"
TIER_GENERIC_GAP = "generic_gap"
TIER_OK = "within_benchmarks"
TIER_NO_BENCHMARK = "no_benchmark"
TIER_UNIT_UNCLEAR = "unit_unclear"
TIER_NOT_MEDICINE = "not_covered"
TIER_DOCTOR_ONLY = "ask_doctor_first"
TIER_NEEDS_CONFIRM = "needs_confirmation"
TIER_SUPPLEMENT = "supplement_no_ceiling"
TIER_ABOVE_MRP = "above_mrp"
MRP_TOLERANCE = 1.005         # absorb rounding in per-strip -> per-tablet arithmetic, nothing more


@dataclass
class BillLine:
    raw: str
    desc: str
    qty: float
    rate: float
    amount: float
    unit: Optional[str] = None      # 'tab' or 'strip' (explicit: bills are ambiguous and a wrong guess would accuse falsely)
    pack: Optional[float] = None    # tablets per strip, ml per bottle or gm per tube
    mrp: Optional[float] = None     # MRP as the bill prints it: per strip / bottle / tube, or per tablet when mrp_each
    mrp_each: bool = False          # the printed MRP is for ONE tablet (the column says MRP/Unit), not for a strip
    list_rate: Optional[float] = None   # the rate before a discount on the whole bill was spread over the lines (None when there was none)
    list_amount: Optional[float] = None # the amount as printed on the bill, before that

    @property
    def shown_amount(self) -> float:
        """The line total as the patient sees it on the paper."""
        return self.list_amount if self.list_amount is not None else self.amount


@dataclass
class Finding:
    line: BillLine
    tier: str
    ingredients: str = ""
    strength: str = ""
    unit_price: Optional[float] = None
    ceiling: Optional[float] = None
    generic_unit: Optional[float] = None
    generic_name: str = ""
    possible_saving: float = 0.0
    note: str = ""
    via_model: bool = False
    mrp_pct: Optional[float] = None    # charged rate as % of the printed MRP, when checkable
    basis: str = ""                    # what unit_price is per: tablet, ml, gm, vial or bag (for display)
    mrp_unit: Optional[float] = None   # the printed MRP on the same basis as the billed rate, when checkable
    source: str = ""                   # where the identification came from, in words for the reader ("the public brand table and your bill")


NON_MEDICINE = re.compile(r"\b(syringe|cannula|iv set|drip set|gloves?|mask|gown|catheter|stent|implant|"
                          r"bed|room|nursing|consult|visit|ot charge|theatre|surgeon|anaesth|monitor|ventilator|"
                          r"scan|x-?ray|lab|test|blood|oxygen|dressing|bandage|gauze|cotton|plaster|diaper|"
                          r"disposable|consumable|procedure|registration|admission)\b", re.I)
# Vitamins, minerals, protein and similar are food/nutraceutical products: no NPPA ceiling by design. Only applied when
# no price benchmark matched, so an item that really is in a ceiling list is still judged.
SUPPLEMENT = re.compile(r"\b(vitamins?|multi-?vit\w*|b[- ]?complex|zincovit|becosules?|neurobion|shelcal|supradyn|revital|"
                        r"protein|whey|omega[- ]?3|fish oil|probiotics?|collagen|biotin|multimineral|nutri\w*|"
                        r"health drink|energy drink|immunity)\b", re.I)
LINE_RE = re.compile(r"^(?P<desc>.+?)\s*[|,\t ]\s*(?P<qty>\d+(?:\.\d+)?)\s*[|,\t ]\s*(?P<rate>\d+(?:\.\d+)?)"
                     r"\s*[|,\t ]\s*(?P<amt>\d+(?:\.\d+)?)\s*$")


TAB_UNITS = {"tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules", "nos", "no", "unit", "units", "piece", "pcs"}
STRIP_UNITS = {"strip", "strips", "pack", "packs", "blister", "sheet"}
BOTTLE_UNITS = {"bottle", "bottles", "btl", "ml"}      # content in ml
TUBE_UNITS = {"tube", "tubes", "jar", "gm", "g"}       # content in gm
VIAL_UNITS = {"vial", "vials", "amp", "amps", "ampoule", "ampoules"}   # one container; pack = ml it holds (optional)
EACH_UNITS = {"each", "ea"}                             # one piece of a consumable or device: the printed MRP is per piece, no pack size needed


def _num(x: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", x.strip()))


def parse_bill_ex(text: str):
    """Returns (lines, rejected). Format: description | qty | rate | amount [| unit [| pack [| mrp]]]. '#' starts a comment."""
    lines, rejects = [], []
    for ln in [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]:
        if "|" in ln:
            f = [x.strip() for x in ln.split("|")]
            if len(f) >= 4 and all(_num(x) for x in f[1:4]):
                unit = f[4].lower() if len(f) > 4 and f[4] else None
                pack = float(f[5]) if len(f) > 5 and _num(f[5]) else None
                mrp = float(f[6]) if len(f) > 6 and _num(f[6]) else None
                lines.append(BillLine(ln, f[0], float(f[1]), float(f[2]), float(f[3]), unit, pack, mrp))
            elif not re.match(r"(?i)^(item|description|particulars)\b", f[0]):
                rejects.append(ln)
            continue
        m = LINE_RE.match(ln)
        if m:
            lines.append(BillLine(ln, m["desc"].strip(" |,"), float(m["qty"]), float(m["rate"]), float(m["amt"])))
        else:
            rejects.append(ln)
    return lines, rejects


def parse_bill(text: str) -> list[BillLine]:
    return parse_bill_ex(text)[0]


_VOCAB: set | None = None


def _vocab() -> set:
    global _VOCAB
    if _VOCAB is None:
        _VOCAB = set()
        for r in ja.index():
            if len(r.ingredients) == 1:
                _VOCAB |= set(r.ingredients)
        for c in nppa.index():
            if len(c.ingredients) == 1:
                _VOCAB |= set(c.ingredients)
    return _VOCAB


def composition_stated(desc: str, generic: str) -> bool:
    """Does the bill line itself print the ingredients the brand table gives ('... TAB ACECLOFENAC +PARACETAMOL INTAS')? Two independent sources then agree, and the
    table's two-ingredient limit cannot be hiding a third: a bill that lists a composition lists all of it. Matching is by the first five letters, so a
    misspelling ('CLAVUNIC') still counts. Only the text after the form word is looked at: a brand name that merely contains 'parac' proves nothing."""
    m = re.search(r"\b(?:tab|tablets?|caps?|capsules?|syp|syrup|inj|injection)\b(.*)$", desc, re.I)
    stated = re.findall(r"[a-z]+", (m.group(1) if m else "").lower())
    return bool(stated) and all(any(w.startswith(part[:5]) for w in stated) for part in (x.strip() for x in generic.split("+")))


def form_of_desc(desc: str) -> str:
    """The dosage form the bill line names: capsule, injection, liquid (syrup, drops...), topical (gel, jelly, cream...) or tablet. A form the
    name does not state is a tablet, as before. 'LOX 2% JELLY' must be looked up as a topical, not a tablet, or its composition is never found."""
    low = desc.lower()
    return ("capsule" if re.search(r"\bcap(s|sule)?\b", low) else "injection" if re.search(r"\binj", low) else
            "liquid" if re.search(r"\b(syp|syrup|susp|suspension|drops?|solution|sol|elixir|expectorant)\b", low) else
            "topical" if re.search(r"\b(gel|jelly|cream|oint|ointment|lotion)\b", low) else "tablet")


def resolve(desc: str, forced_salt: str | None = None):
    """Return (ingredients, strengths, form, modified_release, pack_in_desc, billed_per, source) or None."""
    low = desc.lower()
    tokens = re.findall(r"[a-z]+", low)
    form = form_of_desc(desc)
    mr = bool(re.search(r"\b(sr|xr|cr|er|mr|retard|prolonged|modified)\b", low))
    per = "strip" if "strip" in low else "tab" if re.search(r"\b(tab|tablet|cap|capsule)s?\b", low) else None
    hit = None if forced_salt else brand_lookup(desc, form)
    if not hit and not forced_salt:     # "HIFENAC P TAB ACECLOFENAC +PARACETAMOL INTAS": the brand is the part up to the form word; the rest is composition and maker
        m = re.match(r"(.+?\b(?:tab|tablet|cap|capsule|syp|syrup|inj|injection|gel|jelly|cream|oint|ointment|lotion)s?)\b\W*\S", desc, re.I)
        hit = brand_lookup(m.group(1), form) if m else None
    if hit:     # whole-brand match: salts AND strengths come from the table, not from a number guessed out of the text
        return hit.salts, hit.strengths, form, hit.modified_release or mr, None, per, "brand_table?mr" if hit.mr_guess else "brand_table"
    brand_tok = next((t for t in tokens if t in BRANDS), None)
    # 'GLYCOMET GP 1' is not Glycomet and 'PAN D' is not Pan: leftover letters mean a different product, so don't guess.
    if brand_tok and BRANDS[brand_tok] != brand_tok and any(t != brand_tok and t not in NOISE and t not in SALT_SUFFIX for t in tokens):
        brand_tok = None
    if brand_tok and not forced_salt and re.search(r"[A-Za-z]\s*[+&]\s*[A-Za-z]", desc):
        brand_tok = None                  # "ACECLOFENAC + PARACETAMOL": a combination named in words is not the single salt that happens to match
    generic = forced_salt or (BRANDS[brand_tok] if brand_tok else None)
    by_name = generic is None      # a plain generic name printed on the bill is used below
    if not generic:   # accept a plain generic name that exists in either benchmark list
        named = list(dict.fromkeys(t for t in tokens if len(t) > 4 and t in _vocab()))
        if len(named) > 1 or (named and re.search(r"[A-Za-z]\s*[+&]\s*[A-Za-z]", desc)):
            return None       # the name lists several ingredients ("A + B"): one of them alone would be a different, wrongly priced product
        generic = named[0] if named else None
    if not generic:
        return None
    st = re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g)?\b", low)
    strengths = []
    if st and "+" not in generic:
        unit = st.group(2) or ("mcg" if generic in MCG_DRUGS else "mg")
        strengths = [(float(st.group(1)), unit)]
    pack = re.search(r"(\d+)\s*(?:'s|s\b|tabs?|caps?|tablets?)", low)
    return (generic, strengths, form, mr, int(pack.group(1)) if pack and strengths and int(pack.group(1)) != strengths[0][0] else None,
            per, "generic" if (by_name or forced_salt) else "curated")


MODEL_SYSTEM = """You identify which generic medicine an Indian brand name is sold as.
You get a bill item and a CLOSED list of candidate generics that exist at that strength.
Reply with ONLY JSON: {"salt": "<one name copied exactly from the list>" or null}.
If you do not clearly know the brand, answer null. Never guess and never invent a name."""

FRAGMENTS = {"chloride", "sulphate", "sulfate", "phosphate", "oxide", "acid", "bicarbonate", "nitrate", "carbonate"}
LAST_RAW: list = []        # diagnostics: (desc, raw model JSON, number of candidates)


def canon_salt(s: str) -> str | None:
    """'Bisoprolol Fumarate' -> 'bisoprolol'; accept only if the result is in our price lists."""
    words = [SALT_ALIAS.get(w, w) for w in re.findall(r"[a-z]+", (s or "").lower()) if w not in SALT_SUFFIX]
    for cand in (" ".join(words), words[0] if words else ""):
        if cand and cand in _vocab() and cand not in FRAGMENTS:
            return cand
    return None


def desc_strengths(desc: str) -> list[tuple[float, str]]:
    """Strength comes from the bill text, never from the model."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g)?\b", desc.lower())
    return [(float(m.group(1)), m.group(2) or "mg")] if m else []


def candidate_salts(strengths: list[tuple[float, str]]) -> list[str]:
    """Single-ingredient generics that have a real product at exactly this strength in either price list."""
    if not strengths:
        return []
    want = tuple(strengths)
    names = set()
    for rec in list(ja.index()) + list(nppa.index()):
        if len(rec.ingredients) == 1 and rec.strengths == want:
            n = next(iter(rec.ingredients))
            if n not in FRAGMENTS:
                names.add(n)
    return sorted(names)


def resolve_with_model(desc: str):
    """Constrained choice: the model may only pick from real candidates at the strength printed on the bill.
    Anything else (free text, invented names, plausible-but-wrong salts at an impossible strength) is discarded."""
    try:
        strengths = desc_strengths(desc)
        cands = candidate_salts(strengths)
        if not cands or len(cands) > 250:
            return None
        d = llm.chat_json(MODEL_SYSTEM, f"Bill item: {desc}\nCandidates: {', '.join(cands)}")
        LAST_RAW.append((desc, d, len(cands)))
        salt = (d.get("salt") or "").strip().lower() if isinstance(d, dict) else ""
        if salt not in cands:
            return None
        low = desc.lower()
        per = "strip" if "strip" in low else "tab" if re.search(r"\b(tab|tablet|cap|capsule)s?\b", low) else None
        return salt, strengths, "tablet", False, None, per
    except Exception:
        return None


def audit_line(line: BillLine, confirmed: dict | None = None) -> Finding:
    """Price tiers + regulatory status + the printed-MRP check, which holds for every product, controlled or not."""
    if SUPPLEMENT.search(line.desc) and not NON_MEDICINE.search(line.desc) and resolve(line.desc) is None:
        f = Finding(line, TIER_SUPPLEMENT)    # skip the model: nothing to resolve, and no ceiling can exist
    else:
        f = _audit_core(line, confirmed)
        if f.tier in (TIER_NO_BENCHMARK, TIER_UNIT_UNCLEAR, TIER_NEEDS_CONFIRM) and SUPPLEMENT.search(line.desc):
            f = Finding(line, TIER_SUPPLEMENT)
    if f.tier == TIER_SUPPLEMENT:
        f.note = ("Vitamins, minerals and similar supplements are not price-controlled (no NPPA ceiling exists), so we cannot "
                  "say this is overpriced. The one limit that still applies is the MRP printed on the pack.")
    mrp_unit = _mrp_on_billed_basis(line)
    f.mrp_unit = mrp_unit
    if mrp_unit is not None and line.rate > mrp_unit * MRP_TOLERANCE:
        f.tier, f.possible_saving = TIER_ABOVE_MRP, round((line.rate - mrp_unit) * line.qty, 2)
        f.note = (f"Charged {line.rate:.2f} but the MRP printed on your bill works out to {mrp_unit:.2f} on the same basis. Selling "
                  "above the printed MRP is not allowed for any product. Ask for the pack and the corrected bill.")
    elif mrp_unit is not None:
        pct = 100 * line.rate / mrp_unit
        if f.tier in (TIER_SUPPLEMENT, TIER_NO_BENCHMARK, TIER_NOT_MEDICINE):
            f.note += f" Charged {line.rate:.2f} is within the MRP on your bill ({pct:.0f}% of {mrp_unit:.2f}); that MRP is the seller's own figure."
        f.mrp_pct = round(pct, 1)
    elif line.mrp:
        f.note += " MRP given but tablets per strip are missing, so the MRP check could not be made."
    f.source = source_label(line, confirmed, f)
    return f


def source_label(line: BillLine, confirmed: dict | None, f: Finding) -> str:
    """Where the ingredient came from, so a patient can judge how far to trust it. Empty when nothing was identified."""
    if not f.ingredients:
        return ""
    if (confirmed or {}).get(line.desc.lower()):
        return "you confirmed it from your strip"
    if f.via_model:
        return "an AI suggestion that you have not confirmed"
    r = resolve(line.desc)
    src = r[6] if r else ""
    if src.startswith("brand_table"):
        return "the public brand table" + (" and the composition printed on your bill" if composition_stated(line.desc, f.ingredients) else "")
    return {"curated": "our checked list of common brands", "generic": "the generic name printed on your bill"}.get(src, "")


def line_unit_price(line: BillLine) -> Optional[float]:
    """Price per tablet/capsule as billed, when the unit makes it certain (per tablet, or per strip with the pack size)."""
    u = (line.unit or "").lower()
    if u in TAB_UNITS:
        return line.rate
    if u in STRIP_UNITS and line.pack:
        return line.rate / line.pack
    return None


def per_tablet_view(unit, rate, mrp, mrp_each, pack) -> tuple[Optional[float], Optional[float]]:
    """(price paid per tablet, MRP per tablet) from what the card says. Either is None while the strip size it needs is missing. The card shows these live,
    so choosing 'per tablet' or 'per strip' visibly changes what the numbers mean."""
    u = (unit or "").lower()
    paid = rate if u in TAB_UNITS else (rate / pack if u in STRIP_UNITS and pack else None)
    per_tab_mrp = None if not mrp else (mrp if mrp_each else (mrp / pack if pack else None))
    return paid, per_tab_mrp


def mrp_per_tablet(line: BillLine) -> Optional[float]:
    return per_tablet_view(line.unit, line.rate, line.mrp, line.mrp_each, line.pack)[1]


def suggest_pack(desc: str) -> Optional[int]:
    """Tablets per strip the brand table lists for this brand: only a SUGGESTION for the user to confirm from the strip."""
    low = desc.lower()
    form = "capsule" if re.search(r"\bcap(s|sule)?\b", low) else "tablet"
    hit = brand_lookup(desc, form)
    return hit.pack if hit and hit.form in ("tablet", "capsule") else None


def _mrp_on_billed_basis(line: BillLine) -> Optional[float]:
    """MRP is printed per pack. A per-pack rate (strip/bottle/tube) compares directly; a per-tablet rate needs tablets per strip."""
    if not line.mrp:
        return None
    u = (line.unit or "").lower()
    if u in EACH_UNITS:
        return line.mrp
    if u in TAB_UNITS:
        return line.mrp if line.mrp_each else (line.mrp / line.pack if line.pack else None)
    if u in STRIP_UNITS:
        return (line.mrp * line.pack if line.pack else None) if line.mrp_each else line.mrp
    return line.mrp if u in BOTTLE_UNITS | TUBE_UNITS | VIAL_UNITS else None


def _audit_core(line: BillLine, confirmed: dict | None = None) -> Finding:
    """`confirmed` maps a lower-cased bill description to a salt the USER typed from the strip."""
    fl = injectables.iv_fluid(line.desc)
    if fl and injectables.has_fluid_benchmark(*fl):
        return _audit_iv_fluid(line, *fl)
    if NON_MEDICINE.search(line.desc):
        return Finding(line, TIER_NOT_MEDICINE, note="Consumables, devices, rooms and procedures: no benchmark loaded yet.")
    forced = (confirmed or {}).get(line.desc.lower())
    r = resolve(line.desc, forced_salt=forced.lower() if forced else None)
    via_model = False
    if not r and not llm.is_offline():
        guess = resolve_with_model(line.desc)
        if guess:
            # A model's brand->salt guess can be confidently wrong (e.g. Lasix -> lisinopril), so it is only
            # a SUGGESTION: no price judgement, no accusation, no saving until the user confirms from the strip.
            st = " + ".join(f"{v:g} {u}" for v, u in guess[1])
            return Finding(line, TIER_NEEDS_CONFIRM, guess[0], st, via_model=True,
                           note=f"Our AI thinks this is {guess[0]} {st}. It may be wrong: check the composition printed on "
                                "the strip and confirm. No price judgement is made until you do.")
    if not r:
        return Finding(line, TIER_NO_BENCHMARK, note="Could not match this item to a known salt.")
    generic, strengths, form, mr, pack_in_desc, per, src = r
    st_txt = " + ".join(f"{v:g} {u}" for v, u in strengths)
    if form in ("liquid", "topical"):
        return _audit_liquid(line, generic, strengths, form, src, st_txt)
    if form == "injection":
        return _audit_injection(line, generic, strengths, src, st_txt)
    # --- per-unit price: the billed unit must be stated; a wrong guess would accuse falsely
    unit = (line.unit or "").lower()
    unit_price = None
    if unit in TAB_UNITS:
        unit_price = line.rate
    elif unit in STRIP_UNITS:
        pk = line.pack or pack_in_desc
        if pk:
            unit_price = line.rate / pk
    if unit_price is None:
        why = ("Add the unit column (tab or strip)." if not unit else
               "Strip price needs the pack size (tablets per strip)." if unit in STRIP_UNITS else "Unknown unit.")
        return Finding(line, TIER_UNIT_UNCLEAR, generic, st_txt, note="Cannot tell if the rate is per tablet or per strip. " + why)
    if abs(line.qty * line.rate - line.amount) > max(1.0, 0.02 * line.amount):
        return Finding(line, TIER_UNIT_UNCLEAR, generic, st_txt, unit_price,
                       note="Quantity x rate does not equal the amount charged. Ask the billing desk to explain.")
    ceil = nppa.find(generic, strengths, form, mr)
    gen = ja.find(generic, strengths, form, mr)
    gen = [g for g in gen if g.available and g.price_per_unit]
    c = ceil[0].price if ceil else None
    g = gen[0] if gen else None
    if src == "brand_table?mr" and any([c, g, nppa.find(generic, strengths, form, not mr),
                                        [x for x in ja.find(generic, strengths, form, not mr) if x.available]]):
        # The table lists this brand only as an SR/XR/MR product but the bill does not say so. Plain and modified-release
        # tablets have different price benchmarks, so a wrong guess would give a wrong verdict.
        return Finding(line, TIER_NEEDS_CONFIRM, generic, st_txt, round(unit_price, 3),
                       note=f"The brand table lists only a modified-release (SR/XR) version of this brand, but the bill does not say "
                            f"which one you got. Check the strip: if it is {'plain' if mr else 'SR/XR'} the price benchmark differs.")
    if src.startswith("brand_table") and "+" in generic and (c is not None or g) and not composition_stated(line.desc, generic):
        # The brand table lists at most two actives per product, so a 3-active product (Zerodol-SP) looks like a 2-active one.
        return Finding(line, TIER_NEEDS_CONFIRM, generic, st_txt, round(unit_price, 3),
                       note=f"The brand table says {generic}, but it stores at most two ingredients per product, so a third may be "
                            "missing. Check the composition on the strip before any price comparison.")
    f = Finding(line, TIER_NO_BENCHMARK, generic, st_txt, round(unit_price, 3), c,
                g.price_per_unit if g else None, g.name if g else "", via_model=via_model, basis="tablet")
    tail = " Composition came from a public brand table: check it against your strip." if src.startswith("brand_table") else ""
    if c is not None and unit_price > c * GST_ALLOWANCE:
        f.tier = TIER_ABOVE_CEILING
        f.possible_saving = round((unit_price - c) * line.qty, 2)
        f.note = (f"Charged {unit_price:.2f} per unit; NPPA ceiling is {c:.2f} (plus up to 12% GST = {c*GST_ALLOWANCE:.2f}). "
                  "Ask the hospital to justify the price." + tail)
    elif g and unit_price >= GENERIC_GAP_RATIO * g.price_per_unit:
        if set(generic.split("+")) & DOCTOR_ONLY:
            f.tier = TIER_DOCTOR_ONLY
            f.note = "A generic exists, but switching this medicine should be decided by your doctor."
        else:
            f.tier = TIER_GENERIC_GAP
            f.possible_saving = round((unit_price - g.price_per_unit) * line.qty, 2)
            f.note = (f"Same salt and strength is listed under Jan Aushadhi at {g.price_per_unit:.2f} per unit. "
                      "Ask your doctor or pharmacist whether a generic of the same salt is suitable." + tail)
    elif c is not None or g:
        f.tier = TIER_OK
        f.note = "Within the benchmarks we hold."
    else:
        f.note = "No benchmark for this salt and strength in our data (not the same as 'no ceiling exists')."
    return f


def _audit_liquid(line: BillLine, generic: str, strengths, form: str, src: str, st_txt: str) -> Finding:
    """Bottles and tubes: price per ml / gm against NPPA oral-liquid ceilings and Jan Aushadhi pack prices."""
    tail = " Composition came from a public brand table: check it against the pack." if src.startswith("brand_table") else ""
    nb = lambda note: Finding(line, TIER_NO_BENCHMARK, generic, st_txt, note=note + tail)
    conc = liquids.conc_from_hit(strengths) if src.startswith("brand_table") else None
    if not conc:
        return nb(f"Looks like {generic} {st_txt} ({form}), but the concentration per ml could not be read with certainty, so no "
                  "price comparison is made. The MRP printed on the pack still applies.")
    unit = (line.unit or "").lower()
    desc_pack = liquids.pack_from_desc(line.desc)
    if unit in BOTTLE_UNITS | TUBE_UNITS:
        cu = "ml" if unit in BOTTLE_UNITS else "g"
        if unit in ("ml", "gm", "g"):
            content, unit_price = None, line.rate
        else:
            content = line.pack or (desc_pack[0] if desc_pack and desc_pack[1] == cu else None)
            unit_price = line.rate / content if content else None
    else:
        cu, content, unit_price = ("ml" if form == "liquid" else "g"), None, None
    if unit_price is None:
        return Finding(line, TIER_UNIT_UNCLEAR, generic, st_txt,
                       note="Say how it was sold (bottle or tube) and how many ml or gm it holds, so the price per ml/gm can be "
                            "compared." + tail)
    if abs(line.qty * line.rate - line.amount) > max(1.0, 0.02 * line.amount):
        return Finding(line, TIER_UNIT_UNCLEAR, generic, st_txt, round(unit_price, 4),
                       note="Quantity x rate does not equal the amount charged. Ask the billing desk to explain.")
    salts = liquids.salts_of(generic)
    ceil = liquids.find_ceiling(salts, conc) if cu == "ml" else None
    gen = liquids.find_generic(salts, conc, cu, content)
    per = "ml" if cu == "ml" else "gm"
    f = Finding(line, TIER_NO_BENCHMARK, generic, st_txt, round(unit_price, 4), ceil.price_per_unit if ceil else None,
                gen.price_per_unit if gen else None, gen.name if gen else "", basis=per)
    if ceil and unit_price > ceil.price_per_unit * GST_ALLOWANCE:
        f.tier = TIER_ABOVE_CEILING
        f.possible_saving = round((unit_price - ceil.price_per_unit) * (content or 1) * line.qty, 2)
        f.note = (f"Charged {unit_price:.3f} per {per}; NPPA ceiling is {ceil.price_per_unit:.3f} (plus up to 12% GST = "
                  f"{ceil.price_per_unit * GST_ALLOWANCE:.3f}). Ask the hospital to justify the price." + tail)
    elif gen and unit_price >= GENERIC_GAP_RATIO * gen.price_per_unit:
        if set(generic.split("+")) & DOCTOR_ONLY:
            f.tier, f.note = TIER_DOCTOR_ONLY, "A generic exists, but switching this medicine should be decided by your doctor."
        else:
            f.tier = TIER_GENERIC_GAP
            f.possible_saving = round((unit_price - gen.price_per_unit) * (content or 1) * line.qty, 2)
            f.note = (f"Same salt and concentration is listed under Jan Aushadhi at {gen.price_per_unit:.3f} per {per} "
                      "(pack sizes differ, so this is only a rough guide). Ask your doctor or pharmacist whether a generic is suitable." + tail)
    elif ceil or gen:
        f.tier, f.note = TIER_OK, "Within the benchmarks we hold." + tail
    else:
        f.note = f"No benchmark for {generic} {st_txt} in our data (not the same as 'no ceiling exists')." + tail
    return f


def _audit_iv_fluid(line: BillLine, fluid: str, volume: int) -> Finding:
    """IV bags are priced per bag. Two ceilings can apply: the plain one (glass or non-glass, narrowed if the bill says which) and
    a higher 'special features' one for packs by manufacturers NPPA lists (Eurohead bottles, multi-port bags). A price between the
    two is a question about the pack, not a finding; only a price above both is flagged."""
    name = injectables.FLUID_NAMES[fluid]
    d = line.desc.lower()
    container = ("non-glass" if re.search(r"non[\s-]*glass|plastic|poly\s*pack|polypack|\bffs\b|\bbfs\b|soft\s*pack|\bbag\b", d) else
                 "glass" if re.search(r"\bglass\b|\bbottle\b", d) else None)
    rows = injectables.fluid_ceilings(fluid, volume)
    chosen = [(k, p) for k, p in rows if k in (container, "any")] or rows
    plain = max((p for _, p in chosen), default=None)
    special = injectables.special_ceiling(fluid, volume)
    named_special = special is not None and injectables.special_pack_mentioned(line.desc)
    f = Finding(line, TIER_NO_BENCHMARK, name, f"{volume} ml bag", round(line.rate, 4), special if named_special else (plain or special), basis="bag")
    plain_txt = (", ".join(f"{k} {p:.2f}" for k, p in sorted(chosen)) if len(chosen) > 1 else f"{chosen[0][0]} {chosen[0][1]:.2f}") if chosen else ""
    if abs(line.qty * line.rate - line.amount) > max(1.0, 0.02 * line.amount):
        f.tier, f.note = TIER_UNIT_UNCLEAR, "Quantity x rate does not equal the amount charged. Ask the billing desk to explain."
        return f
    ref = max([x for x in (plain, special if named_special else None) if x is not None], default=special)
    if line.rate <= ref * GST_ALLOWANCE and (plain is None or line.rate <= plain * GST_ALLOWANCE or named_special):
        f.tier = TIER_OK
        f.note = (f"Within the NPPA ceiling for {name} {volume} ml " +
                  (f"in a special-features pack ({special:.2f}), as the bill names a listed manufacturer or brand." if named_special and line.rate > (plain or 0) * GST_ALLOWANCE
                   else f"({plain_txt})."))
    elif special is not None and line.rate <= special * GST_ALLOWANCE:
        f.tier = TIER_NEEDS_CONFIRM
        f.note = (f"Charged {line.rate:.2f} per {volume} ml bag: above the ordinary-pack ceiling ({plain_txt}) but within the "
                  f"special-features ceiling ({special:.2f}, plus GST). Which pack is it? Special-features packs are made by manufacturers "
                  "NPPA lists (Eurohead bottles, multi-port bags). Check the label and the batch MRP before deciding.")
    else:
        f.tier = TIER_ABOVE_CEILING
        top = max(x for x in (plain, special) if x is not None)
        f.possible_saving = round((line.rate - top) * line.qty, 2)
        f.note = (f"Charged {line.rate:.2f} per {volume} ml bag; the NPPA ceiling for {name} is " +
                  (f"{plain_txt} for ordinary packs and {special:.2f} for special-features packs" if plain and special else f"{top:.2f}") +
                  " (plus up to 12% GST). Even the higher ceiling is exceeded. Ask the hospital to justify the price and show the batch MRP.")
    return f


def _audit_injection(line: BillLine, generic: str, strengths, src: str, st_txt: str) -> Finding:
    """Vials/ampoules: per-container price against per-vial lists, per-ml price against per-ml lists. Never converts unless
    the ml per container is given."""
    tail = " Composition came from a public brand table: check it against the pack." if src.startswith("brand_table") else ""
    unit = (line.unit or "").lower()
    ml = line.pack if unit in VIAL_UNITS and line.pack else (liquids.pack_from_desc(line.desc) or (None, None))[0] if unit in VIAL_UNITS else None
    explicit = src == "generic" and re.search(r"\d\s*(mg|mcg|g|iu)\b", line.desc, re.I) and not re.search(r"/\s*\d*\s*ml|%", line.desc, re.I)
    total, conc = injectables.hit_specs(strengths, ml) if (src.startswith("brand_table") or explicit) else (None, None)
    if not (total or conc):
        return Finding(line, TIER_NO_BENCHMARK, generic, st_txt,
                       note=f"Looks like an injection of {generic} {st_txt}, but the strength per vial or per ml could not be read with "
                            "certainty, so no price comparison is made. The MRP printed on the pack still applies." + tail)
    if unit in VIAL_UNITS:
        per_container, per_ml = line.rate, (line.rate / ml if ml else None)
    elif unit == "ml":
        per_container, per_ml = None, line.rate
    else:
        return Finding(line, TIER_UNIT_UNCLEAR, generic, st_txt,
                       note="Say how it was sold: vial (or amp), with the ml it holds if known, or ml." + tail)
    if abs(line.qty * line.rate - line.amount) > max(1.0, 0.02 * line.amount):
        return Finding(line, TIER_UNIT_UNCLEAR, generic, st_txt, round(per_container or per_ml, 4),
                       note="Quantity x rate does not equal the amount charged. Ask the billing desk to explain.")
    salts = liquids.salts_of(generic)
    ceil = injectables.find_ceiling(salts, total, conc, per_container is not None)
    gen = injectables.find_generic(salts, total, conc, per_container is not None, ml)
    if not ceil and not gen and per_container is not None and ml is None and injectables.has_per_ml_benchmark(salts):
        return Finding(line, TIER_UNIT_UNCLEAR, generic, st_txt,
                       note="This injection is priced per ml in the lists. Give the ml each vial or ampoule holds (pack) so the price "
                            "per ml can be compared." + tail)
    if ceil and ceil.per_ml and per_ml is None:
        return Finding(line, TIER_UNIT_UNCLEAR, generic, st_txt, ceiling=ceil.price,
                       note="The NPPA ceiling for this injection is per ml. Give the ml each vial or ampoule holds (pack) so the price "
                            "per ml can be compared." + tail)
    ceil_basis = (per_ml if ceil and ceil.per_ml else per_container) if ceil else None
    f = Finding(line, TIER_NO_BENCHMARK, generic, st_txt, round(ceil_basis if ceil_basis is not None else (per_container or per_ml), 4),
                ceil.price if ceil else None, gen.price if gen else None, gen.name if gen else "")
    f.basis = "ml" if ((ceil and ceil.per_ml) or (not ceil and gen and gen.per_ml)) else "vial"
    per = lambda b: "ml" if b.per_ml else "vial/ampoule"
    qty_units = lambda b: (ml or 1) if b.per_ml else 1
    if ceil and ceil_basis is not None and ceil_basis > ceil.price * GST_ALLOWANCE:
        f.tier = TIER_ABOVE_CEILING
        f.possible_saving = round((ceil_basis - ceil.price) * qty_units(ceil) * line.qty, 2)
        f.note = (f"Charged {ceil_basis:.2f} per {per(ceil)}; NPPA ceiling is {ceil.price:.2f} (plus up to 12% GST = "
                  f"{ceil.price * GST_ALLOWANCE:.2f}). Ask the hospital to justify the price." + tail)
    elif gen:
        gbasis = per_ml if gen.per_ml else per_container
        if gbasis is not None and gbasis >= GENERIC_GAP_RATIO * gen.price:
            if set(generic.split("+")) & DOCTOR_ONLY:
                f.tier, f.note = TIER_DOCTOR_ONLY, "A generic exists, but switching this medicine should be decided by your doctor."
            else:
                f.tier = TIER_GENERIC_GAP
                f.possible_saving = round((gbasis - gen.price) * qty_units(gen) * line.qty, 2)
                f.note = (f"Same medicine and strength is listed under Jan Aushadhi at {gen.price:.2f} per {per(gen)}. Ask your doctor "
                          "or pharmacist whether a generic is suitable." + tail)
        else:
            f.tier, f.note = TIER_OK, "Within the benchmarks we hold." + tail
    elif ceil:
        f.tier, f.note = TIER_OK, "Within the benchmarks we hold." + tail
    else:
        f.note = f"No benchmark for this injection ({generic} {st_txt}) in our data (not the same as 'no ceiling exists')." + tail
    return f


def audit(text: str, confirmed: dict | None = None) -> list[Finding]:
    return [audit_line(l, confirmed) for l in parse_bill(text)]


def summary(findings: list[Finding]) -> dict:
    by = {}
    for f in findings:
        by[f.tier] = by.get(f.tier, 0) + 1
    return {"lines": len(findings), "by_tier": by,
            "billed_total": round(sum(f.line.amount for f in findings), 2),
            "possible_saving_above_ceiling": round(sum(f.possible_saving for f in findings if f.tier == TIER_ABOVE_CEILING), 2),
            "possible_saving_above_mrp": round(sum(f.possible_saving for f in findings if f.tier == TIER_ABOVE_MRP), 2),
            "no_price_control_value": round(sum(f.line.amount for f in findings if f.tier == TIER_SUPPLEMENT), 2),
            "needs_confirmation": sum(1 for f in findings if f.tier == TIER_NEEDS_CONFIRM),
            "possible_saving_generic": round(sum(f.possible_saving for f in findings if f.tier == TIER_GENERIC_GAP), 2),
            "benchmark_dates": {"nppa_ceiling": nppa.AS_ON, "jan_aushadhi": "21 Oct 2026"}}
