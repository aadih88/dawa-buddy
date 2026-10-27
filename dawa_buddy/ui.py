"""The visual layer: design tokens, fonts, widget restyling, and HTML builders for every component of the design.

Streamlit draws the widgets (uploader, toggles, steppers, expanders); this module restyles them with CSS and supplies plain-HTML builders
for everything it does not provide (header, verdict, cards, price meter, chips). Keep visual decisions here so the screens stay about content.
Colour pairs are checked for WCAG contrast in tests/test_ui.py.
"""
from __future__ import annotations
import html
import urllib.parse

FONTS = ("https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Serif+Display&"
         "family=Noto+Sans+Devanagari:wght@400;500;600&family=Noto+Sans+Kannada:wght@400;500;600&display=swap")

T = dict(page="#F7F5F0", card="#FFFFFF", line="#E4DFD3", hair="#EEEAE0", ink="#1C2326", muted="#4C575E", faint="#8A949B",
         brand="#0F6B5C", brand_dark="#0B4F44", brand_tint="#EAF4F0", control="#CFC9BA", well="#F1EEE6")
# status -> text colour, tint background, "over the limit" bar colour, darker text for use on the tint
S = {
    "red":   dict(fg="#A8201A", bg="#FCEBE8", bar="#F2B8B2", deep="#5B100C"),
    "amber": dict(fg="#8A5200", bg="#FFF3D6", bar="#F6DFA4", deep="#4A3000"),
    "green": dict(fg="#17663F", bg="#E4F3EA", bar="#BFE3CF", deep="#0F3F26"),
    "grey":  dict(fg="#4A5760", bg="#EDF0F2", bar="#D5DBDF", deep="#2C353B"),
}

_CAMERA_SVG = ("<svg xmlns='http://www.w3.org/2000/svg' width='56' height='56' viewBox='0 0 56 56'><circle cx='28' cy='28' r='28' fill='white'/>"
               "<g transform='translate(16 16)' fill='none' stroke='#0F6B5C' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
               "<path d='M14.5 4h-5L8 6H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-3Z'/><circle cx='12' cy='12.5' r='3.5'/></g></svg>")
CAMERA_URI = "data:image/svg+xml," + urllib.parse.quote(_CAMERA_SVG, safe="/:=,'")
_SVG = ('<svg width="{s}" height="{s}" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">{p}</svg>')
_PATHS = {
    "logo": '<path d="M10.5 20.5 3.5 13.5a4.95 4.95 0 0 1 7-7l7 7a4.95 4.95 0 0 1-7 7Z"/><path d="m8.5 8.5 7 7"/>',
    "alert": '<path d="m10.3 3.9-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3.1l-8-14a2 2 0 0 0-3.4 0Z"/><path d="M12 9.5v4M12 17v.01"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.2a2.6 2.6 0 0 1 5 .8c0 1.7-2.5 2.2-2.5 3.7M12 17v.01"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "minus": '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.01"/>',
    "camera": '<path d="M14.5 4h-5L8 6H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-3Z"/><circle cx="12" cy="12.5" r="3.5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "lock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "arrow": '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "download": '<path d="M12 4v11m0 0-4-4m4 4 4-4M5 20h14"/>',
}
_KIND_ICON = {"red": "alert", "amber": "help", "green": "check", "grey": "minus"}


def icon(name: str, size: int = 16, color: str = "currentColor", weight: float = 2.2) -> str:
    return _SVG.format(s=size, c=color, w=weight, p=_PATHS[name])


def esc(x) -> str:
    return html.escape(str(x), quote=True)


