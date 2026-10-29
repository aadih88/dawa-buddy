"""Turn findings into a plain list of questions to take to the pharmacy, hospital or doctor.

Deterministic on purpose: every number comes from the audit, nothing is generated, nothing is an accusation.
"""
from __future__ import annotations
from . import bill as b
from .reconcile import Flag


def questions(findings: list[b.Finding], flags: list[Flag] | None = None, peer_lines: list[str] | None = None, online_lines: list[str] | None = None) -> str:
    out = ["# Questions to ask about this bill", "",
           "These are prompts for a conversation, not findings of wrongdoing. Prices below come from public lists "
           f"(NPPA ceilings as on {b.nppa.AS_ON}; Jan Aushadhi list 21 Oct 2026).", ""]
    mrp = [f for f in findings if f.tier == b.TIER_ABOVE_MRP]
    supp = [f for f in findings if f.tier == b.TIER_SUPPLEMENT]
    ceil = [f for f in findings if f.tier == b.TIER_ABOVE_CEILING]
    gen = [f for f in findings if f.tier == b.TIER_GENERIC_GAP]
    doc = [f for f in findings if f.tier == b.TIER_DOCTOR_ONLY]
    unclear = [f for f in findings if f.tier in (b.TIER_UNIT_UNCLEAR, b.TIER_NEEDS_CONFIRM)]
    if mrp:
        out += ["## Charged above the printed MRP", ""]
        out += [f"- **{f.line.desc}**: charged {f.line.rate:.2f}, MRP on the bill {f.line.mrp:.2f}. Ask to see the pack and get a corrected bill."
                for f in mrp]
        out.append("")
    shown = [f for f in findings if f.line.mrp and f.tier != b.TIER_ABOVE_MRP]
    if shown:
        out += ["## Check the MRP on the strip", "",
                "The MRP on a bill is the seller's own figure, so a bill can agree with itself and still print the wrong MRP. The pack in your hand is the check.", ""]
        out += [f"- **{f.line.desc}**: the bill prints an MRP of {f.line.mrp:.2f}. Is it the same as the MRP printed on the strip or box?" for f in shown]
        out.append("")
    if ceil:
        out += ["## Ask the pharmacy or hospital billing desk", ""]
        for f in ceil:
            out.append(f"- **{f.line.desc}**: charged {f.unit_price:.2f} per unit; the government ceiling is {f.ceiling:.2f} "
                       f"(up to {f.ceiling*b.GST_ALLOWANCE:.2f} with GST). Ask them to show the batch MRP and explain the difference. "
                       "If it stays unexplained, you can raise it with NPPA's complaint channel.")
        out.append("")
    if gen:
        out += ["## Ask your doctor", ""]
        for f in gen:
            out.append(f"- **{f.line.desc}**: you paid {f.unit_price:.2f} per unit; a Jan Aushadhi generic of {f.generic_name} is listed at "
                       f"{f.generic_unit:.2f}. Ask: \"Is a generic of the same medicine suitable for me?\" Do not switch on your own.")
        out.append("")
    if doc:
        out += ["## Do not switch these without your doctor", ""]
        out += [f"- **{f.line.desc}**: dose-sensitive medicine. Ask your doctor before changing brand." for f in doc]
        out.append("")
    if supp:
        out += ["## Supplements: no price ceiling exists", "",
                "Supplements are not price-controlled, so we make no price judgement on these. Only the printed MRP limits them.", ""]
        out += [f"- {f.line.desc}: {f.line.amount:.2f}" for f in supp]
        out.append("")
    if unclear:
        out += ["## We could not check these", ""]
        out += [f"- **{f.line.desc}**: {f.note}" for f in unclear]
        out.append("")
    if online_lines:
        out += ["## Prices listed online", "", "Pharmacy websites list today's MRP; it can differ by batch, so these are questions, not findings.", ""]
        out += [f"- {x}" for x in online_lines]
        out.append("")
    if peer_lines:
        out += ["## Other brands of the same medicine", "",
                "NPPA has fixed prices for other companies' versions. These are not a legal limit on your brand: they show that an equivalent costs less.", ""]
        out += [f"- {x}" for x in peer_lines]
        out.append("")
    if flags:
        wrong = [x for x in flags if x.kind == "different_variant"]
        if wrong:
            out += ["## Check before taking: the bill may not match the prescription", ""]
            out += [f"- **{x.subject}**: {x.note}" for x in wrong]
            out.append("")
        rest = [x for x in flags if x.kind != "different_variant"]
        if rest:
            out += ["## Prescription vs bill", ""]
            out += [f"- **{x.subject}**: {x.note}" for x in rest]
            out.append("")
    if len(out) <= 4:
        out.append("Nothing to raise from the lists we hold. That is not a guarantee: many items have no public benchmark.")
    return "\n".join(out)
