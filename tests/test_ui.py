"""The visual layer: palette contrast (WCAG), escaping, and the geometry of the price meter."""
import re

from dawa_buddy import ui


def lum(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_every_text_and_background_pair_in_the_palette_meets_wcag_aa():
    pairs = []
    for k, c in ui.S.items():
        pairs += [(f"{k} text on its tint", c["fg"], c["bg"]), (f"{k} deep text on its tint", c["deep"], c["bg"]), (f"{k} text on white", c["fg"], "#FFFFFF")]
    pairs += [("ink on page", ui.T["ink"], ui.T["page"]), ("muted on page", ui.T["muted"], ui.T["page"]), ("muted on white", ui.T["muted"], ui.T["card"]),
              ("white on brand button", "#FFFFFF", ui.T["brand"]), ("brand on page", ui.T["brand"], ui.T["page"]), ("brand on white", ui.T["brand"], "#FFFFFF"),
              ("brand dark on brand tint", ui.T["brand_dark"], ui.T["brand_tint"]), ("brand on brand tint", ui.T["brand"], ui.T["brand_tint"]),
              ("white on ink badge", "#FFFFFF", ui.T["ink"]), ("white on status icon (red)", "#FFFFFF", ui.S["red"]["fg"])]
    failed = [(n, round(ratio(a, b), 2)) for n, a, b in pairs if ratio(a, b) < 4.5]
    assert not failed, failed


def test_user_text_is_escaped_in_every_builder():
    bad = '<img src=x onerror=alert(1)>'
    out = ui.card("red", bad, bad, total=bad, why=bad) + ui.verdict("red", bad, bad, [(bad, bad, "red")]) + ui.diff(bad, bad) + ui.section_label(bad, 1) + ui.found_badge(bad)
    assert "<img" not in out and out.count("&lt;img") >= 10


def pct(html_, style_fragment):
    return [float(x) for x in re.findall(style_fragment + r":([\d.]+)%", html_)]


def test_meter_puts_the_tick_at_the_limit_and_the_dot_at_the_price_on_a_shared_scale():
    m = ui.meter(12.40, 6.92, "red", "You paid ₹12.40", "Legal limit ₹6.92")
    lefts = pct(m, "left")
    assert abs(lefts[-2] - 6.92 / (12.40 * 1.15) * 100) < 0.1 and abs(lefts[-1] - 12.40 / (12.40 * 1.15) * 100) < 0.1   # tick, dot
    assert ui.S["red"]["bar"] in m and "You paid ₹12.40" in m and "Legal limit ₹6.92" in m


def test_meter_for_a_price_within_the_limit_has_no_overshoot_segment():
    m = ui.meter(5.0, 8.0, "green", "You paid ₹5", "Limit ₹8")
    assert ui.S["green"]["bar"] in m and ui.S["red"]["bar"] not in m and 'width:' in m
    assert pct(m, "left")[-1] < pct(m, "left")[-2]                                                          # dot before the tick


def test_header_marks_the_current_step_and_the_finished_ones():
    h = ui.header(2)
    assert h.count("db-dot on") == 1 and h.count("db-pill") == 1 and "Step 2 of 3" in h and ui.header().count("db-dot") == 0


def test_stylesheet_loads_the_fonts_and_hides_streamlit_chrome_but_keeps_icon_fonts_alone():
    c = ui.css()
    assert "DM+Serif+Display" in c and "Noto+Sans+Kannada" in c and "Noto+Sans+Devanagari" in c
    assert 'header[data-testid="stHeader"]' in c and 'stIconMaterial' in c            # icon glyphs are excluded from the font override
