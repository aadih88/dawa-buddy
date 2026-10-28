"""Dawa Buddy: was your medicine bill fair?  Photo (or sample) -> confirm the numbers -> what to ask.

Run:  streamlit run bill_app.py
Hosting knob: DAWA_MAX_PHOTO_READS (photo reads per browser session, default 5) protects a public demo's model credits.
"""
import html
import os
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st

from dawa_buddy import bill as b, explainer, i18n, listings, llm, nppa_orders, pipeline, samples, scheduler, ui, vision, webcheck
from dawa_buddy.reader import read_prescription
from dawa_buddy.reconcile import reconcile
from dawa_buddy.report import questions

COLS = samples.COLS
LANGS = {"English": "en", "हिन्दी": "hi", "ಕನ್ನಡ": "kn"}

RED, ORANGE, AMBER, GREEN, GREY = "#d64545", "#e8883a", "#d4a017", "#2e9e6b", "#8a94a0"
# tier -> (colour, short label, group). Groups decide what is shown up front and what is folded away.
RESULT = {
    b.TIER_ABOVE_MRP: (RED, "Above the MRP printed on the pack", "attention"),
    b.TIER_ABOVE_CEILING: (RED, "Above the legal ceiling price", "attention"),
    b.TIER_NEEDS_CONFIRM: (ORANGE, "Please confirm what this is", "attention"),
    b.TIER_UNIT_UNCLEAR: (ORANGE, "Needs the unit or pack size", "attention"),
    b.TIER_GENERIC_GAP: (AMBER, "A cheaper generic exists: ask your doctor", "attention"),
    b.TIER_DOCTOR_ONLY: (AMBER, "A generic exists: only your doctor should switch", "attention"),
    b.TIER_OK: (GREEN, "Within the price limits we hold", "fine"),
    b.TIER_SUPPLEMENT: (GREY, "Supplement: no government price limit", "unchecked"),
    b.TIER_NO_BENCHMARK: (GREY, "No price list covers this", "unchecked"),
    b.TIER_NOT_MEDICINE: (GREY, "Consumable or service", "unchecked"),
}
POSSIBLE_VIOLATION = (b.TIER_ABOVE_CEILING, b.TIER_ABOVE_MRP)
PER = {"tablet": "tablet", "ml": "ml", "gm": "gm", "vial": "vial", "bag": "bag"}


st.set_page_config(page_title="Dawa Buddy: was your medicine bill fair?", page_icon="💊", layout="centered",
                   initial_sidebar_state="collapsed")
st.markdown(ui.css(), unsafe_allow_html=True)


# ---------------------------------------------------------------- helpers
def rupees(x: float) -> str:
    return f"₹{x:,.0f}" if abs(x - round(x)) < 0.005 else f"₹{x:,.2f}"


@st.cache_data(show_spinner=False)
def parse_rx(text: str):
    """Cached: the reader may call a model, and Streamlit reruns the script on every click."""
    return read_prescription(text)


def default_units(df: pd.DataFrame) -> pd.DataFrame:
    """Fill the unit only where the description makes it certain; tablets stay blank (per tablet or per strip is the user's call)."""
    def guess(r):
        if r.get("unit"):
            return r["unit"]
        d = str(r["description"]).lower()
        return ("vial" if re.search(r"\binj", d) else "bottle" if re.search(r"\b(syp|syrup|susp|suspension|drops?)\b", d) else
                "tube" if re.search(r"\b(cream|gel|oint|ointment|lotion)\b", d) else
                "each" if b.NON_MEDICINE.search(d) else None)
    out = df.copy()
    out["unit"] = [None if pd.isna(guess(r)) else guess(r) for r in out.to_dict("records")]
    return out


def billed_word(unit: str | None) -> str:
    return {"tab": "tablet", "strip": "strip", "bottle": "bottle", "tube": "tube", "vial": "vial", "each": "piece"}.get((unit or "").lower(), "unit")


def first_sentence(text: str) -> str:
    return text.split(". ")[0].rstrip(".") + "."


def finding_html(f: b.Finding) -> str:
    """One finding as a card: a chip for what it is, the item, then the price meter (paid against the limit) or one plain sentence."""
    kind = "red" if f.tier in POSSIBLE_VIOLATION else "amber"
    per = PER.get(f.basis, "unit")
    visual, body = "", ""
    if f.tier == b.TIER_ABOVE_CEILING and f.unit_price and f.ceiling:
        visual = ui.meter(f.unit_price, f.ceiling, "red", f"You paid {rupees(f.unit_price)} per {per}", f"Legal limit {rupees(f.ceiling)}")
    elif f.tier == b.TIER_ABOVE_MRP and f.mrp_unit:
        w = billed_word(f.line.unit)
        visual = ui.meter(f.line.rate, f.mrp_unit, "red", f"You paid {rupees(f.line.rate)} per {w}", f"Printed MRP {rupees(f.mrp_unit)}")
    elif f.tier in (b.TIER_GENERIC_GAP, b.TIER_DOCTOR_ONLY) and f.unit_price and f.generic_unit:
        visual = ui.meter(f.unit_price, f.generic_unit, "amber", f"You paid {rupees(f.unit_price)} per {per}", f"Generic {rupees(f.generic_unit)}")
    else:
        body = first_sentence(f.note)
    why = f.note + (" Tip: under 'Edit the numbers', add the maker or 'glass' / 'non-glass' to the item name to settle this." if f.basis == "bag" else "")
    return ui.card(kind, f.line.desc, RESULT[f.tier][1], total=f"{rupees(f.line.amount)} total", body=body, visual=visual, why=why)


