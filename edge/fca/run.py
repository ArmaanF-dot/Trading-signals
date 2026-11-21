"""FCA pipeline (aggregate net shorts): download -> snapshot -> diff against previous snapshot -> alerts."""
from datetime import date

import pandas as pd

import config
from edge import notify, prices, store
from edge.fca import shorts


def load_isin_tickers() -> dict[str, str]:
    df = store.read_csv(config.ISIN_TICKER_CSV)
    return dict(zip(df["isin"], df["ticker"])) if not df.empty else {}


def process(cur: pd.DataFrame, today: str) -> pd.DataFrame:
    prev = shorts.latest_snapshot(config.FCA_SNAPSHOT_DIR, before=today)
    config.FCA_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    cur.to_csv(config.FCA_SNAPSHOT_DIR / f"{today}.csv", index=False)
    if prev.empty:
        print("fca: first snapshot saved, no diff yet")
        return pd.DataFrame(columns=shorts.EVENT_COLUMNS)
    events = shorts.diff(prev, cur, today)
    tick = load_isin_tickers()
    events["ticker"] = events["isin"].map(tick).fillna("")
    new = store.append_dedupe(config.FCA_EVENTS_CSV, events.astype(str), ["date", "event", "isin"])
    for r in new.itertuples():
        if r.event in config.FCA_ALERT_EVENTS:
            notify.send(f"FCA short {r.event}: {r.issuer}",
                        f"{float(r.prev_pct):.2f}% -> {float(r.new_pct):.2f}% ({r.isin})",
                        tags=["chart_with_downwards_trend"])
    return new


def update_returns() -> None:
    df = store.read_csv(config.FCA_EVENTS_CSV)
    if df.empty:
        return
    prices.fill_returns(df, "ticker", "date", "uk").to_csv(config.FCA_EVENTS_CSV, index=False)


def run() -> None:
    cur = shorts.parse_csv(shorts.download())
    process(cur, date.today().isoformat())
    update_returns()
