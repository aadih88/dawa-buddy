"""Built-in sample bills so anyone can try the audit in one click, without a photo or an API key.

SYNTHETIC: invented patients, invented prices (chosen to show each kind of result). Medicine names are real brands; the price
lists they are compared with are the real NPPA and Jan Aushadhi lists in data/. No real person's bill is in this repository.
Bill format: description | qty | rate | amount | unit | pack | mrp   (mrp is per pack as printed)
"""
from __future__ import annotations
import pandas as pd
from . import bill as b

SAMPLES = {
    "Outpatient pharmacy bill": {
        "about": "Six lines from a neighbourhood pharmacy. Shows an above-MRP line, an above-ceiling line, a generic-price question, "
                 "a supplement, and a wrong-variant warning (the prescription says Shelcal-XT, the bill has Shelcal 500).",
        "bill": """TELMA 40 TAB | 1 | 372.00 | 372.00 | strip | 30
AMLONG 5 TAB | 10 | 9.00 | 90.00 | tab | 10 | 80.00
ATORVA 10 TAB | 30 | 4.90 | 147.00 | tab
DOLO 650 TAB | 10 | 2.10 | 21.00 | tab
SHELCAL 500MG TAB | 30 | 9.81 | 294.21 | tab | 15 | 163.45
VELTAM 0.4MG TAB | 15 | 12.66 | 189.85 | tab | 15 | 210.94""",
        "rx": """Tab Telma 40 1-0-0 x 30 days
Tab Amlong 5 1-0-0 x 30 days
Tab Atorva 10 0-0-1 x 30 days
Tab Dolo 650 SOS
Tab Shelcal-XT 0-1-0 to continue""",
        "total": 1114.06,
    },
    "Hospital pharmacy bill": {
        "about": "Injections, IV fluids and consumables. Shows per-vial and per-ml injection ceilings, an IV saline bag priced against the "
                 "ordinary ceiling and the higher 'special features' ceiling, an IV set billed at 24 times its printed MRP (the kind of mark-up the Supreme Court has been "
                 "asking about), and items no price list covers.",
        "bill": """ACYCLOTAS 500MG INJ ACYCLOVIR | 13 | 568.14 | 7385.82 | vial | | 568.14
AACEF 250 INJ | 4 | 90.00 | 360.00 | vial
LASIX INJ | 5 | 25.00 | 125.00 | vial | 2
NS EUROHEAD IV FLUIDS 0.9% 100ML NON-GLASS DENIS HOUSE | 13 | 45.22 | 587.86
NS 0.9% 100ML | 2 | 45.22 | 90.44
SYRINGE 10ML WITH NEEDLE | 13 | 43.99 | 571.87
IV SET NOVOFUSION 30115 | 2 | 265.00 | 530.00 | each | | 11.00""",
        "rx": """INJ.ACYCLOVIR 500MG IV 1-1-1 AFTER FOOD X 7 DAYS
INJ.CEFTRIAXONE 250MG IV 1-0-1 X 2 DAYS
INJ NS 100ML IV with each dose x 7 days""",
        "total": 9650.99,
    },
}

COLS = ["description", "qty", "rate", "amount", "unit", "pack", "mrp", "unsure", "mrp_each"]


def frame(name: str) -> pd.DataFrame:
    """The sample's bill as the editable table the app shows."""
    lines, _ = b.parse_bill_ex(SAMPLES[name]["bill"])
    return pd.DataFrame([{"description": l.desc, "qty": l.qty, "rate": l.rate, "amount": l.amount, "unit": l.unit,
                          "pack": l.pack, "mrp": l.mrp, "unsure": False, "mrp_each": l.mrp_each} for l in lines], columns=COLS)
