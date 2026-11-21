"""UK combo: a director buy on an ISIN that also has a named-fund net short (FCA)."""
import pandas as pd

import config
from edge import notify, prices, store
from edge.fca import shorts
from edge.rns import directors

COMBO_COLUMNS = ["signal_date", "company", "isin", "ticker", "n_directors", "director_value_gbp",
                 "total_net_short_pct", "n_short_holders", "price_at_signal", "ret_5d", "ret_20d"]


def find_combos(rns: pd.DataFrame, fca: pd.DataFrame, min_short: float = config.COMBO_MIN_NET_SHORT_PCT,
                lookback_days: int = config.COMBO_LOOKBACK_DAYS, today: str | None = None) -> pd.DataFrame:
    if rns.empty or fca.empty:
        return pd.DataFrame(columns=COMBO_COLUMNS)
    r = rns.copy()
    r["date"] = pd.to_datetime(r["date"])
    r["value_gbp"] = pd.to_numeric(r.get("value_gbp", 0), errors="coerce").fillna(0)
    if today:
        r = r[r["date"] >= pd.Timestamp(today) - pd.Timedelta(days=lookback_days)]
    s = fca.groupby("isin").agg(total=("net_short_pct", "sum"), holders=("holder", "nunique"))
    rows = []
    for isin, g in r.groupby("isin"):
        if isin not in s.index or s.loc[isin, "total"] < min_short:
            continue
        last = g.sort_values("date").iloc[-1]
        rows.append({
            "signal_date": g["date"].max().strftime("%Y-%m-%d"), "company": last.get("company", ""),
            "isin": isin, "ticker": last.get("ticker", ""), "n_directors": g["director"].nunique(),
            "director_value_gbp": round(g["value_gbp"].sum(), 2),
            "total_net_short_pct": round(float(s.loc[isin, "total"]), 3),
            "n_short_holders": int(s.loc[isin, "holders"]),
            "price_at_signal": "", "ret_5d": "", "ret_20d": "",
        })
    return pd.DataFrame(rows, columns=COMBO_COLUMNS)


def run(today: str | None = None) -> pd.DataFrame:
    from datetime import date
    today = today or date.today().isoformat()
    fca = shorts.latest_snapshot(config.FCA_SNAPSHOT_DIR)
    combos = find_combos(directors.load(), fca, today=today)
    new = store.append_dedupe(config.COMBO_CSV, combos.astype(str), ["isin", "signal_date"])
    for r in new.itertuples():
        notify.send(f"UK combo: {r.company}",
                    f"Director buy (GBP {float(r.director_value_gbp):,.0f}) while funds net short {float(r.total_net_short_pct):.2f}% ({r.n_short_holders} holders)",
                    priority="high", tags=["rotating_light"])
    df = store.read_csv(config.COMBO_CSV)
    if not df.empty:
        prices.fill_returns(df, "ticker", "signal_date", "uk").to_csv(config.COMBO_CSV, index=False)
    return new
