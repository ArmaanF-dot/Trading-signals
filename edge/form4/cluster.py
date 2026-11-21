"""Cluster-buy detection over the stored purchase rows."""
import pandas as pd

import config

CLUSTER_COLUMNS = [
    "issuer_cik", "window_start", "signal_date", "ticker", "issuer", "n_insiders",
    "total_value", "insiders", "last_price", "market_cap", "price_at_signal", "ret_5d", "ret_20d",
]


def _flag(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1"])


def assign_buyer_ids(buys: pd.DataFrame) -> pd.Series:
    """Owners that appear on the identical trade (same filing, date, shares, price) are one
    economic buyer, e.g. a person plus their own fund on a joint Form 4. Union them."""
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _, g in buys.groupby(["accession", "date", "shares", "price"]):
        ciks = list(g["owner_cik"])
        for other in ciks[1:]:
            parent[find(other)] = find(ciks[0])
    return buys["owner_cik"].map(find)


def load_buys(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a str-typed CSV frame to proper dtypes."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    for c in ("is_director", "is_officer", "is_ten_pct"):
        if c in df:
            df[c] = _flag(df[c])
    for c in ("shares", "price", "value"):
        df[c] = pd.to_numeric(df[c])
    return df


def find_clusters(
    buys: pd.DataFrame,
    min_insiders: int = config.CLUSTER_MIN_INSIDERS,
    window_days: int = config.CLUSTER_WINDOW_DAYS,
    min_value: float = config.CLUSTER_MIN_VALUE,
    require_insider: bool = config.CLUSTER_REQUIRE_OFFICER_OR_DIRECTOR,
) -> pd.DataFrame:
    """Return one row per cluster. Windows run [start, start + window_days] where
    start is a buy date; once a window qualifies, later starts inside it are skipped
    so each cluster is emitted once."""
    rows = []
    if buys.empty:
        return pd.DataFrame(columns=CLUSTER_COLUMNS)
    buys = buys.copy()
    buys["buyer_id"] = assign_buyer_ids(buys)
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
            owners = w.drop_duplicates("buyer_id")
            has_insider = True
            if require_insider and {"is_director", "is_officer"} <= set(w.columns):
                has_insider = bool((w["is_director"] | w["is_officer"]).any())
            if len(owners) >= min_insiders and total >= min_value and has_insider:
                last = w.sort_values("date").iloc[-1]
                rows.append({
                    "issuer_cik": cik,
                    "window_start": start.strftime("%Y-%m-%d"),
                    "signal_date": w["date"].max().strftime("%Y-%m-%d"),
                    "ticker": last["ticker"], "issuer": last["issuer"],
                    "n_insiders": len(owners), "total_value": round(total, 2),
                    "insiders": "; ".join(f"{r.owner} ({r.role})" for r in owners.itertuples()),
                    "last_price": float(last["price"]), "market_cap": "",
                    "price_at_signal": "", "ret_5d": "", "ret_20d": "",
                })
                covered_until = end
    return pd.DataFrame(rows, columns=CLUSTER_COLUMNS)
