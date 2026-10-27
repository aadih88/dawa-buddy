# Data sources
- `brand_index.json`: brand -> composition, derived by `scripts/build_brand_index.py` from
  github.com/junioralive/Indian-Medicine-Dataset (MIT licence, prices as of 2022; prices are discarded).
  Third-party compilation: spot-check against the strip before relying on it.
- `nppa_ceiling_2026-03.csv`: NPPA ceiling price posters (partial categories).
- `janaushadhi_2026-10-21.csv`: PMBJP product list.
- `brand_overrides.json`: hand-checked compositions that replace table rows (sources listed inside the file).
- `nppa_ceiling_2026-04.csv`: parsed from the three NPPA gazette notifications of 25.03.2026 (S.O. for 767 NLEM-2022, 1581(E) for 138 NLEM-2015, 1582(E) for 6 NLEM-2011 formulations), ceilings w.e.f. 1.4.2026 (WPI +0.64956%). Built by `scripts/parse_nppa_gazette.py`; source PDFs are kept out of git in `my_data/`.
- `nppa_ivfluids_special_2026-04.csv` / `nppa_special_makers_2026-04.csv`: ceilings for IV fluids in packs "with special features" and the manufacturers/brands NPPA lists as entitled to them (Table B), from three gazette notifications of 25.03.2026 (Ringer lactate, 6 other IV fluids, 8 IV fluids). Built by `scripts/parse_nppa_ivfluids.py`. Table B notes restricting some manufacturers to certain rows are not encoded: the tool treats naming a listed maker as a signal, not proof.