def msg(kind: str, text: str) -> None:
    st.markdown(ui.message(kind, text), unsafe_allow_html=True)


def reset():
    for k in list(st.session_state):
        del st.session_state[k]


# ---------------------------------------------------------------- screen 1: start
def start():
    st.markdown(ui.header(), unsafe_allow_html=True)
    st.title("Was your medicine bill fair?")
    st.markdown("<p class='db-sub'>Photograph your bill. We compare it with government price lists and your prescription, "
                "and tell you what to ask.</p>", unsafe_allow_html=True)
    pending = st.session_state.pop("start_msg", None)       # an error from the last read, shown once
    if pending:
        msg(*pending)
    reading = st.session_state.get("reading", False)       # set by the button, so the next run shows every control disabled while the photo is read
    bill_img = rx_img = None
    if llm.vision_available():
        bill_img = st.file_uploader("Photo of your bill", type=["png", "jpg", "jpeg"], key="bill_photo", disabled=reading)
        with st.expander("＋ Add your prescription (optional)"):
            rx_img = st.file_uploader("Photo of your prescription", type=["png", "jpg", "jpeg"], key="rx_photo", disabled=reading)
        if st.button("Read my bill", type="primary", disabled=bill_img is None or reading, width="stretch"):
            st.session_state.reading = True
            st.rerun()
        if reading and bill_img is None:          # the upload was lost (a refresh): give the controls back
            st.session_state.reading = False
            st.rerun()
        st.markdown("<p class='db-or'>or try a sample</p>", unsafe_allow_html=True)
    else:
        st.markdown("<p class='db-or'>Try a sample bill</p>", unsafe_allow_html=True)
    cols = st.columns(len(samples.SAMPLES))
    for col, name in zip(cols, samples.SAMPLES):
        if col.button(name, key=f"sample_{name}", width="stretch", disabled=reading):
            smp = samples.SAMPLES[name]
            reset()          # a sample takes the same road as a photo: confirm the numbers, then see the result
            st.session_state.update(df=samples.frame(name), rx=smp["rx"], total=smp["total"], sample=name, stage="review")
            st.rerun()
    if reading and bill_img is not None:      # last, so every control above is already drawn (disabled) while the photo is read
        read_photos(bill_img, rx_img)


def read_photos(bill_img, rx_img):
    limit = int(os.environ.get("DAWA_MAX_PHOTO_READS", "5"))
    if st.session_state.get("photo_reads", 0) >= limit:
        st.session_state.update(reading=False, start_msg=("amber", f"This demo reads {limit} photos per visit. Try a sample, or run the app yourself (see the README)."))
        st.rerun()
    reads = st.session_state.get("photo_reads", 0) + 1
    with st.spinner("Reading your bill..."):
        try:
            rows, total = vision.read_bill_photo(bill_img.getvalue(), bill_img.type)
            rx = vision.read_rx_photo(rx_img.getvalue(), rx_img.type) if rx_img else ""
        except Exception as e:
            st.session_state.update(reading=False, start_msg=("red", f"We could not read that photo ({type(e).__name__}). Try a sharper, flatter photo."))
            st.rerun()
    if not rows:
        st.session_state.update(reading=False, start_msg=("amber", "We could not find any bill lines in that photo. Try a sharper, flatter photo."))
        st.rerun()
    reset()
    df = pd.DataFrame([r.__dict__ for r in rows]).drop(columns=["notes"], errors="ignore")
    st.session_state.update(df=enrich(df), rx=rx, total=total, stage="review", photo_reads=reads, load_id=1)
    st.rerun()


# ---------------------------------------------------------------- the lines: one card per line, readable on a phone
UNIT_LABEL = {"tab": "per tablet", "strip": "per strip", "bottle": "per bottle", "tube": "per tube", "vial": "per vial", "each": "per piece"}
PACK_LABEL = {"tab": "Tablets per strip (to compare with the MRP)", "strip": "Tablets per strip", "bottle": "ml in the bottle",
              "tube": "gm in the tube", "vial": "ml in the vial (optional)"}


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """After a photo read: fill the unit where certain, and suggest tablets per strip from the brand table (to be confirmed on the strip)."""
    df = default_units(df)
    guesses = {}
    packs = []
    for r in df.to_dict("records"):
        pack = r.get("pack")
        if pack is None or pd.isna(pack):
            guess = b.suggest_pack(str(r["description"])) if r.get("unit") in (None, "tab", "strip") or pd.isna(r.get("unit")) else None
            if guess:
                guesses[str(r["description"])] = (guess, "the brand table")
            packs.append(guess)
        else:
            packs.append(pack)
    df["pack"] = packs
    st.session_state.pack_guess = guesses
    return df


def num(v, default=0.0) -> float:
    return default if v is None or pd.isna(v) else float(v)


def unit_options(r: dict) -> list[str]:
    """Only the ways this line can plausibly have been sold: five choices wrap on a phone. A tablet line is per tablet or per strip; a line already
    known to be a syrup, tube or vial adds that one; anything we cannot place keeps every choice."""
    known = r.get("unit") if r.get("unit") in UNIT_LABEL else None
    if known in ("bottle", "tube", "vial", "each"):
        return [known, "tab", "strip"]
    if known in ("tab", "strip") or re.search(r"\b(tab|tablet|cap|capsule)\b", str(r.get("description", "")).lower()):
        return ["tab", "strip"]
    return list(UNIT_LABEL)


