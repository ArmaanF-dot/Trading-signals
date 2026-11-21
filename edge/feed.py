"""One daily feed of current signals (JSON plus a readable summary) for the agent council.

Stances: "avoid" (do not buy), "watch" (inspect), "info". Nothing here is a buy instruction:
the backtests (see reports/) found no standalone edge, and every record carries that evidence.
"""
import json
from datetime import date

import pandas as pd

import config
from edge import store
from edge.fca import shorts


def _recent(df: pd.DataFrame, col: str, today: str, days: int) -> pd.DataFrame:
    if df.empty or col not in df:
        return df.iloc[0:0]
    d = pd.to_datetime(df[col], errors="coerce")
    return df[(d >= pd.Timestamp(today) - pd.Timedelta(days=days)) & (d <= pd.Timestamp(today))]


def form4_records(clusters: pd.DataFrame, today: str, days: int) -> list[dict]:
    col = "public_date" if "public_date" in clusters.columns else "signal_date"
    out = []
    for r in _recent(clusters, col, today, days).itertuples():
        cap = getattr(r, "market_cap", "")
        out.append({
            "id": f"form4:{r.issuer_cik}:{r.window_start}", "symbol": r.ticker, "market": "US", "signal": "form4_cluster",
            "stance": "watch", "date": r.signal_date,
            "summary": f"{r.n_insiders} insiders bought ${float(r.total_value):,.0f} (window from {r.window_start}): {r.insiders}",
            "metrics": {"n_insiders": int(r.n_insiders), "total_value": float(r.total_value),
                        "market_cap": float(cap) if str(cap) not in ("", "nan") else None},
            "evidence": config.FEED_EVIDENCE["form4_cluster"],
        })
    return out


def fca_records(events: pd.DataFrame, snapshot: pd.DataFrame, today: str, days: int) -> list[dict]:
    """Net change in aggregate short per ISIN over the lookback; a rise of FCA_RISE_PP or more is an avoid flag."""
    ev = _recent(events, "date", today, days)
    if ev.empty:
        return []
    ev = ev.assign(delta=pd.to_numeric(ev["delta_pp"], errors="coerce").fillna(0.0))
    level = dict(zip(snapshot["isin"], snapshot["net_short_pct"])) if not snapshot.empty else {}
    out = []
    for isin, g in ev.groupby("isin"):
        net = float(g["delta"].sum())
        if abs(net) < config.FCA_RISE_PP - 1e-9:
            continue
        rise = net > 0
        out.append({
            "id": f"fca:{isin}:{g['date'].max()}", "symbol": (g["ticker"].iloc[-1] or ""), "isin": isin, "market": "UK",
            "signal": "fca_short_rise" if rise else "fca_short_fall", "stance": "avoid" if rise else "info",
            "date": g["date"].max(), "summary": f"{g['issuer'].iloc[-1]}: aggregate net short {'up' if rise else 'down'} {abs(net):.2f}pp "
                                               f"over {days} days, now {level.get(isin, float('nan')):.2f}%",
            "metrics": {"net_change_pp": round(net, 3), "aggregate_net_short_pct": float(level[isin]) if isin in level else None},
            "evidence": config.FEED_EVIDENCE["fca_short_rise"] if rise else "Short covering: no measurable edge in backtests.",
        })
    return out


def combo_records(combos: pd.DataFrame, today: str, days: int) -> list[dict]:
    return [{
        "id": f"combo:{r.isin}:{r.signal_date}", "symbol": r.ticker, "isin": r.isin, "market": "UK", "signal": "uk_combo",
        "stance": "watch", "date": r.signal_date,
        "summary": f"{r.company}: {r.n_directors} director(s) bought GBP {float(r.director_value_gbp):,.0f} while aggregate net short is {float(r.total_net_short_pct):.2f}%",
        "metrics": {"n_directors": int(r.n_directors), "director_value_gbp": float(r.director_value_gbp),
                    "aggregate_net_short_pct": float(r.total_net_short_pct)},
        "evidence": config.FEED_EVIDENCE["uk_combo"],
    } for r in _recent(combos, "signal_date", today, days).itertuples()]


ORDER = {"avoid": 0, "watch": 1, "info": 2}


def build_feed(today: str, clusters, events, snapshot, combos, days: int = config.FEED_LOOKBACK_DAYS) -> dict:
    recs = form4_records(clusters, today, days) + fca_records(events, snapshot, today, days) + combo_records(combos, today, days)
    recs.sort(key=lambda r: (ORDER[r["stance"]], r["date"]), reverse=False)
    return {"as_of": today, "lookback_days": days, "disclaimer": config.FEED_DISCLAIMER, "signals": recs}


def to_markdown(feed: dict) -> str:
    L = [f"# Signal feed ({feed['as_of']})", "", f"_{feed['disclaimer']}_", ""]
    if not feed["signals"]:
        return "\n".join(L + ["No active signals."])
    for stance in ("avoid", "watch", "info"):
        group = [s for s in feed["signals"] if s["stance"] == stance]
        if group:
            L += [f"## {stance.capitalize()}", ""]
            L += [f"- **{s['symbol'] or s.get('isin', '?')}** ({s['market']}, {s['signal']}, {s['date']}): {s['summary']}" for s in group]
            L.append("")
    return "\n".join(L)


def run(today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    clusters = store.read_csv(config.FORM4_CLUSTERS_CSV)
    events = store.read_csv(config.FCA_EVENTS_CSV)
    combos = store.read_csv(config.COMBO_CSV)
    snapshot = shorts.latest_snapshot(config.FCA_SNAPSHOT_DIR)
    feed = build_feed(today, clusters, events, snapshot, combos)
    config.SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    config.FEED_JSON.write_text(json.dumps(feed, indent=2) + "\n")
    config.FEED_MD.write_text(to_markdown(feed) + "\n")
    return feed
