import json, re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def _load(name):
    return json.loads((DATA / name).read_text())


BRANDS: dict = {k: v for k, v in _load("brands.json").items() if not k.startswith("_")}
INTERACTIONS: list = _load("interactions.json")["pairs"]


def resolve_generic(name: str) -> str | None:
    """Map a brand or generic name to its active ingredient(s), if known."""
    tokens = re.findall(r"[a-z]+", name.lower())
    for t in tokens:
        if t in BRANDS:
            return BRANDS[t]
    return None


def load_alerts(path: Path | None = None) -> list:
    return json.loads((path or DATA / "nsq_alerts.json").read_text())["alerts"]