def lines_form(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    """One card per bill line: what we read (to compare with the paper), how it was sold, pack size, and a popover to fix any number."""
    guesses = st.session_state.get("pack_guess", {})
    rows = []
    for i, r in enumerate(df.to_dict("records")):
        k = f"{scope}{st.session_state.get('load_id', 0)}_{i}"
        if st.session_state.get(f"{k}_rm"):
            continue
        qty, rate = st.session_state.get(f"{k}_qty", num(r["qty"])), st.session_state.get(f"{k}_rate", num(r["rate"]))
        amount, mrp = st.session_state.get(f"{k}_amt", num(r["amount"])), st.session_state.get(f"{k}_mrp", num(r["mrp"]))
        name = st.session_state.get(f"{k}_name", str(r["description"]))
        with st.container(border=True, key=f"card_{k}"):
            st.markdown(ui.line_head(name, f"{qty:g} × {rupees(rate)} = {rupees(amount)}", f"MRP on pack {rupees(mrp)}" if mrp else "", bool(r.get("unsure"))),
                        unsafe_allow_html=True)
            unit = st.segmented_control("Sold", unit_options(r), format_func=UNIT_LABEL.get, key=f"{k}_unit", label_visibility="collapsed",
                                        default=r["unit"] if r["unit"] in UNIT_LABEL else None)
            if unit is None:
                st.caption("How was this sold? Choose one so we can compare the price.")
            pack = None
            if unit and unit != "each" and (unit != "tab" or mrp):
                pack = st.number_input(PACK_LABEL[unit], min_value=0.0, step=1.0, key=f"{k}_pack",
                                       value=num(r["pack"]) if r.get("pack") is not None and not pd.isna(r.get("pack")) else 0.0,
                                       help="From the strip or box" + ("; suggested: check yours" if guesses.get(str(r["description"])) else ""))
                g = guesses.get(str(r["description"]))
                if g and pack == g[0]:
                    st.caption(f"Suggested from {g[1]}. Check it on your strip.")
            with st.popover("Fix a number", width="stretch"):
                st.text_input("Item", value=str(r["description"]), key=f"{k}_name")
                c1, c2, c3 = st.columns(3)
                c1.number_input("Qty", min_value=0.0, value=num(r["qty"]), key=f"{k}_qty")
                c2.number_input("Price each", min_value=0.0, value=num(r["rate"]), step=0.01, key=f"{k}_rate")
                c3.number_input("Total", min_value=0.0, value=num(r["amount"]), step=0.01, key=f"{k}_amt")
                st.number_input("MRP printed on the pack (optional)", min_value=0.0, value=num(r["mrp"]), step=0.01, key=f"{k}_mrp")
                st.checkbox("Remove this line", key=f"{k}_rm")
        rows.append({"description": name, "qty": qty, "rate": rate, "amount": amount, "unit": unit, "pack": (pack or None),
                     "mrp": (mrp or None), "unsure": bool(r.get("unsure"))})
    return pd.DataFrame(rows, columns=COLS)


def add_line():
    with st.popover("Add a line we missed", width="stretch"):
        name = st.text_input("Item", key="new_name")
        c1, c2, c3 = st.columns(3)
        qty = c1.number_input("Qty", min_value=0.0, value=1.0, key="new_qty")
        rate = c2.number_input("Price each", min_value=0.0, step=0.01, key="new_rate")
        amount = c3.number_input("Total", min_value=0.0, step=0.01, key="new_amt")
        if st.button("Add", key="new_add") and name.strip():
            row = {"description": name.strip(), "qty": qty, "rate": rate, "amount": amount, "unit": None, "pack": None, "mrp": None, "unsure": False}
            st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([row])], ignore_index=True)
            st.rerun()


# ---------------------------------------------------------------- screen 2: review
def dose_warning(text: str) -> bool:
    """One amber note (not one per line) when a prescription line has no readable dose; returns True if shown so the caller can open the text box."""
    bad = explainer.unclear_dose_lines(text)
    if bad:
        n = len(bad)
        st.markdown(ui.note("amber", f"We could not read the dose on {n} prescription line{'s' if n > 1 else ''}", [(line, "") for line in bad],
                            foot="Check each against your paper and fix the line in the prescription box (for example 1-0-1). Until then we cannot say how to take it."),
                    unsafe_allow_html=True)
    return bool(bad)


def review():
    st.markdown(ui.header(2, "Step 2 of 3 · Check the numbers"), unsafe_allow_html=True)
    st.title("Check the numbers")
    st.markdown("<p class='db-sub'>Compare each line with your paper. Choose how it was sold, and fix anything that is wrong.</p>", unsafe_allow_html=True)
    if st.session_state.get("sample"):
        st.caption(f"Sample: {samples.SAMPLES[st.session_state.sample]['about']}")
    unclear = dose_warning(st.session_state.get("rx", ""))      # first: it is the thing most likely to be missed, so it must not sit below six cards
    df = lines_form(st.session_state.df, "r")
    add_line()
    total = st.number_input("Total printed on the bill (optional)", value=float(st.session_state.get("total") or 0.0))
    with st.expander("Prescription lines", expanded=unclear):
        st.text_area("One medicine per line, as written", key="rx", height=130, label_visibility="collapsed")
    checking = st.session_state.get("checking", False)
    if st.button("See the result", type="primary", width="stretch", disabled=checking):
        st.session_state.checking = True
        st.rerun()
    if st.button("Start over", type="tertiary", width="stretch", disabled=checking):
        reset(); st.rerun()
    if checking:
        with st.spinner("Checking prices..."):
            st.session_state.update(df=df, total=total, stage="results", load_id=st.session_state.get("load_id", 0) + 1, checking=False)
            st.rerun()


