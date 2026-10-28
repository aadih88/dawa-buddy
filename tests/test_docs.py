"""The README quotes numbers (tests, ingredients, price-list rows). They are checked against the code and data here, so they cannot drift silently."""
import csv
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()


def test_every_test_count_in_the_readme_is_the_real_count():
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"], cwd=ROOT, capture_output=True, text=True).stdout
    real = int(re.search(r"(\d+) tests? collected", out).group(1))
    quoted = {int(n) for n in re.findall(r"tests-(\d+)%20passing", README)} | {int(n) for n in re.findall(r"(\d+) tests\b", README)} | \
             {int(n) for n in re.findall(r"\*\*(\d+) pass\*\*", README)} | {int(n) for n in re.findall(r"tests: (\d+) passing", README)}
    assert quoted == {real}, f"README quotes {sorted(quoted)} but there are {real} tests"


def test_the_kannada_table_size_in_the_readme_is_the_real_size():
    from dawa_buddy import medinfo
    quoted = {int(n) for n in re.findall(r"\*\*(\d+) common ingredients\*\*", README)}
    assert quoted == {len(medinfo.MEDS)}, f"README says {sorted(quoted)}, the table has {len(medinfo.MEDS)}"


def test_the_formulation_counts_in_the_readme_match_the_price_list_files():
    gazette = list(csv.DictReader(open(ROOT / "data" / "nppa_ceiling_2026-04.csv", encoding="utf-8-sig")))
    assert len(gazette) == 911 and "911 formulations" in README
    assert sum(1 for r in gazette if r["category"] == "nlem2022") == 767 and sum(1 for r in gazette if r["category"] == "nlem2015") == 138 and sum(1 for r in gazette if r["category"] == "nlem2011") == 6
    assert len(list(csv.DictReader(open(ROOT / "data" / "nppa_ceiling_2026-03.csv", encoding="utf-8-sig")))) == 267 and "233 of 267" in README


def test_the_readme_does_not_publish_the_hosted_demo_link():
    assert "streamlit.app" not in README, "the demo URL belongs in the submission's testing instructions, not in the public repository"
