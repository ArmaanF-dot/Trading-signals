"""Cluster-buy detection over the stored purchase rows."""
import pandas as pd

import config

CLUSTER_COLUMNS = [
    "issuer_cik", "window_start", "signal_date", "ticker", "issuer", "n_insiders",
    "total_value", "insiders", "price_at_signal", "ret_5d", "ret_20d",
]


def load_buys(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a str-typed CSV frame to proper dtypes."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    for c in ("shares", "price", "value"):
        df[c] = pd.to_numeric(df[c])
    return df


def find_clusters(
    buys: pd.DataFrame,
    min_insiders: int = config.CLUSTER_MIN_INSIDERS,
    window_days: int = config.CLUSTER_WINDOW_DAYS,
    min_value: float = config.CLUSTER_MIN_VALUE,
) -> pd.DataFrame:
    """Return one row per cluster. Windows run [start, start + window_days] where
    start is a buy date; once a window qualifies, later starts inside it are skipped
    so each cluster is emitted once."""
    rows = []
    if buys.empty:
        return pd.DataFrame(columns=CLUSTER_COLUMNS)
    for cik, g in buys.groupby("issuer_cik"):
        g = g.sort_values("date")
        covered_until = pd.Timestamp.min
        for start in sorted(g["date"].unique()):
            start = pd.Timestamp(start)
            if start <= covered_until:
                continue
            end = start + pd.Timedelta(days=window_days)
            w = g[(g["date"] >= start) & (g["date"] <= end)]
            # joint filings repeat the same trade per owner: count value once
            total = w.drop_duplicates(["accession", "date", "shares", "price"])["value"].sum()
            owners = w.drop_duplicates("owner_cik")
            if len(owners) >= min_insiders and total >= min_value:
                last = w.sort_values("date").iloc[-1]
                rows.append({
                    "issuer_cik": cik,
                    "window_start": start.strftime("%Y-%m-%d"),
                    "signal_date": w["date"].max().strftime("%Y-%m-%d"),
                    "ticker": last["ticker"], "issuer": last["issuer"],
                    "n_insiders": len(owners), "total_value": round(total, 2),
                    "insiders": "; ".join(f"{r.owner} ({r.role})" for r in owners.itertuples()),
                    "price_at_signal": "", "ret_5d": "", "ret_20d": "",
                })
                covered_until = end
    return pd.DataFrame(rows, columns=CLUSTER_COLUMNS)