# ---------------------------------------------------------------- screen 3: results
def verdict(n_viol, n_ask, excess, generic):
    """The headline answer: what to do first, in a sentence. Tiles appear only when they carry news: a zero is not a result."""
    if n_viol:
        total = n_viol + n_ask          # the headline counts everything listed below it, so the two numbers always agree
        kind, head = "red", f"{total} thing{'s' if total > 1 else ''} to ask about"
        body = ("Some lines are above a legal price limit. Ask the seller to explain them." if excess else
                "Nothing is above a legal limit, but these need a question to the seller or your confirmation.")
    elif n_ask:
        kind, head = "amber", "Nothing above a legal limit, but a few questions"
        body = f"{n_ask} line{'s need' if n_ask > 1 else ' needs'} a look or your confirmation."
    else:
        kind, head = "green", "Nothing above a legal limit"
        body = "Every price we could check is within the limits. What we checked is listed below."
    stats = ([(rupees(excess), "above legal limits", "red")] if excess else []) + \
            ([(rupees(generic), "possible saving with a generic (ask your doctor)", "amber")] if generic else [])
    st.markdown(ui.verdict(kind, head, body, stats), unsafe_allow_html=True)


def check_rows(fs, flags, wrong, unidentified, generic) -> list[tuple[str, str, str]]:
    """'What we checked': what was verified and found fine, what was not and why. Each row says what was done, so a clean bill reads as protection."""
    n = len(fs)
    plural = lambda k, word: f"{k} {word}{'' if k == 1 else 's'}"
    over = sum(f.tier == b.TIER_ABOVE_MRP for f in fs)
    known = sum(f.mrp_pct is not None or f.tier == b.TIER_ABOVE_MRP for f in fs)
    ok = known - over
    rows = []
    if over:
        rest = n - over - ok
        rows.append(("red", "Printed MRP", f"Charged above the printed MRP on {plural(over, 'line')} of {n}."
                     + (f" {plural(ok, 'other line')} {'is' if ok == 1 else 'are'} within it." if ok else "")
                     + (f" {rest} had no MRP or pack size to compare." if rest else "")))
    elif ok:
        rows.append(("green", "Printed MRP", f"Charged at or below the printed MRP on {'all ' + plural(n, 'line') if ok == n else plural(ok, 'line') + ' of ' + str(n)}. "
                     "Selling above the printed MRP is not allowed for any product." + (f" {n - ok} had no MRP or pack size to compare." if ok < n else "")))
    else:
        rows.append(("grey", "Printed MRP", "Could not be compared: add the MRP printed on the pack and the tablets per strip (Edit the numbers)."))
    capped = [f for f in fs if f.ceiling is not None]
    above = sum(f.tier == b.TIER_ABOVE_CEILING for f in fs)
    if above:
        rows.append(("red", "Legal price ceiling (NPPA)", f"Above the ceiling on {above} of {plural(len(capped), 'price-controlled line')}."))
    elif capped:
        rows.append(("green", "Legal price ceiling (NPPA)", f"Within the ceiling on {'the' if len(capped) == 1 else 'all ' + str(len(capped))} price-controlled {'line' if len(capped) == 1 else 'lines'}."))
    else:
        rows.append(("grey", "Legal price ceiling (NPPA)", "Not applicable: none of these has a government ceiling. That is normal, since most branded medicines are not price-controlled."))
    if not st.session_state.get("rx", "").strip():
        rows.append(("grey", "Your prescription", "None added. Add one to check you were given the medicines the doctor wrote."))
    elif not flags:
        rows.append(("green", "Your prescription", "The bill matches your prescription: same products, no extras, no missing items."))
    else:
        rows.append(("red" if wrong else "amber", "Your prescription", f"{plural(len(flags), 'difference')} from the prescription, listed below."))
    if generic:
        k = sum(f.tier == b.TIER_GENERIC_GAP for f in fs)
        rows.append(("amber", "Cheaper generics", f"A cheaper generic may exist for {plural(k, 'line')} (about {rupees(generic)}). Ask your doctor before switching."))
    if unidentified:
        rows.append(("amber", "Medicines to confirm", f"{plural(len(unidentified), 'medicine')} not identified yet: {', '.join(unidentified)}. Confirm them under “Help us identify”."))
    return rows


def mini(f) -> str:
    """One line per folded-away item: what it is, how it was judged, and (for 'not covered') why there is nothing to compare with."""
    right = rupees(f.line.amount)
    label = html.escape(RESULT[f.tier][1])
    why = ""
    if f.tier in (b.TIER_NO_BENCHMARK, b.TIER_NOT_MEDICINE, b.TIER_SUPPLEMENT):
        known = f"Identified as {f.ingredients} {f.strength}. " if f.ingredients and f.tier == b.TIER_NO_BENCHMARK else ""
        reason = {b.TIER_NO_BENCHMARK: "We hold no NPPA ceiling or Jan Aushadhi price for this salt, strength and form.",
                  b.TIER_NOT_MEDICINE: "Consumables and devices have no price list here.",
                  b.TIER_SUPPLEMENT: "Supplements have no government price limit."}[f.tier]
        mrp = f" Charged {f.mrp_pct:.0f}% of the printed MRP." if f.mrp_pct is not None else ""
        why = f"<br><span class='small'>{html.escape(known + reason + mrp)}</span>"
    elif f.mrp_pct is not None and f.tier == b.TIER_OK:
        why = f"<br><span class='small'>Charged {f.mrp_pct:.0f}% of the printed MRP.</span>"
    return f"<div class='mini'><span class='l'>{html.escape(f.line.desc)}<br><span class='small'>{label}</span>{why}</span><span class='r'>{right}</span></div>"