# ---------------------------------------------------------------- the stylesheet
def css() -> str:
    """One <style> block: tokens, fonts, page chrome, widget restyling, and the classes the builders below use."""
    return f"""
<style>
@import url('{FONTS}');
:root {{
  --page:{T['page']}; --card:{T['card']}; --line:{T['line']}; --hair:{T['hair']}; --ink:{T['ink']}; --muted:{T['muted']};
  --brand:{T['brand']}; --brand-dark:{T['brand_dark']}; --brand-tint:{T['brand_tint']}; --control:{T['control']}; --well:{T['well']};
  --sans:'DM Sans','Noto Sans Devanagari','Noto Sans Kannada',system-ui,sans-serif; --serif:'DM Serif Display',Georgia,serif;
}}
/* page chrome */
#MainMenu, footer, header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{display:none !important;}}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{background:var(--page) !important;}}
.stApp, .stApp p, .stApp label, .stApp li, .stApp input, .stApp textarea, .stApp button, .stApp summary, .stApp span:not([data-testid="stIconMaterial"]) {{font-family:var(--sans);}}
.stApp {{color:var(--ink);}}
.block-container {{max-width:720px; padding-top:1.4rem; padding-bottom:3rem;}}
h1, h2, h3, h1 *, h2 *, h3 * {{font-family:var(--serif) !important; font-weight:400 !important; letter-spacing:-0.01em; color:var(--ink);}}
h1 {{font-size:2.5rem !important; line-height:1.08 !important; margin-bottom:.2rem !important;}}
h2 {{font-size:2rem !important; line-height:1.1 !important;}}
h3 {{font-size:1.5rem !important;}}
a {{color:var(--brand);}}

/* buttons: one teal for every action */
div.stButton > button, div.stDownloadButton > button, [data-testid="stPopover"] > div > button {{
  border-radius:14px; font-weight:600; min-height:48px; border:1.5px solid var(--control); background:var(--card); color:var(--ink); box-shadow:none;}}
div.stButton > button:hover, div.stDownloadButton > button:hover {{border-color:var(--brand); color:var(--brand-dark);}}
div.stButton > button[kind="primary"], div.stDownloadButton > button[kind="primary"], button[data-testid="stBaseButton-primary"] {{
  background:var(--brand); border:0; color:#fff; font-weight:650; min-height:54px; font-size:1.05rem;}}
div.stButton > button[kind="primary"]:hover, div.stDownloadButton > button[kind="primary"]:hover {{background:var(--brand-dark); color:#fff;}}
div.stButton > button:disabled {{opacity:.55;}}
div.stButton > button p, div.stDownloadButton > button p {{font-weight:inherit;}}

/* photo drop zone: camera and wording drawn by CSS around Streamlit's own button */
[data-testid="stFileUploaderDropzone"] {{border:1.5px dashed var(--brand); background:var(--brand-tint); border-radius:22px; padding:22px 18px 22px; min-height:190px;
  display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; gap:12px;}}
[data-testid="stFileUploaderDropzone"]::before {{content:"Take or upload a photo of your bill"; display:block; padding-top:68px; font-weight:650; font-size:1.05rem; color:var(--brand-dark);
  background:url("{CAMERA_URI}") no-repeat top center / 56px 56px;}}
[data-testid="stFileUploaderDropzone"] small {{color:var(--muted);}}
[data-testid="stFileUploaderDropzone"] button {{background:var(--brand); color:#fff; border:0; border-radius:12px; min-height:44px; font-weight:650;}}
[data-testid="stFileUploader"] label p {{font-weight:600;}}

/* segmented control (how it was sold, language) */
[data-testid="stButtonGroup"] [role="radiogroup"] {{display:flex; background:var(--well); border-radius:12px; padding:3px; gap:3px; width:fit-content; max-width:100%;}}
[data-testid="stButtonGroup"] button {{flex:1 0 auto; min-width:0; padding:0 16px; border:0 !important; border-radius:10px !important; background:transparent !important; color:var(--muted);
  font-weight:550; min-height:40px; box-shadow:none; white-space:nowrap;}}
[data-testid="stButtonGroup"] button * {{overflow:visible !important; text-overflow:clip !important; white-space:nowrap !important;}}
[data-testid="stButtonGroup"] button[aria-checked="true"] {{background:var(--card) !important; color:var(--brand-dark) !important; font-weight:650; box-shadow:0 1px 2px rgba(0,0,0,.12) !important;}}

/* inputs */
[data-testid="stNumberInput"] > div, [data-testid="stTextInput"] > div > div, [data-testid="stTextArea"] > div > div {{
  border-radius:12px; border:1.5px solid var(--control); background:var(--card);}}
[data-testid="stNumberInput"] input, [data-testid="stTextInput"] input {{font-variant-numeric:tabular-nums; font-weight:600;}}
label[data-testid="stWidgetLabel"] p {{color:var(--muted); font-size:.9rem;}}

/* expanders: a quiet grouped list, not a stack of boxes */
[data-testid="stExpander"] details {{border:1px solid var(--line); border-radius:16px; background:var(--card);}}
[data-testid="stExpander"] summary {{font-weight:550; padding:.8rem 1rem;}}
[data-testid="stExpander"] summary:hover {{color:var(--brand-dark);}}
/* consecutive expanders read as ONE list: no gap, shared hairline, only the outer corners rounded */
[data-testid="stLayoutWrapper"]:has(> [data-testid="stExpander"]) + [data-testid="stLayoutWrapper"]:has(> [data-testid="stExpander"]) {{margin-top:-17px;}}
[data-testid="stLayoutWrapper"]:has(> [data-testid="stExpander"]) + [data-testid="stLayoutWrapper"]:has(> [data-testid="stExpander"]) details {{border-top-left-radius:0; border-top-right-radius:0;}}
[data-testid="stLayoutWrapper"]:has(> [data-testid="stExpander"]):has(+ [data-testid="stLayoutWrapper"] > [data-testid="stExpander"]) details {{border-bottom-left-radius:0; border-bottom-right-radius:0;}}

/* alerts and metrics keep Streamlit's behaviour, in the palette */
[data-testid="stAlert"] {{border-radius:14px;}}
[data-testid="stMetricValue"] {{font-variant-numeric:tabular-nums;}}
[data-testid="stCaptionContainer"] {{color:#5A646B;}}

/* ---- builders ---- */
.db-top {{display:flex; align-items:center; justify-content:space-between; height:40px; margin-bottom:6px;}}
.db-brand {{display:flex; align-items:center; gap:10px; font-weight:700; font-size:1.18rem; letter-spacing:-0.01em;}}
.db-mark {{width:34px; height:34px; border-radius:11px; background:var(--brand); display:flex; align-items:center; justify-content:center;}}
.db-steps {{display:flex; align-items:center; gap:6px; font-size:.8rem; color:var(--muted); font-weight:500;}}
.db-dot {{width:8px; height:8px; border-radius:50%; background:var(--control);}} .db-dot.on {{background:var(--brand);}}
.db-pill {{width:22px; height:8px; border-radius:4px; background:var(--brand);}}
.db-or {{display:flex; align-items:center; gap:12px; margin:1.1rem 0 .4rem; color:#5A646B; font-size:.85rem;}}
.db-or::before, .db-or::after {{content:""; flex:1; height:1px; background:#DDD8CB;}}
.db-sub {{color:var(--muted); font-size:1.05rem; line-height:1.5; margin:.2rem 0 1.1rem;}}
.db-verdict {{border-radius:24px; padding:22px 20px 18px; margin:.6rem 0 1rem;}}
.db-vhead {{display:flex; align-items:center; gap:12px;}}
.db-vicon {{width:44px; height:44px; flex:none; border-radius:50%; display:flex; align-items:center; justify-content:center;}}
.db-vtitle {{font-family:var(--serif); font-size:2.05rem !important; line-height:1.05 !important; margin:0 !important; padding:0 !important;}}
.db-vbody {{margin:12px 0 0; font-size:1rem; line-height:1.45;}}
.db-stats {{margin-top:16px; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px;}}
.db-stat {{background:rgba(255,255,255,.72); border-radius:14px; padding:11px 10px;}}
.db-stat b {{display:block; font-size:1.45rem; font-weight:700; font-variant-numeric:tabular-nums;}}
.db-stat span {{display:block; margin-top:2px; font-size:.75rem; line-height:1.3;}}
.db-label {{margin:26px 2px 10px; display:flex; align-items:center; gap:8px; font-size:.78rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--muted);}}
.db-count {{min-width:22px; height:22px; border-radius:11px; background:var(--ink); color:#fff; font-size:.75rem; font-weight:700; display:inline-flex; align-items:center; justify-content:center; padding:0 6px; letter-spacing:0;}}
.db-card {{background:var(--card); border:1px solid var(--line); border-radius:18px; padding:15px 16px; margin:0 0 12px;}}
.db-chip {{display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:4px 11px 4px 8px; font-size:.78rem; font-weight:700;}}
.db-row {{margin-top:10px; display:flex; justify-content:space-between; align-items:baseline; gap:10px;}}
.db-name {{font-size:1.06rem; font-weight:650; overflow-wrap:anywhere;}}
.db-amt {{font-size:.88rem; color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap;}}
.db-meter {{position:relative; height:20px; margin-top:14px;}}
.db-meter > div {{position:absolute;}}
.db-legend {{margin-top:8px; display:flex; justify-content:space-between; gap:10px; font-size:.85rem; font-variant-numeric:tabular-nums;}}
.db-diff {{margin-top:10px; display:grid; grid-template-columns:minmax(0,1fr) 22px minmax(0,1fr); align-items:center; gap:6px;}}
.db-diff > div {{border-radius:12px; padding:9px 11px;}}
.db-diff small {{display:block; font-size:.7rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase;}}
.db-diff b {{display:block; margin-top:2px; font-size:.94rem; font-weight:600; overflow-wrap:anywhere;}}
.db-card details {{margin-top:11px;}} .db-card summary {{cursor:pointer; color:var(--brand); font-size:.85rem; font-weight:600;}}
.db-body {{margin-top:8px; font-size:.95rem; line-height:1.45; overflow-wrap:anywhere;}}
.db-why {{margin-top:6px; font-size:.9rem; line-height:1.5; overflow-wrap:anywhere;}}
.db-found {{display:inline-flex; align-items:center; gap:6px; background:{S['green']['bg']}; color:{S['green']['fg']}; border-radius:999px; padding:4px 10px 4px 8px; font-size:.78rem; font-weight:600;}}
.db-callout {{margin:12px 0; border-radius:18px; padding:14px 16px; display:flex; align-items:center; gap:12px; font-size:.88rem; line-height:1.55;}}
.db-dose {{border-radius:14px; padding:12px 13px; background:var(--brand-tint);}}
.db-dose small {{display:block; font-size:.7rem; font-weight:700; letter-spacing:.07em; text-transform:uppercase; color:var(--brand-dark);}}
.db-dose div {{margin-top:5px; font-size:1.05rem; line-height:1.55; font-weight:500; color:#12302A;}}
/* messages, spinner and the review-screen line cards */
[class^="db-"], [class*=" db-"], [class^="db-"] *, [class*=" db-"] * {{font-family:var(--sans) !important;}}
.db-msg {{display:flex; align-items:flex-start; gap:10px; border-radius:14px; padding:12px 14px; margin:.4rem 0 .8rem; font-size:.93rem; line-height:1.5;}}
.db-msg svg {{flex:none; margin-top:2px;}}
div[class*="st-key-card_"] {{background:var(--card); border:1px solid var(--line) !important; border-radius:18px !important; padding:15px 16px 14px !important; margin-bottom:2px;}}
.db-calc {{margin-top:3px; font-size:.95rem; color:var(--muted); font-variant-numeric:tabular-nums; overflow-wrap:anywhere;}}
.db-chips {{margin-top:8px; display:flex; flex-wrap:wrap; gap:6px; align-items:center;}}
.db-mrp {{font-size:.78rem; font-weight:650; color:var(--brand-dark); background:var(--brand-tint); border-radius:999px; padding:4px 10px;}}
[data-testid="stSpinner"] {{color:var(--brand-dark); background:var(--brand-tint); border-radius:14px; padding:10px 14px; font-weight:550;}}
[data-testid="stSpinner"] svg, [data-testid="stSpinner"] i {{color:var(--brand) !important; border-top-color:var(--brand) !important;}}
.db-watch {{margin-top:8px; font-size:.9rem; line-height:1.5; color:var(--muted); overflow-wrap:anywhere;}} .db-watch b {{color:var(--ink);}}
.db-note {{border-radius:16px; padding:13px 15px; margin:0 0 10px;}}
.db-notehead {{display:flex; align-items:center; gap:7px; font-size:.82rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase;}}
.db-noteitem {{margin-top:8px; font-size:.93rem; line-height:1.5; overflow-wrap:anywhere;}} .db-noteitem b {{display:block;}}
.db-foot {{text-align:center; font-size:.75rem; color:#5A646B; line-height:1.45; margin-top:1rem;}}

/* ---- legacy classes still used by the screens until they move to the builders ---- */
.sub {{color:var(--muted); font-size:1.05rem; margin:.1rem 0 1.2rem 0;}}
.verdict {{border-radius:24px; padding:20px 22px; margin:.4rem 0 1rem 0; color:#14181d;}}
.verdict .head {{font-family:var(--serif); font-size:1.9rem; line-height:1.15;}}
.verdict .line {{margin-top:.35rem; font-size:1rem; opacity:.9;}}
.chips {{margin-top:.8rem; display:flex; flex-wrap:wrap; gap:8px;}}
.chip {{background:rgba(255,255,255,.75); border-radius:999px; padding:4px 12px; font-size:.88rem; font-weight:600;}}
.card {{border:1px solid var(--line); border-left:6px solid var(--c); border-radius:16px; padding:14px 16px; margin:10px 0; background:var(--card);}}
.card .top {{display:flex; justify-content:space-between; gap:14px; align-items:baseline;}}
.card .name {{font-weight:650; font-size:1.02rem; overflow-wrap:anywhere;}}
.card .amt {{color:var(--muted); font-size:.9rem; white-space:nowrap;}}
.card .tag {{margin-top:2px; font-size:.8rem; font-weight:700; color:var(--c); text-transform:uppercase; letter-spacing:.02em;}}
.card .meta {{margin-top:4px; font-size:.95rem; overflow-wrap:anywhere;}}
.card details {{margin-top:8px;}} .card summary {{cursor:pointer; color:var(--muted); font-size:.88rem;}}
.card .why {{margin-top:6px; font-size:.92rem; line-height:1.5; overflow-wrap:anywhere;}}
.mini {{display:flex; justify-content:space-between; gap:12px; padding:7px 0; border-bottom:1px solid var(--hair); font-size:.95rem;}}
.mini .l {{overflow-wrap:anywhere;}} .mini .r {{color:var(--muted); white-space:nowrap;}}
.small {{color:#6b7480; font-size:.85rem;}}
</style>
"""


