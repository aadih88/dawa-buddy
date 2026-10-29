"""Dawa Buddy: was your medicine bill fair?  Photo (or sample) -> confirm the numbers -> what to ask.

Run:  streamlit run bill_app.py
Hosting knobs: DAWA_ACCESS_CODE (visitors start locked: no model or web calls until the code is entered) and DAWA_MAX_PHOTO_READS (photo reads per browser session, default 5).
"""
import hmac
import html
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st

from dawa_buddy import bill as b, explainer, i18n, listings, llm, nppa_orders, pipeline, review_triage as rt, samples, scheduler, transparency, ui, vision, webcheck
from dawa_buddy.reader import read_prescription
from dawa_buddy.reconcile import reconcile
from dawa_buddy.report import questions

COLS = samples.COLS
LANGS = {"English": "en", "हिन्दी": "hi", "ಕನ್ನಡ": "kn"}

RED, ORANGE, AMBER, GREEN, GREY = "#d64545", "#e8883a", "#d4a017", "#2e9e6b", "#8a94a0"
# tier -> (colour, short label, group). Groups decide what is shown up front and what is folded away.
RESULT = {
    b.TIER_ABOVE_MRP: (RED, "Above the MRP on your bill", "attention"),
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
    rows, foot = transparency.reference(f, rupees, billed_word)
    return ui.card(kind, f.line.desc, RESULT[f.tier][1], total=f"{rupees(f.line.amount)} total", body=body, visual=visual, why=why,
                   why_label="How we checked this", facts_html=ui.facts(rows) if rows else "")


def msg(kind: str, text: str) -> None:
    st.markdown(ui.message(kind, text), unsafe_allow_html=True)


def reset():
    for k in list(st.session_state):
        if k != "unlocked":                   # starting another bill must not ask for the access code again
            del st.session_state[k]


def access_gate() -> bool:
    """Until the access code is entered, every model and web call is switched off for this visitor (the sample bills and all price checks still work).
    No DAWA_ACCESS_CODE set (local use, development): no gate. This is what keeps a leaked link from spending the model credits."""
    code = os.environ.get("DAWA_ACCESS_CODE", "")
    unlocked = not code or bool(st.session_state.get("unlocked"))
    llm.restrict(not unlocked)
    return unlocked


def unlock_box() -> None:
    code = os.environ.get("DAWA_ACCESS_CODE", "")
    if not code or st.session_state.get("unlocked"):
        return
    st.markdown(ui.message("grey", "Photo reading, AI explanations and web look-ups are switched on with an access code (given to the hackathon judges). "
                                   "The sample bills and every price check work without it."), unsafe_allow_html=True)
    with st.expander("I have an access code"):
        with st.form("unlock", border=False):
            entered = st.text_input("Access code", type="password")
            go = st.form_submit_button("Unlock", type="primary")
        if go and hmac.compare_digest(entered.strip().encode(), code.encode()):
            st.session_state.unlocked = True
            st.rerun()
        elif go:
            time.sleep(1.5)                   # a wrong guess costs time, so the code cannot be guessed quickly
            st.caption("That code is not right.")


# ---------------------------------------------------------------- screen 1: start
def start():
    st.markdown(ui.header(), unsafe_allow_html=True)
    st.title("Was your medicine bill fair?")
    st.markdown("<p class='db-sub'>Photograph your bill. We compare it with government price lists and your prescription, "
                "and tell you what to ask.</p>", unsafe_allow_html=True)
    pending = st.session_state.pop("start_msg", None)       # an error from the last read, shown once
    if pending:
        msg(*pending)
    unlock_box()
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
    st.session_state.update(df=enrich(df), rx=rx, total=total, stage="review", photo_reads=reads, load_id=1,
                            line_notes={r.description: list(r.notes) for r in rows})
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


def refresh_lines(df: pd.DataFrame) -> None:
    """Replace the bill lines (after a lookup or when moving on): new widget keys, and the per-line edit bookkeeping that belonged to the old ones is dropped."""
    st.session_state.df = df
    st.session_state.load_id = st.session_state.get("load_id", 0) + 1
    for name in ("removed", "edits", "memo", "ver"):
        st.session_state.pop(name, None)


def calc_text(qty, rate, amount) -> str:
    return f"{qty:g} × {rupees(rate)} = {rupees(amount)}"


def flag(v) -> bool:
    """A yes/no cell of the table: a missing one (None or NaN, which is truthy) is a no."""
    return False if v is None or (isinstance(v, float) and pd.isna(v)) else bool(v)


def needs_strip_size(unit, mrp, pack, mrp_each=False) -> bool:
    """Tablets per strip are needed only to convert: a per-strip MRP against a per-tablet price, or a per-strip price into a per-tablet one. A per-tablet MRP on a
    per-tablet price needs no strip size at all."""
    return (unit == "strip" and not pack) or (unit == "tab" and bool(mrp) and not mrp_each and not pack)


MRP_BASIS = {"tab": "one tablet", "strip": "a whole strip"}


def readout(unit, rate, mrp, mrp_each, pack) -> str:
    """What the numbers on the card mean, in one sentence, recomputed whenever the choices change: it is the visible effect of choosing per tablet or per strip."""
    if unit not in ("tab", "strip"):
        return ""
    paid, mrp_t = b.per_tablet_view(unit, rate, mrp, mrp_each, pack)
    sold = f"You paid {rupees(rate)} per {'tablet' if unit == 'tab' else 'strip'}"
    if unit == "strip":
        sold += f" ({rupees(paid)} per tablet)" if paid else " (the price per tablet needs the tablets per strip)"
    if not mrp:
        return sold + "."
    m = f"MRP on the bill {rupees(mrp)} for {'one tablet' if mrp_each else 'a whole strip'}"
    m += f" ({rupees(mrp_t)} per tablet)" if (mrp_t and not mrp_each) else (f" ({rupees(mrp * pack)} per strip)" if mrp_each and pack else "")
    return f"{sold}. {m}."


def lines_form(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    """One card per bill line: what we read (to compare with the paper), how it was sold, pack size, and a popover to fix a number.
    Edits are STAGED in a small form and apply only on 'Save changes'; the total is always quantity x price; a removed line goes to 'Removed lines' and can be put back."""
    guesses = st.session_state.get("pack_guess", {})
    removed = st.session_state.setdefault("removed", set())
    edits, memo, ver = (st.session_state.setdefault(n, {}) for n in ("edits", "memo", "ver"))
    trash = st.session_state.setdefault("trash", [])
    rows = []
    for i, r in enumerate(df.to_dict("records")):
        k = f"{scope}{st.session_state.get('load_id', 0)}_{i}"
        if k in removed:
            continue
        ed = edits.get(k, {})
        name, qty, rate, mrp = ed.get("name", str(r["description"])), ed.get("qty", num(r["qty"])), ed.get("rate", num(r["rate"])), ed.get("mrp", num(r["mrp"]))
        amount = ed.get("amount", num(r["amount"]))
        mismatch = abs(qty * rate - amount) > max(0.51, 0.005 * amount)
        unit_default = memo.get(k, {}).get("unit", r["unit"] if r["unit"] in UNIT_LABEL else None)
        status, why = rt.line_status(qty, rate, amount, unit_default, bool(r.get("unsure")), st.session_state.get("line_notes", {}).get(str(r["description"]), []))
        # a line whose numbers multiply out and that needed no guess is approved by looking at one row; the rest open so the eyes go where they are needed
        shell = st.expander(f"✓ {name}: {calc_text(qty, rate, amount)}", expanded=False) if status == rt.OK else st.container(border=True, key=f"card_{k}")
        with shell:
            if status != rt.OK:
                st.markdown(ui.line_head(name, calc_text(qty, rate, amount), f"MRP on bill {rupees(mrp)}" if mrp else "", bool(r.get("unsure")), mismatch), unsafe_allow_html=True)
                st.markdown(ui.message("red" if status == rt.FIX else "amber", why), unsafe_allow_html=True)
            unit = st.segmented_control("Sold", unit_options(r), format_func=UNIT_LABEL.get, key=f"{k}_unit", label_visibility="collapsed", default=unit_default)
            if unit is None:
                st.markdown(ui.need("How was this sold? Choose one so we can compare the price."), unsafe_allow_html=True)
            pack = ed.get("pack", memo.get(k, {}).get("pack", num(r["pack"]) if r.get("pack") is not None and not pd.isna(r.get("pack")) else 0.0)) or None
            g = guesses.get(str(r["description"]))
            mrp_each = False
            if mrp and unit in ("tab", "strip"):
                # which way the bill's MRP is printed is its own fact: per tablet (MRP/Unit) or per whole strip. It is not the same question as how the line was sold.
                basis = st.segmented_control("MRP on the bill is for", list(MRP_BASIS), format_func=MRP_BASIS.get, key=f"{k}_mb", default=memo.get(k, {}).get("basis", "tab" if flag(r.get("mrp_each")) else "strip"))
                mrp_each = basis == "tab"
            else:
                basis = None
            if unit in ("tab", "strip"):
                st.caption(readout(unit, rate, mrp, mrp_each, pack or 0))
                if g and pack and pack == g[0]:
                    st.caption(f"Strip size of {g[0]:g} suggested from {g[1]}. Check it on your strip.")
            if needs_strip_size(unit, mrp, pack, mrp_each):
                st.markdown(ui.need("Needed: the tablets per strip, to compare a tablet price with a strip price. Enter it under “Fix a number”" + (f" (suggested {g[0]:g} from {g[1]}: check your strip)" if g else "") + "."), unsafe_allow_html=True)
            memo[k] = {"unit": unit, "pack": pack or 0.0, "basis": basis}
            with st.popover("Fix a number", width="stretch"):
                v = ver.get(k, 0)
                with st.form(f"fix_{k}_{v}", border=False):         # nothing changes until the user presses Save
                    new_name = st.text_input("Item", value=name, key=f"{k}_fn{v}")
                    c1, c2 = st.columns(2)
                    new_qty = c1.number_input("Quantity", min_value=0.0, value=float(qty), key=f"{k}_fq{v}")
                    new_rate = c2.number_input("Price each (₹)", min_value=0.0, value=float(rate), step=0.01, key=f"{k}_fr{v}")
                    new_mrp = st.number_input("MRP printed on the bill (optional)", min_value=0.0, value=float(mrp), step=0.01, key=f"{k}_fm{v}")
                    new_pack = st.number_input(PACK_LABEL.get(unit, "Tablets per strip"), min_value=0.0, step=1.0, value=float(pack or 0), key=f"{k}_fp{v}",
                                               help="From the strip or box. Only needed to convert between a tablet price and a strip price.")
                    st.caption("The total is worked out as quantity × price.")
                    saved = st.form_submit_button("Save changes", type="primary")
                if saved:
                    edits[k] = {"name": new_name.strip() or name, "qty": new_qty, "rate": new_rate, "mrp": new_mrp, "pack": new_pack,
                                "amount": round(new_qty * new_rate, 2) if (new_qty, new_rate) != (qty, rate) else amount}
                    ver[k] = v + 1
                    st.rerun()
                if st.button("Remove this line", key=f"{k}_rm", help="It goes to “Removed lines” below, where you can put it back."):
                    removed.add(k)
                    trash.append({"k": k, "row": {"description": name, "qty": qty, "rate": rate, "amount": amount, "unit": unit, "pack": pack or None,
                                                  "mrp": mrp or None, "unsure": bool(r.get("unsure")), "mrp_each": mrp_each}})
                    st.rerun()
        rows.append({"description": name, "qty": qty, "rate": rate, "amount": amount, "unit": unit, "pack": (pack or None),
                     "mrp": (mrp or None), "unsure": bool(r.get("unsure")), "mrp_each": mrp_each})
    if trash:
        with st.expander(f"Removed lines ({len(trash)})"):
            for j, t in enumerate(list(trash)):
                c1, c2 = st.columns([3, 2], vertical_alignment="center")
                c1.markdown(f"**{t['row']['description']}**  \n{calc_text(t['row']['qty'], t['row']['rate'], t['row']['amount'])}")
                if c2.button("Put back", key=f"undo_{scope}_{j}_{t['k']}", width="stretch"):
                    trash.pop(j)
                    if t["k"] in removed:                  # still in the table, only hidden
                        removed.discard(t["k"])
                    else:                                  # the table was rebuilt since: add the row again
                        st.session_state.df = pd.DataFrame(df.to_dict("records") + [t["row"]], columns=df.columns)
                    st.rerun()
    return pd.DataFrame(rows, columns=COLS)


def add_line():
    with st.popover("Add a line we missed", width="stretch"):
        v = st.session_state.get("add_ver", 0)
        with st.form(f"add_{v}", border=False):
            name = st.text_input("Item name, as printed", key=f"new_name{v}")
            c1, c2 = st.columns(2)
            qty = c1.number_input("Quantity", min_value=0.0, value=1.0, key=f"new_qty{v}")
            rate = c2.number_input("Price each (₹)", min_value=0.0, step=0.01, key=f"new_rate{v}")
            mrp = st.number_input("MRP printed on the bill (optional)", min_value=0.0, step=0.01, key=f"new_mrp{v}")
            st.caption("The total is worked out as quantity × price. Choose how it was sold on its card afterwards.")
            added = st.form_submit_button("Add this line", type="primary")
        if added and (not name.strip() or qty <= 0 or rate <= 0):
            st.caption("Give the item a name, a quantity and a price first.")
        elif added:
            row = {"description": name.strip(), "qty": qty, "rate": rate, "amount": round(qty * rate, 2), "unit": None, "pack": None, "mrp": mrp or None, "unsure": False, "mrp_each": False}
            st.session_state.df = pd.DataFrame(st.session_state.df.to_dict("records") + [row], columns=st.session_state.df.columns)
            st.session_state.add_ver = v + 1
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


def review_gaps(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """One amber note at the top for the numbers a line still needs before it can be checked, with a button to find strip sizes online right where they are needed."""
    blank = lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else v          # a missing number reaches us as NaN, which is truthy
    recs = [{**r, "unit": blank(r["unit"]), "pack": blank(r["pack"]), "mrp": blank(r["mrp"]), "mrp_each": flag(r.get("mrp_each"))} for r in df.to_dict("records")]
    no_unit = [r["description"] for r in recs if not r["unit"]]
    no_pack = [r for r in recs if needs_strip_size(r["unit"], r["mrp"], r["pack"], r["mrp_each"])]
    items = ([(d, "Choose how it was sold (per tablet, per strip…): we cannot compare the price without it.") for d in no_unit]
             + [(r["description"], f"Enter the tablets per strip: the MRP of {rupees(r['mrp'])} on your bill is for a whole strip." if r["mrp"]
                 else "Enter the tablets per strip, to turn the strip price into a price per tablet.") for r in no_pack])
    if items:
        n = len(items)
        st.markdown(ui.note("amber", f"{n} line{'s need' if n > 1 else ' needs'} a number before we can check {'them' if n > 1 else 'it'}", items,
                            foot="Until then the line gets no price judgement and its printed MRP cannot be checked."), unsafe_allow_html=True)
    asked = st.session_state.get("listings", {})
    todo = [r["description"] for r in no_pack if r["description"].lower() not in asked]
    if todo and webcheck.available():
        names = ", ".join(dict.fromkeys(todo))
        if st.button(f"Find strip sizes online for {names}", key="find_strips", type="primary", width="stretch",
                     help="Reads the strip size from pharmacy websites and fills it in as a suggestion. Check it against your strip before continuing."):
            run_listing_lookup(df, list(dict.fromkeys(todo)))
    return no_unit, [r["description"] for r in no_pack]


def review():
    st.markdown(ui.header(2, "Step 2 of 3 · Check the numbers"), unsafe_allow_html=True)
    st.title("Check the numbers")
    st.markdown("<p class='db-sub'>Lines that read correctly are folded up: open only the ones that need a look. You approve the numbers; nothing is judged before that.</p>", unsafe_allow_html=True)
    if st.session_state.get("sample"):
        st.caption(f"Sample: {samples.SAMPLES[st.session_state.sample]['about']}")
    unclear = dose_warning(st.session_state.get("rx", ""))      # first: it is the thing most likely to be missed, so it must not sit below six cards
    top = st.container()                                        # filled after the cards are drawn: the note depends on what the cards now say
    df = lines_form(st.session_state.df, "r")
    add_line()
    total = st.number_input("Total printed on the bill (optional)", value=float(st.session_state.get("total") or 0.0))
    with st.expander("Prescription lines", expanded=unclear):
        st.text_area("One medicine per line, as written", key="rx", height=130, label_visibility="collapsed")
    notes = st.session_state.get("line_notes", {})
    sts = [rt.line_status(r["qty"], r["rate"], r["amount"], r["unit"] if r["unit"] in UNIT_LABEL else None, bool(r.get("unsure")), notes.get(str(r["description"]), []))[0]
           for r in df.to_dict("records")]
    tie, line_sum = rt.bill_tie(df["amount"].tolist(), total)
    sm = rt.summary(sts)
    all_clear = sm[rt.FIX] == 0 and sm[rt.CHECK] == 0 and tie != "mismatch"
    with top:
        n = sm["lines"]
        head = f"{n} line{'s' if n != 1 else ''} read." + (f" {sm[rt.FIX]} need{'s' if sm[rt.FIX] == 1 else ''} a correction." if sm[rt.FIX] else "") + \
               (f" {sm[rt.CHECK]} to compare with your paper." if sm[rt.CHECK] else "") + (" Every line multiplies out." if all_clear or (not sm[rt.FIX] and not sm[rt.CHECK]) else "")
        tie_text = {"match": f" The lines add up to the printed total, {rupees(total)}.", "none": "",
                    "mismatch": f" The lines add up to {rupees(line_sum)} but the total on the bill is {rupees(total)}: look at the open lines."}[tie]
        st.markdown(ui.message("green" if all_clear else "red" if sm[rt.FIX] else "amber", head + tie_text), unsafe_allow_html=True)
        no_unit, no_pack = review_gaps(df)
    checking = st.session_state.get("checking", False)
    if no_unit or no_pack:
        parts = ([f"{len(no_pack)} line{'s' if len(no_pack) > 1 else ''} will not be checked against {'their' if len(no_pack) > 1 else 'its'} printed MRP"] if no_pack else []) \
              + ([f"{len(no_unit)} line{'s' if len(no_unit) > 1 else ''} will get no price judgement"] if no_unit else [])
        st.caption(" and ".join(parts) + " until the numbers above are filled in. You can still continue.")
    if st.button("Looks right, see the result" if all_clear else "See the result", type="primary", width="stretch", disabled=checking):
        st.session_state.checking = True
        st.rerun()
    if st.button("Start over", width="stretch", disabled=checking):
        reset(); st.rerun()
    if checking:
        with st.spinner("Checking prices..."):
            refresh_lines(df)
            st.session_state.update(total=total, stage="results", checking=False)
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


def check_rows(fs, flags, wrong, unidentified, generic, listed_ok: int = 0, looked_up: bool = False) -> list[tuple[str, str, str]]:
    """'What we checked': what was verified and found fine, what was not and why. Each row says what was done, so a clean bill reads as protection."""
    n = len(fs)
    plural = lambda k, word: f"{k} {word}{'' if k == 1 else 's'}"
    over_fs = [f for f in fs if f.tier == b.TIER_ABOVE_MRP]
    over = len(over_fs)
    known = sum(f.mrp_pct is not None or f.tier == b.TIER_ABOVE_MRP for f in fs)
    ok = known - over
    rest = n - known
    gap = f"{plural(rest, 'line')} could not be compared because the MRP or the strip size is missing." if rest else ""
    named = lambda items: "; ".join(items[:3]) + (f"; and {len(items) - 3} more" if len(items) > 3 else "")
    rows = []
    if over:     # name the line and both prices, so the reader can see what is wrong without opening anything
        what = named([f"{f.line.desc}: charged {rupees(f.line.rate)} per {billed_word(f.line.unit)}, the MRP on the bill is {rupees(f.mrp_unit)}" for f in over_fs])
        rows.append(("red", "MRP on your bill", f"{plural(over, 'line')} {'is' if over == 1 else 'are'} priced above the MRP printed on the bill. {what}."
                     + (f" {plural(ok, 'other line')} {'is' if ok == 1 else 'are'} priced at or below {'its' if ok == 1 else 'their'} MRP." if ok else "")
                     + (f" {gap}" if gap else "")))
    elif ok:
        rows.append(("green", "MRP on your bill", ("All " + plural(n, "line") + " are" if ok == n and n > 1 else "This line is" if ok == n else f"{ok} of {n} lines are")
                     + " priced at or below the MRP printed on the bill. That MRP is the seller's own figure, so it proves the bill agrees with itself, not that the MRP is right: "
                     + (f"pharmacy websites list a consistent MRP for {plural(listed_ok, 'line')}; compare the strip for the rest." if listed_ok else
                        "we found no pharmacy-website listing to compare." if looked_up else "compare the MRP on each strip with the bill.")
                     + (f" {gap}" if gap else "")))
    else:
        rows.append(("grey", "MRP on your bill", "Could not be compared: add the MRP printed on the bill and the tablets per strip (Edit the numbers)."))
    capped = [f for f in fs if f.ceiling is not None]
    above_fs = [f for f in fs if f.tier == b.TIER_ABOVE_CEILING]
    if above_fs:
        what = named([f"{f.line.desc}: charged {rupees(f.unit_price)} per {PER.get(f.basis, 'unit')}, the legal limit is {rupees(f.ceiling)}" for f in above_fs])
        rows.append(("red", "Legal price ceiling (NPPA)", f"{len(above_fs)} of {plural(len(capped), 'price-controlled line')} {'is' if len(above_fs) == 1 else 'are'} above the legal ceiling price. {what}."))
    elif capped:
        rows.append(("green", "Legal price ceiling (NPPA)", ("The price-controlled line is" if len(capped) == 1 else f"All {len(capped)} price-controlled lines are") + " within the legal ceiling price."))
    else:
        rows.append(("grey", "Legal price ceiling (NPPA)", "Not applicable: none of these has a government ceiling. That is normal, since most branded medicines are not price-controlled."))
    if not st.session_state.get("rx", "").strip():
        rows.append(("grey", "Your prescription", "None added. Add one to check you were given the medicines the doctor wrote."))
    elif not flags:
        rows.append(("green", "Your prescription", "The bill matches your prescription: same products, no extras, no missing items."))
    else:
        rows.append(("red" if wrong else "amber", "Your prescription", f"{plural(len(flags), 'difference')} from the prescription, listed below."))
    mild = [f.line.desc for f in fs if f.tier == b.TIER_OK and mild_generic(f)]
    mild_text = (f" {plural(len(mild), 'other line' if generic else 'line')} {'has' if len(mild) == 1 else 'have'} a generic listed too, but under {b.GENERIC_GAP_RATIO:g}× the price, "
                 "so not flagged: " + named(mild) + ".") if mild else ""
    if generic:
        k = sum(f.tier == b.TIER_GENERIC_GAP for f in fs)
        rows.append(("amber", "Cheaper generics", f"A cheaper generic may exist for {plural(k, 'line')} (about {rupees(generic)}). Ask your doctor before switching." + mild_text))
    elif mild:
        rows.append(("grey", "Cheaper generics", f"None flagged (we flag a generic at {b.GENERIC_GAP_RATIO:g}× the price or more)." + mild_text))
    if unidentified:
        rows.append(("amber", "Medicines to confirm", f"{plural(len(unidentified), 'medicine')} not identified yet: {', '.join(unidentified)}. Confirm them under “Help us identify”."))
    return rows


def mild_generic(f) -> bool:
    """A line inside every limit whose generic is still clearly cheaper, but under the ratio at which a generic is flagged."""
    return bool(f.generic_unit and f.unit_price and b.GENERIC_MENTION_RATIO * f.generic_unit <= f.unit_price < b.GENERIC_GAP_RATIO * f.generic_unit)


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
        mrp = f" Charged {f.mrp_pct:.0f}% of the MRP on your bill (that MRP is the seller's own figure: compare it with the strip)." if f.mrp_pct is not None else ""
        why = f"<br><span class='small'>{html.escape(known + reason + mrp)}</span>"
    elif f.mrp_pct is not None and f.tier == b.TIER_OK:
        why = f"<br><span class='small'>Charged {f.mrp_pct:.0f}% of the MRP on your bill.</span>"
    if f.tier == b.TIER_OK and mild_generic(f):          # inside the limits, yet a generic is cheaper: say so, and why it was not flagged
        why += (f"<br><span class='small'>A Jan Aushadhi generic is listed at {rupees(f.generic_unit)} per {PER.get(f.basis, 'unit')}; you paid "
                f"{f.unit_price / f.generic_unit:.1f}× that. We flag a generic only at {b.GENERIC_GAP_RATIO:g}× or more.</span>")
    rows, foot = transparency.reference(f, rupees, billed_word)
    how = f"<details class='how'><summary>How we checked this</summary>{ui.facts(rows)}</details>" if len(rows) > 1 else ""
    return f"<div class='minibox'><div class='mini'><span class='l'>{html.escape(f.line.desc)}<br><span class='small'>{label}</span>{why}</span><span class='r'>{right}</span></div>{how}</div>"


def needs_identifying(f) -> bool:
    """The ONE rule for 'this medicine needs the user to say what it is': an AI or brand-table guess waiting for confirmation, or a line we could not match at all.
    A medicine we did identify (say, from the brand table) but that no price list covers is not here: there is nothing for the user to confirm.
    The checklist row, the 'Please confirm' cards and the 'Help us identify' list all use this, so they can never disagree."""
    return f.basis != "bag" and (f.tier == b.TIER_NEEDS_CONFIRM or (f.tier == b.TIER_NO_BENCHMARK and not f.ingredients))


def results(df, total):
    confirmed = st.session_state.setdefault("confirmed", {})
    rows = [vision.Row(**{k: (None if pd.isna(v) else v) for k, v in rec.items() if k in COLS}) for rec in df.to_dict("records")]
    lines = vision.rows_to_lines(rows)
    fs = [b.audit_line(l, confirmed) for l in lines]
    if webcheck.available() and not st.session_state.get("auto_listed") and not st.session_state.get("sample"):
        # The MRP on a bill is the seller's own figure; pharmacy websites are the only independent check on it. Look them up once, without a button the patient
        # has to understand. Not for the samples (their results must not change from one run to the next) and not for a locked visitor (webcheck is off then).
        st.session_state.auto_listed = True
        todo = eligible_for_listing(fs, everything=True)[:6]
        if todo:
            run_listing_lookup(df, [f.line.desc for f in todo])
    tot = sum(f.line.amount for f in fs) or 1
    s = b.summary(fs)
    group = lambda g: sorted([f for f in fs if RESULT[f.tier][2] == g], key=lambda f: list(RESULT).index(f.tier))
    attention, fine, unchecked = group("attention"), group("fine"), group("unchecked")
    mrp_only = [f for f in unchecked if f.mrp_pct is not None]               # no price list covers them: the only comparison is the bill's own MRP
    unchecked = [f for f in unchecked if f.mrp_pct is None]
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
    unidentified = [f.line.desc for f in {f.line.desc.lower(): f for f in fs if needs_identifying(f)}.values()]
    verdict(n_viol_total, n_ask, s["possible_saving_above_ceiling"] + s["possible_saving_above_mrp"], s["possible_saving_generic"])
    listed_ok = len({x["f"].line.desc.lower() for x in listed if x["kind"] in ("agrees", "within_listed_mrp")})
    st.markdown(ui.checks(check_rows(fs, flags, wrong, unidentified, s["possible_saving_generic"], listed_ok, bool(st.session_state.get("listings")))), unsafe_allow_html=True)

    needs_pack = [f for f in fs if f.line.mrp and f.mrp_unit is None and (f.line.unit or "").lower() in ("tab", "strip") and not f.line.pack]
    if needs_pack and not (webcheck.available() and eligible_for_listing(fs)):
        st.caption(f"Tip: {len(needs_pack)} line{'s have' if len(needs_pack) > 1 else ' has'} a printed MRP but no tablets-per-strip, so the MRP could "
                   "not be checked. Add it under “Edit the numbers”.")

    n_cards = len(wrong) + len(attention) + sum(x["higher"] for x in peer_found) + len(flagged_listings)
    if n_cards:
        st.markdown(ui.section_label("Ask about these", n_cards), unsafe_allow_html=True)
    for x in wrong:        # a possibly wrong medicine matters more than any price, so it comes first
        prescribed, billed = x.subject.split(" -> ")
        shown = re.search(r"different product\.\s*((?:Ingredients differ|Same ingredients).*?)\s*Ask the pharmacist", x.note)         # how they differ is the point of this card: not behind a tap
        st.markdown(ui.card("red", billed, "Check before taking", body=shown.group(1) if shown else "", visual=ui.diff(prescribed, billed), why=x.note), unsafe_allow_html=True)
    for f in attention:
        st.markdown(finding_html(f), unsafe_allow_html=True)
    peers = peer_cards(peer_found)
    online = listing_cards(listed)

    if any(transparency.reference(f, rupees, billed_word)[1] for f in fs):
        st.caption(transparency.CEILING_NOTE)                  # said once for the page: the same sentence under every card is noise
    if fine:
        with st.expander(f"Within the limits ({len(fine)})"):
            st.markdown("".join(mini(f) for f in fine), unsafe_allow_html=True)
    if mrp_only:
        with st.expander(f"Checked only against the MRP on your bill ({len(mrp_only)})"):
            st.markdown("".join(mini(f) for f in mrp_only), unsafe_allow_html=True)
            st.caption("No government or generic price applies to these. The MRP is the seller's own figure: compare it with the one on each strip.")
    if unchecked:
        with st.expander(f"Not covered by a price list ({len(unchecked)})"):
            st.markdown("".join(mini(f) for f in unchecked), unsafe_allow_html=True)
            if s["no_price_control_value"]:
                st.caption(f"Supplements have no government price limit; only the MRP limits them (compare the strip with your bill).")
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


def eligible_for_listing(fs, everything: bool = False) -> list:
    """Tablet-type lines still missing a pack size or a printed MRP, and not looked up yet. `everything` drops the 'missing' condition: the websites are also
    the only independent check on an MRP the bill prints, so a line whose MRP is present is worth looking up too."""
    done = st.session_state.get("listings", {})
    seen, out = set(), []
    for f in fs:
        key = f.line.desc.lower()
        if (f.tier != b.TIER_NOT_MEDICINE and (f.line.unit or "").lower() in ("tab", "strip") and (everything or not f.line.pack or not f.line.mrp)
                and key not in done and key not in seen):
            seen.add(key)
            out.append(f)
    return out


def run_listing_lookup(df: pd.DataFrame, descs: list[str]) -> None:
    """Read pharmacy websites for these bill lines, fill pack sizes in as SUGGESTIONS, and keep what the sites say for the result cards."""
    with st.spinner("Searching pharmacy websites..."):
        with ThreadPoolExecutor(max_workers=6) as ex:
            found = list(ex.map(listings.search, descs))
    book = st.session_state.setdefault("listings", {})
    guesses = st.session_state.setdefault("pack_guess", {})
    new = df.copy()
    for d, lst in zip(descs, found):
        book[d.lower()] = lst
        if lst and lst.pack:
            for i in new.index[new["description"] == d]:
                if pd.isna(new.at[i, "pack"]) or not new.at[i, "pack"]:
                    new.at[i, "pack"] = lst.pack
                    guesses[d] = (lst.pack, "pharmacy websites (" + ", ".join(x.split(".")[0] for x in lst.pack_sites) + ")")
    refresh_lines(new)
    st.rerun()


def online_check(fs, df) -> None:
    """Tell the user what the look-up is for and which medicines it covers, then one button."""
    todo = eligible_for_listing(fs)
    if not todo or not webcheck.available():
        return
    names = ", ".join(html.escape(f.line.desc) for f in todo)
    st.markdown(ui.callout(f"<b>Strip size and listed price</b> can be read from pharmacy websites for: {names}. "
                           "That lets us check the MRP printed on your bill against what the sites list. A listing is a reference, never the legal limit.", "search"),
                unsafe_allow_html=True)
    if st.button(f"Look up {len(todo)} line{'s' if len(todo) > 1 else ''} on pharmacy websites", type="primary", width="stretch", key="listing_lookup",
                 help="Reads the strip size and the listed price from 1mg, PharmEasy, Truemeds and Netmeds so your MRP can be checked."):
        run_listing_lookup(df, [f.line.desc for f in todo])


def listing_findings(fs) -> list[dict]:
    """What the pharmacy websites say about each looked-up line, as questions (see listings.judge)."""
    out = []
    for f in fs:
        lst = st.session_state.get("listings", {}).get(f.line.desc.lower())
        if not lst or not lst.per_tablet_max:
            continue
        printed = b.mrp_per_tablet(f.line) if f.line.mrp else None
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
    """Lines we are unsure about, or cannot price: the user confirms the ingredients from the strip; the web only shows evidence.
    One collapsible row per medicine (the list stays short however many there are); a button that has done its job is disabled for the session."""
    orders = st.session_state.setdefault("orders", {})
    todo, seen = [], set()           # one entry per distinct item: the same medicine can appear twice (two batches)
    for f in fs:
        key = f.line.desc.lower()
        if key not in seen and (needs_identifying(f) or key in confirmed):
            seen.add(key)
            todo.append(f)
    if not todo:
        return
    pending = sum(f.line.desc.lower() not in confirmed for f in todo)
    if pending:        # the badge counts only what still needs the user: a number next to "Help us identify" means there is something to do
        st.markdown(ui.section_label("Help us identify", pending), unsafe_allow_html=True)
        st.caption("These medicines could not be matched from the bill alone. Open one and type the ingredients printed on the strip (under \"Each tablet contains\"). "
                   "We then compare the line with the government price lists and update the result above. Until you do, we make no price judgement.")
    else:              # nothing left to do, but the answers stay visible and changeable (a typo must not be permanent)
        st.markdown(ui.section_label("Medicines you confirmed", len(todo)), unsafe_allow_html=True)
        st.caption("Nothing more to do here. Open a row to review or change what you confirmed.")
    texts = st.session_state.setdefault("ident_text", {})          # what the user confirmed for each medicine, in their own words
    for f in todo:
        key = f.line.desc.lower()
        is_confirmed = key in confirmed
        editing = st.session_state.get(f"edit_{key}", False)
        status = "confirmed" if is_confirmed else "needs your confirmation"
        # the row the user last worked in stays open: the page above re-flows after a confirmation and Streamlit would otherwise fold it shut
        with st.expander(f"{f.line.desc} · {status}", expanded=st.session_state.get("ident_open") == key):
            if not is_confirmed or editing:
                guess = f"Our AI guessed {f.ingredients} {f.strength}: check the strip" if f.tier == b.TIER_NEEDS_CONFIRM and f.ingredients else "e.g. bisoprolol 5 mg + telmisartan 40 mg"
                with st.form(f"form_{key}", border=False):         # a form, so there is a visible button to press (a bare text box only applies on Enter)
                    typed = st.text_input("Ingredients and strengths on the strip", key=f"salt_{key}", value=texts.get(key) or prefill(f), placeholder=guess)
                    submitted = st.form_submit_button("Confirm ingredients", type="primary")
                if submitted and not typed.strip():
                    st.caption("Type the ingredients printed on the strip first.")
                elif submitted:                                    # pressing the button is the user's confirmation, even of a value we suggested from the brand table
                    want = nppa_orders.parse_wanted(typed)
                    confirmed[key] = "+".join(n for n, _ in want) if want else typed.strip().lower()
                    texts[key] = typed.strip()
                    st.session_state[f"edit_{key}"] = False
                    st.session_state.ident_open = key
                    st.rerun()
                if not is_confirmed:
                    st.caption("Not confirmed yet, so this line has no price judgement.")
            else:                                                  # confirmed: the box gives way to what was confirmed, and what it did
                what = f"{f.ingredients} {f.strength}".strip() or confirmed[key]
                st.markdown(f"<div class='db-outcome'><b>Compared as {html.escape(what)}.</b> {html.escape(RESULT[f.tier][1])}. "
                            f"{html.escape(first_sentence(f.note))}</div>", unsafe_allow_html=True)
                if st.button("Change ingredients", key=f"chg_{key}", type="primary"):
                    st.session_state[f"edit_{key}"] = True
                    st.session_state.ident_open = key
                    st.rerun()
                text = texts.get(key, "")
                if nppa_orders.parse_wanted(text) and webcheck.available():
                    done = key in orders and orders[key][1] == text          # already searched for exactly this: nothing new to get from pressing again
                    if st.button("Government price orders shown below" if done and orders[key][0][0] else "Searched: no price order found" if done else
                                 "See government price orders for this combination", key=f"ord_{key}", disabled=done,
                                 help="The government sets these prices company by company. This shows what other brands of the same combination are capped at, as context. It is not a limit on your brand."):
                        with st.spinner("Searching NPPA orders..."):
                            orders[key] = (webcheck.lookup_orders(text), text)
                        st.session_state.ident_open = key
                        st.rerun()
            if webcheck.available() and (not is_confirmed or editing):    # once confirmed there is nothing left to look up
                looked = st.session_state.get("evidence", {}).get(key) is not None
                if st.button("Looked up online (see below)" if looked else "Look up the ingredients online", key=f"web_{key}", disabled=looked,
                             help="Reads pharmacy websites for this exact product and shows what each page says. You still confirm it against your strip."):
                    with st.spinner("Searching..."):
                        st.session_state.setdefault("evidence", {})[key] = webcheck.lookup_brand(f.line.desc, b.form_of_desc(f.line.desc))
                    st.session_state.ident_open = key
                    st.rerun()
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
                if pick:
                    answer = "+".join(n for n, _ in sorted(pick))
                    used = confirmed.get(key) == answer
                    if st.button(f"Using: {webcheck.show(pick)}" if used else f"My strip says {webcheck.show(pick)}: use it", key=f"use_{key}", disabled=used):
                        confirmed[key], texts[key] = answer, webcheck.show(pick)
                        st.session_state[f"edit_{key}"] = False
                        st.session_state.ident_open = key
                        st.rerun()


def briefing():
    """The prescription explainer, folded into the result: only when there is a prescription, and only on request."""
    text = st.session_state.get("rx", "")
    if not text.strip():
        return
    st.markdown(ui.section_label("Understand your prescription"), unsafe_allow_html=True)      # its own section: otherwise it reads as one more row of the list above
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
            st.caption("AI text is switched off without the access code: the dose, safety notes and timetable below come from fixed templates and are complete."
                       if llm.restricted() else "Offline mode: explanations are limited.")
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
            daily = [i for i in brief.schedule if i.slot != "once"]
            once = [i for i in brief.schedule if i.slot == "once"]
            if daily:
                st.markdown(ui.section_label(L["timetable"]), unsafe_allow_html=True)
                st.table(i18n.schedule_rows(daily, lang))
            if once:           # a vaccine or any single dose is not part of a daily routine: shown apart, never as a row of the table
                st.markdown(ui.section_label(L["one_time"]) + "".join(ui.card("grey", i.med, i.instruction, icon_name="check") for i in once), unsafe_allow_html=True)
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
            "and the MRP printed on your bill (the seller's own figure, checked against pharmacy-website listings where we can).\n\n"
            "**Privacy.** Photos are sent to Nebius Token Factory (NVIDIA Nemotron) to be read. Nothing is stored. "
            "The look-up buttons search the web for the medicine name and strength (or the ingredients you typed) only: never your photos, name or amounts. "
            "Cover your name, phone and address before uploading.")
    st.markdown(ui.footer("Information, not a finding of wrongdoing. Not medical advice."), unsafe_allow_html=True)


# ---------------------------------------------------------------- main
def main():
    access_gate()
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