def results(df, total):
    confirmed = st.session_state.setdefault("confirmed", {})
    rows = [vision.Row(**{k: (None if pd.isna(v) else v) for k, v in rec.items() if k in COLS}) for rec in df.to_dict("records")]
    lines = vision.rows_to_lines(rows)
    fs = [b.audit_line(l, confirmed) for l in lines]
    tot = sum(f.line.amount for f in fs) or 1
    s = b.summary(fs)
    group = lambda g: sorted([f for f in fs if RESULT[f.tier][2] == g], key=lambda f: list(RESULT).index(f.tier))
    attention, fine, unchecked = group("attention"), group("fine"), group("unchecked")
    n_viol = sum(f.tier in POSSIBLE_VIOLATION for f in fs)
    n_ask = len(attention) - n_viol

    flags = reconcile(parse_rx(st.session_state["rx"]), lines, total or None) if st.session_state.get("rx", "").strip() else []
    wrong = [x for x in flags if x.kind == "different_variant"]
    other = [x for x in flags if x.kind != "different_variant"]

    peer_found = peer_findings(fs)
    n_ask += sum(x["higher"] for x in peer_found)
    listed = listing_findings(fs)
    flagged_listings = [x for x in listed if x["kind"] in ("printed_above_listings", "charged_above_listed_mrp")]
    n_ask += len(flagged_listings)
    n_viol_total = n_viol + len(wrong)
    st.markdown(ui.header(3, "Result"), unsafe_allow_html=True)
    unidentified = [f.line.desc for f in {f.line.desc.lower(): f for f in fs if f.tier in (b.TIER_NEEDS_CONFIRM, b.TIER_NO_BENCHMARK)
                                           and not f.ingredients and f.basis != "bag"}.values()]
    verdict(n_viol_total, n_ask, s["possible_saving_above_ceiling"] + s["possible_saving_above_mrp"], s["possible_saving_generic"])
    st.markdown(ui.checks(check_rows(fs, flags, wrong, unidentified, s["possible_saving_generic"])), unsafe_allow_html=True)

    needs_pack = [f for f in fs if f.line.mrp and f.mrp_unit is None and (f.line.unit or "").lower() in ("tab", "strip") and not f.line.pack]
    if needs_pack:
        st.caption(f"Tip: {len(needs_pack)} line{'s have' if len(needs_pack) > 1 else ' has'} a printed MRP but no tablets-per-strip, so the MRP could "
                   "not be checked. Add it under “Edit the numbers”.")

    n_cards = len(wrong) + len(attention) + sum(x["higher"] for x in peer_found) + len(flagged_listings)
    if n_cards:
        st.markdown(ui.section_label("Ask about these", n_cards), unsafe_allow_html=True)
    for x in wrong:        # a possibly wrong medicine matters more than any price, so it comes first
        prescribed, billed = x.subject.split(" -> ")
        st.markdown(ui.card("red", billed, "Check before taking", visual=ui.diff(prescribed, billed), why=x.note), unsafe_allow_html=True)
    for f in attention:
        st.markdown(finding_html(f), unsafe_allow_html=True)
    peers = peer_cards(peer_found)
    online = listing_cards(listed)

    if fine:
        with st.expander(f"Within the limits ({len(fine)})"):
            st.markdown("".join(mini(f) for f in fine), unsafe_allow_html=True)
    if unchecked:
        with st.expander(f"Not covered by a price list ({len(unchecked)})"):
            st.markdown("".join(mini(f) for f in unchecked), unsafe_allow_html=True)
            if s["no_price_control_value"]:
                st.caption(f"Supplements have no government price limit; only the MRP printed on the pack limits them.")
    if other:
        with st.expander(f"Other differences from the prescription ({len(other)})"):
            st.markdown("\n".join(f"- **{x.subject}**: {x.note}" for x in other))
    if flags == [] and st.session_state.get("rx", "").strip():
        msg("green", "The bill matches the prescription.")

    online_check(fs, df)
    identify(fs, confirmed)
    briefing()
    st.download_button("Download the questions to ask", questions(fs, flags, peers, online), file_name="questions_to_ask.md", type="primary", width="stretch")
    if st.button("Check another bill", width="stretch"):
        reset(); st.rerun()
    return fs


def prefill(f) -> str:
    """'tamsulosin 0.4 mg' from the brand table, so the user only has to confirm it. A model's guess is never pre-filled: it would
    push the user toward an answer that may be wrong (the AI said 'bisoprolol' for a bisoprolol + telmisartan tablet)."""
    if f.via_model or f.tier == b.TIER_NEEDS_CONFIRM:
        return ""
    salts, strengths = [x for x in f.ingredients.split("+") if x], [x for x in f.strength.split(" + ") if x]
    return " + ".join(f"{a} {b_}" for a, b_ in zip(salts, strengths)) if salts and len(salts) == len(strengths) else ""