# ---------------------------------------------------------------- builders (all return HTML strings)
def header(step: int | None = None, label: str = "") -> str:
    """Brand mark and name; with `step` (1-3) the progress dots: the current step is the long pill."""
    dots = ""
    if step:
        parts = "".join('<span class="db-pill"></span>' if i == step else f'<span class="db-dot{" on" if i < step else ""}"></span>' for i in (1, 2, 3))
        dots = f'<div class="db-steps">{parts}<span style="margin-left:4px">{esc(label or f"Step {step} of 3")}</span></div>'
    return (f'<div class="db-top"><div class="db-brand"><div class="db-mark">{icon("logo", 20, "#fff", 2)}</div>Dawa Buddy</div>{dots}</div>')


def chip(kind: str, text: str, icon_name: str | None = None) -> str:
    c = S[kind]
    return (f'<span class="db-chip" style="background:{c["bg"]};color:{c["fg"]}">'
            f'{icon(icon_name or _KIND_ICON[kind], 14, c["fg"], 2.4)}{esc(text)}</span>')


def verdict(kind: str, title: str, body: str, stats: list[tuple[str, str, str]]) -> str:
    """The headline answer. stats: (value, caption, kind) triples shown as three tiles."""
    c = S[kind]
    tiles = "".join(f'<div class="db-stat"><b style="color:{S[k]["fg"]}">{esc(v)}</b><span style="color:{c["deep"]}">{esc(cap)}</span></div>' for v, cap, k in stats)
    return (f'<div class="db-verdict" style="background:{c["bg"]}"><div class="db-vhead">'
            f'<div class="db-vicon" style="background:{c["fg"]}">{icon(_KIND_ICON[kind], 24, "#fff", 2.2)}</div>'
            f'<h1 class="db-vtitle" style="color:{c["deep"]}">{esc(title)}</h1></div>'
            f'<p class="db-vbody" style="color:{c["deep"]}">{esc(body)}</p><div class="db-stats">{tiles}</div></div>')


