"""UFC model predictions for Baco's Fight night tab.

The model lives in ArmaanF-dot/MMA-betting. Its `scripts/signal_data.py` writes `ufc-ui/data.json`,
which that repo git-ignores because it holds scraped bookmaker prices. This module converts that file
into a small, stable interface (schema 1) that the dashboard reads:

    {"schema": 1, "generated_at": ..., "public": true,
     "events": [{"name", "dates", "days_to_go", "fights": [
         {"a", "b", "weight_class", "rounds", "p_a", "p_elo_a", "p_distance",
          "pick", "pick_side", "confidence", "tier", "drivers", "flags", "thin_data"}]}],
     "forward": {"logged", "graded", "needed"}, "evidence": [...], "gap": {...}}

Public mode (the default, used for anything committed to this public repo) keeps only the model's own
output: no bookmaker prices, books, market-implied probabilities or stakes. Private mode adds those and
is meant for the browser's local import, never for the repository.

    python run.py ufc ../MMA-betting/ufc-ui/data.json            # writes data/ufc_predictions.json (public)
    python run.py ufc ../MMA-betting/ufc-ui/data.json --private out.json
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import config

UFC_JSON = config.DATA_DIR / "ufc_predictions.json"
# The model repo's weekly `picks` workflow publishes the model's own picks (no prices) here.
REMOTE_URL = "https://raw.githubusercontent.com/ArmaanF-dot/MMA-betting/main/public/picks.json"
SCHEMA = 1


def tier_label(conf: float | None) -> str:
    """Plain-English confidence from the model's probability for its pick."""
    if conf is None:
        return "Unknown"
    return "High" if conf >= 0.80 else "Good" if conf >= 0.70 else "Moderate" if conf >= 0.60 else "Toss-up"


def _r(v, n=4):
    return None if v is None else round(float(v), n)


def fight(f: dict, public: bool = True) -> dict:
    pa = float(f["p_model"])
    pick_a = pa >= 0.5
    conf = max(pa, 1 - pa)
    out = {
        "a": f["a"], "b": f["b"], "weight_class": f.get("wc"), "rounds": f.get("rounds"),
        "p_a": _r(pa), "p_elo_a": _r(f.get("p_elo")), "p_distance": _r(f.get("dist")),
        "pick": f["a"] if pick_a else f["b"], "pick_side": "A" if pick_a else "B",
        "confidence": _r(conf), "confidence_label": tier_label(conf), "tier": (f.get("pick") or {}).get("tier"),
        "drivers": [[str(n), _r(v, 1)] for n, v in (f.get("drivers") or [])][:3],
        "flags": list(f.get("flags") or []),
        "thin_data": bool(f.get("coverage")) and min(f["coverage"]) < 3,
    }
    if not public:
        out.update({"price_a": f.get("best_a"), "price_b": f.get("best_b"), "book_a": f.get("best_a_book"),
                    "book_b": f.get("best_b_book"), "market_p_a": _r(f.get("p_mkt")), "blend_p_a": _r(f.get("p_blend"))})
        bet = f.get("bet")
        if bet:
            out["bet"] = {"fighter": bet["fighter"], "price": bet["price"], "book": bet["book"], "edge": _r(bet["edge"]),
                          "stake_per_50": bet["stake"]}
    return out


def normalise(raw: dict, public: bool = True, now: datetime | None = None) -> dict:
    """Convert the model's ufc-ui/data.json into the dashboard's interface."""
    now = now or datetime.now(timezone.utc)
    events = []
    for c in raw.get("cards", []):
        events.append({"name": c.get("name"), "dates": c.get("dates"), "days_to_go": c.get("days"),
                       "n_fights": len(c.get("fights", [])), "last_data": c.get("last_data"),
                       "fights": [fight(f, public) for f in c.get("fights", [])]})
    fwd = raw.get("forward") or {}
    out = {"schema": SCHEMA, "public": public, "source": "ufcmodel (ArmaanF-dot/MMA-betting)",
           "generated_at": now.isoformat(timespec="seconds"), "model_as_of": raw.get("asof"),
           "events": events,
           "forward": {"logged": fwd.get("logged", 0), "graded": fwd.get("graded", 0), "needed": fwd.get("needed", 150)},
           "evidence": raw.get("evidence") or [], "gap": raw.get("gap")}
    return out


def load(path: Path | None = None) -> dict | None:
    """The committed public predictions, or None if there are none yet."""
    try:
        d = json.loads((path or UFC_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if d.get("schema") == SCHEMA and d.get("events") is not None else None


def fetch_remote(get=None, url: str = REMOTE_URL) -> dict | None:
    """The picks published by the model repo's weekly workflow, or None if unavailable or not in schema 1."""
    import requests
    get = get or requests.get
    try:
        r = get(url, timeout=20)
        d = r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("schema") == SCHEMA and isinstance(d.get("events"), list) else None


def current(get=None) -> dict | None:
    """Newest of the remote and committed picks (by generated_at), so the page never shows an older card than exists."""
    cands = [c for c in (fetch_remote(get), load()) if c]
    return max(cands, key=lambda c: c.get("generated_at") or "") if cands else None


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: python run.py ufc PATH_TO_ufc-ui/data.json [--private OUT.json]")
        return 2
    raw = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    if "--private" in argv:
        out = Path(argv[argv.index("--private") + 1])
        data = normalise(raw, public=False)
    else:
        out, data = UFC_JSON, normalise(raw, public=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    n = sum(len(e["fights"]) for e in data["events"])
    print(f"ufc: wrote {out} ({len(data['events'])} events, {n} fights, {'public' if data['public'] else 'PRIVATE: do not commit'})")
    return 0