def peer_findings(fs) -> list[dict]:
    """After the user confirms a combination and we find NPPA orders for it: other companies' prices for the same medicine (context, not a limit)."""
    found = []
    for f in fs:
        got = st.session_state.get("orders", {}).get(f.line.desc.lower())
        paid = b.line_unit_price(f.line)
        if not got or not got[0][0] or paid is None:
            continue
        rows, urls = got[0]
        found.append({"f": f, "paid": paid, "rows": rows, "urls": urls, "lo": rows[0].price, "hi": rows[-1].price,
                      "higher": paid > rows[-1].price * 1.05})        # above the dearest NPPA-priced version even with 5% GST
    return found


def peer_cards(found: list[dict]) -> list[str]:
    lines_out = []
    for x in found:
        f, rows, urls, paid, lo, hi = x["f"], x["rows"], x["urls"], x["paid"], x["lo"], x["hi"]
        n = len(rows)
        meta = (f"You paid {rupees(paid)} per tablet · NPPA-priced versions by {n} other compan{'ies' if n > 1 else 'y'}: "
                f"{rupees(lo)} to {rupees(hi)} before GST")
        why = ("This is not a legal limit on your brand: NPPA's orders bind only the companies named, and none of the orders we found names this "
               "brand's maker. It shows that the same combination is sold for less. Ask your doctor or pharmacist whether another brand of the "
               "same combination is suitable. Do not switch on your own. Companies: " +
               "; ".join(sorted({r.company.replace("M/s ", "") for r in rows})[:6]) + ".")
        kind = "amber" if x["higher"] else "green"
        visual = ui.meter(paid, hi, kind, f"You paid {rupees(paid)} per tablet", f"NPPA-priced up to {rupees(hi)} (before GST)")
        st.markdown(ui.card(kind, f.line.desc, "Same combination, price-controlled lower elsewhere" if x["higher"] else "In line with NPPA-priced versions",
                            total=f"{rupees(f.line.amount)} total", body=f"{n} other compan{'ies' if n > 1 else 'y'}: {rupees(lo)} to {rupees(hi)} per tablet before GST",
                            visual=visual, why=why), unsafe_allow_html=True)
        st.caption("Sources: " + " · ".join(f"[NPPA order]({u})" for u in urls[:4]))
        if x["higher"]:
            lines_out.append(f"{f.line.desc}: you paid {rupees(paid)} per tablet; NPPA-priced versions of the same combination by other companies are "
                             f"{rupees(lo)} to {rupees(hi)} before GST. Is an equivalent brand suitable? (sources: {', '.join(urls[:3])})")
    return lines_out


def eligible_for_listing(fs) -> list:
    """Tablet-type lines still missing a pack size or a printed MRP, and not looked up yet."""
    done = st.session_state.get("listings", {})
    seen, out = set(), []
    for f in fs:
        key = f.line.desc.lower()
        if (f.tier != b.TIER_NOT_MEDICINE and (f.line.unit or "").lower() in ("tab", "strip") and (not f.line.pack or not f.line.mrp)
                and key not in done and key not in seen):
            seen.add(key)
            out.append(f)
    return out


def online_check(fs, df) -> None:
    """One button: look the lines up on pharmacy websites, fill pack sizes in as SUGGESTIONS, and keep what the sites say for the cards."""
    todo = eligible_for_listing(fs)
    if not todo or not webcheck.available():
        return
    if st.button(f"Look up {len(todo)} line{'s' if len(todo) > 1 else ''} on pharmacy websites", width="stretch",
                 help="Reads the strip size and the listed price from 1mg, PharmEasy, Truemeds and Netmeds so your MRP can be checked. A listing is a reference, never the legal limit."):
        with st.spinner("Searching pharmacy websites..."):
            with ThreadPoolExecutor(max_workers=6) as ex:
                found = list(ex.map(lambda f: listings.search(f.line.desc), todo))
        book = st.session_state.setdefault("listings", {})
        guesses = st.session_state.setdefault("pack_guess", {})
        new = df.copy()
        for f, lst in zip(todo, found):
            book[f.line.desc.lower()] = lst
            if lst and lst.pack:
                for i in new.index[new["description"] == f.line.desc]:
                    if pd.isna(new.at[i, "pack"]) or not new.at[i, "pack"]:
                        new.at[i, "pack"] = lst.pack
                        guesses[f.line.desc] = (lst.pack, "pharmacy websites (" + ", ".join(x.split(".")[0] for x in lst.pack_sites) + ")")
        st.session_state.df = new
        st.session_state.load_id = st.session_state.get("load_id", 0) + 1
        st.rerun()


def listing_findings(fs) -> list[dict]:
    """What the pharmacy websites say about each looked-up line, as questions (see listings.judge)."""
    out = []
    for f in fs:
        lst = st.session_state.get("listings", {}).get(f.line.desc.lower())
        if not lst or not lst.per_tablet_max:
            continue
        printed = f.line.mrp / f.line.pack if f.line.mrp and f.line.pack else None
        verdict = listings.judge(lst, b.line_unit_price(f.line), printed)
        if verdict:
            out.append({"f": f, "lst": lst, **verdict})
    return out