def meter(paid: float, limit: float, kind: str, left: str, right: str) -> str:
    """Paid against the limit: green up to the limit, the overshoot in the status colour, a tick at the limit, a dot where the price is."""
    c = S[kind]
    scale = max(paid, limit) * 1.15 or 1
    p, l = paid / scale * 100, limit / scale * 100
    green_to = min(p, l)
    over = (f'<div style="left:{l:.1f}%;width:{p - l:.1f}%;top:6px;height:8px;background:{c["bar"]}"></div>' if p > l else "")
    return (f'<div class="db-meter" role="img" aria-label="{esc(left)}; {esc(right)}">'
            f'<div style="left:0;right:0;top:6px;height:8px;border-radius:4px;background:#ECE8DC"></div>'
            f'<div style="left:0;width:{green_to:.1f}%;top:6px;height:8px;border-radius:4px 0 0 4px;background:{S["green"]["bar"]}"></div>{over}'
            f'<div style="left:{l:.1f}%;top:1px;width:2px;height:18px;background:{T["ink"]}"></div>'
            f'<div style="left:{p:.1f}%;top:2px;width:16px;height:16px;margin-left:-8px;border-radius:50%;background:{c["fg"]};border:2.5px solid #fff;'
            f'box-shadow:0 1px 3px rgba(0,0,0,.3);box-sizing:border-box"></div></div>'
            f'<div class="db-legend"><span style="color:{c["fg"]};font-weight:650">{esc(left)}</span><span style="color:{T["muted"]}">{esc(right)}</span></div>')


