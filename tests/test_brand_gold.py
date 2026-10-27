from collections import Counter
from evals.run_brand_evals import run


def test_brand_table_never_pushes_a_wrong_salt_into_a_price_verdict():
    c = Counter(status for *_, status in run(use_table=True))
    assert c["WRONG+JUDGED"] == 0
    assert c["wrong"] == 0


def test_brand_table_resolves_most_common_brands_and_beats_the_curated_map():
    with_t = Counter(status for *_, status in run(use_table=True))
    without = Counter(status for *_, status in run(use_table=False))
    assert with_t["correct"] >= 95 and with_t["correct"] > 3 * without["correct"]