def listing_cards(found: list[dict]) -> list[str]:
    lines_out = []
    for x in found:
        f, lst, ref, value = x["f"], x["lst"], x["ref"], x["value"]
        sites = ", ".join(sorted({d.split(".")[0] for d, _, _ in lst.mrp_sites}))
        if x["kind"] == "printed_above_listings":
            meta = (f"Bill prints MRP {rupees(value * (f.line.pack or 1))} per strip ({rupees(value)} per tablet) · listed online: {rupees(ref)} per tablet ({sites})")
            why = ("MRP can differ by batch and listings can lag, so this is a question, not a finding. Ask to see the MRP printed on the strip. "
                   "NPPA lets the MRP of a non-scheduled medicine rise by at most 10% a year.")
            st.markdown(ui.card("amber", f.line.desc, "Printed MRP is higher than the pharmacy-website listings", total=f"{rupees(f.line.amount)} total",
                                visual=ui.meter(value, ref, "amber", f"Bill prints {rupees(value)} per tablet", f"Listed online {rupees(ref)} ({sites})"), why=why), unsafe_allow_html=True)
            lines_out.append(f"{f.line.desc}: the bill prints an MRP of {rupees(value)} per tablet; pharmacy websites ({sites}) list {rupees(ref)}. Can I see the MRP on the strip?")
        elif x["kind"] == "charged_above_listed_mrp":
            meta = f"You paid {rupees(value)} per tablet · MRP listed online: {rupees(ref)} per tablet ({sites})"
            why = ("No MRP is printed on your bill, so we compared with the MRP the pharmacy websites list today. A seller may not charge above the MRP printed on the pack, "
                   "and an older pack usually has a lower MRP, not a higher one. This is a question: ask to see the MRP on the strip.")
            st.markdown(ui.card("amber", f.line.desc, "Above the MRP listed online", total=f"{rupees(f.line.amount)} total",
                                visual=ui.meter(value, ref, "amber", f"You paid {rupees(value)} per tablet", f"Listed MRP {rupees(ref)} ({sites})"), why=why), unsafe_allow_html=True)
            lines_out.append(f"{f.line.desc}: charged {rupees(value)} per tablet; pharmacy websites ({sites}) list an MRP of {rupees(ref)}. Can I see the MRP on the strip?")
    ok = list(dict.fromkeys(x["f"].line.desc for x in found if x["kind"] in ("agrees", "within_listed_mrp")))
    if ok:
        st.caption("Pharmacy websites list an MRP consistent with this bill for: " + ", ".join(ok) + ".")
    return lines_out


def identify(fs, confirmed):
    """Lines we are unsure about, or cannot price: the user confirms the ingredients from the strip; the web only shows evidence."""
    orders = st.session_state.setdefault("orders", {})
    todo, seen = [], set()           # one entry per distinct item: the same medicine can appear twice (two batches)
    for f in fs:
        key = f.line.desc.lower()
        if key not in seen and (f.tier in (b.TIER_NEEDS_CONFIRM, b.TIER_NO_BENCHMARK) and f.basis != "bag" or key in confirmed):
            seen.add(key)
            todo.append(f)
    if not todo:
        return
    # open once the user has worked in it: the page above re-flows after a confirmation and Streamlit would otherwise fold the box shut
    with st.expander(f"Help us identify {len(todo)} item{'s' if len(todo) > 1 else ''}", expanded=st.session_state.get("ident_open", False)):
        st.caption("These medicines could not be matched from the bill alone. Type the ingredients printed on the strip (under \"Each tablet contains\"). "
                   "We then compare the line with the government price lists and update the result above. Until you do, we make no price judgement.")
        changed = False
        for f in todo:
            key = f.line.desc.lower()
            st.markdown(f"**{f.line.desc}**")
            guess = f"Our AI guessed {f.ingredients} {f.strength}: check the strip" if f.tier == b.TIER_NEEDS_CONFIRM and f.ingredients else "e.g. bisoprolol 5 mg + telmisartan 40 mg"
            typed = st.text_input("Ingredients and strengths on the strip", key=f"salt_{key}", value=prefill(f), placeholder=guess)
            want = nppa_orders.parse_wanted(typed)
            if typed.strip() and typed.strip() != prefill(f):      # only what the user changed counts as a confirmation
                new_value = "+".join(n for n, _ in want) if want else typed.strip().lower()
                if confirmed.get(key) != new_value:
                    confirmed[key], changed = new_value, True
                    st.session_state.ident_open = True
            if key in confirmed and not changed:      # say what the confirmation did, so the section is never a dead end
                what = f"{f.ingredients} {f.strength}".strip() or confirmed[key]
                st.markdown(f"<div class='db-outcome'><b>Compared as {html.escape(what)}.</b> {html.escape(RESULT[f.tier][1])}. "
                            f"{html.escape(first_sentence(f.note))}</div>", unsafe_allow_html=True)
            elif key not in confirmed:
                st.caption("Not confirmed yet, so this line has no price judgement.")
            if want and webcheck.available():
                if st.button("See government price orders for this combination", key=f"ord_{key}",
                             help="The government sets these prices company by company. This shows what other brands of the same combination are capped at, as context. It is not a limit on your brand."):
                    with st.spinner("Searching NPPA orders..."):
                        orders[key] = (webcheck.lookup_orders(typed), typed)
                    st.session_state.ident_open = True
                    st.rerun()
                if key in orders and not orders[key][0][0]:
                    st.caption("No NPPA price order found for this exact combination and strength.")
            if webcheck.available() and st.button("Look up the ingredients online", key=f"web_{key}",
                                                  help="Reads pharmacy websites for this exact product and shows what each page says. You still confirm it against your strip."):
                with st.spinner("Searching..."):
                    st.session_state.setdefault("evidence", {})[key] = webcheck.lookup_brand(f.line.desc)
            ev = st.session_state.get("evidence", {}).get(key)
            if ev:
                st.write(ev.note)
                for src in [x for x in ev.sources if x.composition]:
                    st.markdown(f"- [{src.title or src.url}]({src.url}): {webcheck.show(src.composition)}")
                hidden = sum(1 for x in ev.sources if not x.composition)
                if hidden or ev.skipped:
                    st.caption(" ".join(filter(None, [f"{hidden} matching page{'s' if hidden != 1 else ''} did not state the composition." if hidden else "",
                                                      f"{ev.skipped} page{'s' if ev.skipped != 1 else ''} about similar-named products (a different strength or a 'Plus' version) were ignored." if ev.skipped else ""])))
                pick = ev.consensus or ev.best
                if pick and st.button(f"My strip says {webcheck.show(pick)}: use it", key=f"use_{key}"):
                    confirmed[key] = "+".join(n for n, _ in sorted(pick))
                    st.session_state.ident_open = True
                    st.rerun()
        if changed:
            st.rerun()