def diff(prescribed: str, billed: str) -> str:
    return (f'<div class="db-diff"><div style="background:#F4F1E9"><small style="color:{T["muted"]}">Prescribed</small><b>{esc(prescribed)}</b></div>'
            f'{icon("arrow", 22, T["faint"], 2)}<div style="background:{S["red"]["bg"]}"><small style="color:{S["red"]["fg"]}">On the bill</small><b>{esc(billed)}</b></div></div>')


def card(kind: str, name: str, chip_text: str, *, total: str = "", body: str = "", visual: str = "", why: str = "", why_label: str = "Why this matters", icon_name: str | None = None) -> str:
    """A finding: status chip, item name (and its total), then a visual (meter or diff) and an optional folded explanation."""
    right = f'<span class="db-amt">{esc(total)}</span>' if total else ""
    why_html = f'<details><summary>{esc(why_label)}</summary><div class="db-why">{esc(why)}</div></details>' if why else ""
    body_html = f'<div class="db-body">{esc(body)}</div>' if body else ""
    return (f'<div class="db-card">{chip(kind, chip_text, icon_name)}<div class="db-row"><span class="db-name">{esc(name)}</span>{right}</div>'
            f'{body_html}{visual}{why_html}</div>')


def section_label(text: str, count: int | None = None) -> str:
    badge = f'<span class="db-count">{count}</span>' if count is not None else ""
    return f'<div class="db-label">{esc(text)}{badge}</div>'


