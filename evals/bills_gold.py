"""SYNTHETIC bills (fictional hospital, invented prices) with hand-labelled expected tiers.
Format per line: description | qty | rate | amount.  No real patient or hospital data."""
from dawa_buddy import bill as b

BILLS = [
 {"id": "synthetic_cardiac_ward", "text": """TELMA 40 TAB | 30 | 6.50 | 195.00 | tab
ATORVA 10 TAB | 30 | 4.90 | 147.00 | tab
ECOSPRIN 75 TAB | 30 | 0.40 | 12.00 | tab
CLOPITAB 75 TAB | 30 | 6.50 | 195.00 | tab
DOLO 650 TAB | 6 | 1.90 | 11.40 | tab
PHENYTOIN 100 TAB | 30 | 1.90 | 57.00 | tab
IV SET DISPOSABLE | 4 | 85.00 | 340.00
ROOM RENT GENERAL WARD | 3 | 1500.00 | 4500.00""",
  "expected": {"TELMA 40 TAB": b.TIER_GENERIC_GAP, "ATORVA 10 TAB": b.TIER_GENERIC_GAP,
               "ECOSPRIN 75 TAB": b.TIER_OK, "CLOPITAB 75 TAB": b.TIER_GENERIC_GAP,
               "DOLO 650 TAB": b.TIER_OK, "PHENYTOIN 100 TAB": b.TIER_DOCTOR_ONLY,
               "IV SET DISPOSABLE": b.TIER_NOT_MEDICINE, "ROOM RENT GENERAL WARD": b.TIER_NOT_MEDICINE}},
 {"id": "synthetic_above_ceiling", "text": """AMLONG 5 TAB | 10 | 9.00 | 90.00 | tab
GLYCOMET 500 TAB | 20 | 2.00 | 40.00 | tab
GLIMEPIRIDE 1 TAB | 20 | 6.50 | 130.00 | tab""",
  "expected": {"AMLONG 5 TAB": b.TIER_ABOVE_CEILING, "GLYCOMET 500 TAB": b.TIER_NEEDS_CONFIRM,
               "GLIMEPIRIDE 1 TAB": b.TIER_ABOVE_CEILING}},
 {"id": "synthetic_ambiguous", "text": """PANTOP 40 | 10 | 120.00 | 1200.00
TELMA 40 TAB | 10 | 8.00 | 90.00""",
  "expected": {"PANTOP 40": b.TIER_UNIT_UNCLEAR, "TELMA 40 TAB": b.TIER_UNIT_UNCLEAR}},
 {"id": "synthetic_injections", "text": """AACEF 250 INJ | 1 | 26.00 | 26.00 | vial
LASIX INJ | 5 | 25.00 | 125.00 | vial | 2
AMICAP 500 INJ | 1 | 150.00 | 150.00 | vial
LASIX 20 INJ | 1 | 30.00 | 30.00 | vial""",
  "expected": {"AACEF 250 INJ": b.TIER_OK, "LASIX INJ": b.TIER_ABOVE_CEILING,
               "AMICAP 500 INJ": b.TIER_GENERIC_GAP, "LASIX 20 INJ": b.TIER_UNIT_UNCLEAR}},
 {"id": "synthetic_injection_high", "text": "AACEF 250 INJ | 1 | 90.00 | 90.00 | vial",
  "expected": {"AACEF 250 INJ": b.TIER_ABOVE_CEILING}},
]