def briefing():
    """The prescription explainer, folded into the result: only when there is a prescription, and only on request."""
    text = st.session_state.get("rx", "")
    if not text.strip():
        return
    with st.expander("Explain my medicines in plain language"):
        dose_warning(text)
        lang = LANGS[st.segmented_control("Language", list(LANGS), default="English", label_visibility="collapsed") or "English"]
        if st.button("Explain", key="explain"):
            with st.spinner("Writing..."):
                st.session_state.briefing = (lang, pipeline.run(text, lang))
        got = st.session_state.get("briefing")
        if not got or got[0] != lang:
            return
        brief = got[1]
        L = {k: v.get(lang) or v["en"] for k, v in i18n.LABELS.items()}
        if brief.mode == "offline":
            st.caption("Offline mode: explanations are limited.")
        st.markdown(ui.callout(html.escape(i18n.explainer_note(lang, brief.explanations)), "info"), unsafe_allow_html=True)
        notes = []
        for sev, kind in (("call_doctor", "red"), ("ask_pharmacist", "amber"), ("info", "grey")):
            group = [fl for fl in brief.flags if fl.severity == sev]
            if group:          # one block per severity, one entry per distinct issue
                notes.append(ui.note(kind, i18n.SEVERITY[sev][lang], [(fl.title, fl.detail) for fl in group]))
        if notes:
            st.markdown(ui.section_label(L["safety"]) + "".join(notes), unsafe_allow_html=True)
        # The dose is built from your prescription by fixed templates, never by the model; only purpose and side effects are model text.
        st.markdown(ui.section_label(L["medicines"], len(brief.explanations)) + "".join(
            ui.med_card(e.name, e.how_to_take, L["from_rx"], e.purpose, L["watch_for"], e.watch_for) for e in brief.explanations), unsafe_allow_html=True)
        if brief.schedule:
            st.markdown(ui.section_label(L["timetable"]), unsafe_allow_html=True)
            st.table(i18n.schedule_rows(brief.schedule, lang))
            days = max([m.duration_days or 0 for m in brief.prescription.medications] or [0]) or None
            st.download_button(L["download"], scheduler.share_text(brief.schedule, days, lang), file_name="timetable.txt", key="tt_dl")
        st.markdown(ui.footer(brief.disclaimer), unsafe_allow_html=True)


# ---------------------------------------------------------------- footer
def footer():
    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    with st.expander("About, privacy and price lists"):
        dates = b.summary([])["benchmark_dates"]
        st.markdown(
            "**What this is.** Dawa Buddy compares a medicine bill with your prescription and with public price lists, then lists what to ask. "
            "It never accuses anyone, never diagnoses and is not medical advice. 'No price list' never means 'no limit exists'.\n\n"
            f"**Price lists.** NPPA legal ceilings effective {dates['nppa_ceiling']}, Jan Aushadhi prices ({dates['jan_aushadhi']}), "
            "and the MRP printed on the pack.\n\n"
            "**Privacy.** Photos are sent to Nebius Token Factory (NVIDIA Nemotron) to be read. Nothing is stored. "
            "The look-up buttons search the web for the medicine name and strength (or the ingredients you typed) only: never your photos, name or amounts. "
            "Cover your name, phone and address before uploading.")
    st.markdown(ui.footer("Information, not a finding of wrongdoing. Not medical advice."), unsafe_allow_html=True)


# ---------------------------------------------------------------- main
def main():
    stage = st.session_state.get("stage", "start")
    if stage == "start" or "df" not in st.session_state:
        start()
    elif stage == "review":
        review()
    else:
        top = st.container()
        edit = st.container()          # created after `top` so it sits below the results, but is filled first: results need its output
        with edit:
            with st.expander("Edit the numbers"):
                if st.session_state.get("sample"):
                    st.caption(f"Sample: {samples.SAMPLES[st.session_state.sample]['about']}")
                df = lines_form(st.session_state.df, "e")
                add_line()
                total = st.number_input("Total printed on the bill (optional)", value=float(st.session_state.get("total") or 0.0), key="total_e")
                st.text_area("Prescription lines (one medicine per line)", key="rx", height=120)
        with top:
            results(df, total)
    footer()


main()