def found_badge(text: str) -> str:
    return f'<span class="db-found">{icon("check", 14, S["green"]["fg"], 2.6)}{esc(text)}</span>'


def callout(body_html: str, icon_name: str = "search") -> str:
    return (f'<div class="db-callout" style="background:{T["brand_tint"]};color:{T["brand_dark"]}">'
            f'{icon(icon_name, 24, T["brand"], 2)}<div style="flex:1">{body_html}</div></div>')


def dose_box(sentence: str, label: str = "From your prescription") -> str:
    """The dose sentence, built from the prescription by fixed templates, set apart from the AI-written text."""
    return f'<div class="db-dose"><small>{esc(label)}</small><div>{esc(sentence)}</div></div>'


def med_card(name: str, dose: str, dose_label: str, purpose: str, watch_label: str, watch_for: str) -> str:
    """One medicine: name, the dose (fixed template, in a tinted box), then the AI-written purpose and side-effect line."""
    watch = f'<div class="db-watch"><b>{esc(watch_label)}</b> {esc(watch_for)}</div>' if watch_for else ""
    purpose_html = f'<div class="db-body">{esc(purpose)}</div>' if purpose else ""
    return (f'<div class="db-card"><div class="db-name">{esc(name)}</div><div style="margin-top:10px">{dose_box(dose, dose_label)}</div>'
            f'{purpose_html}{watch}</div>')


def message(kind: str, text: str) -> str:
    """A short status message in the app's own style (replaces Streamlit's default coloured boxes): icon, one or two sentences."""
    c = S[kind]
    return (f'<div class="db-msg" style="background:{c["bg"]};color:{c["deep"]}">{icon(_KIND_ICON[kind], 18, c["fg"], 2.4)}'
            f'<div>{esc(text)}</div></div>')


def line_head(name: str, calc: str, mrp: str = "", unsure: bool = False) -> str:
    """Top of a bill-line card on the review screen: the item as read, what we read for it (to compare with the paper), MRP and a re-check chip."""
    chips = (chip("amber", "Please re-check this line", "help") if unsure else "") + (f'<span class="db-mrp">{esc(mrp)}</span>' if mrp else "")
    return (f'<div class="db-name">{esc(name)}</div><div class="db-calc">{esc(calc)}</div>'
            f'{f"<div class=db-chips>{chips}</div>" if chips else ""}')


def note(kind: str, heading: str, items: list[tuple[str, str]], foot: str = "") -> str:
    """A tinted block of safety notes under one heading: a bold title and a sentence per issue."""
    c = S[kind]
    rows = "".join(f'<div class="db-noteitem"><b>{esc(t)}</b>{esc(d)}</div>' for t, d in items)
    rows += f'<div class="db-noteitem">{esc(foot)}</div>' if foot else ""
    return (f'<div class="db-note" style="background:{c["bg"]};color:{c["deep"]}"><div class="db-notehead" style="color:{c["fg"]}">'
            f'{icon(_KIND_ICON[kind], 16, c["fg"], 2.4)}{esc(heading)}</div>{rows}</div>')


def footer(text: str) -> str:
    return f'<div class="db-foot">{esc(text)}</div>'
