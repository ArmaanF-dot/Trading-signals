"""FCA aggregate net short positions (ANSP): parse, snapshot, diff.

Since 13 July 2026 the FCA publishes anonymised aggregates only (one row per company,
no position holders), as a daily CSV. Events are therefore per ISIN.
"""
import io
from pathlib import Path

import pandas as pd

import config
from edge import http

SNAP_COLS = ["issuer", "isin", "net_short_pct", "position_date"]
EVENT_COLUMNS = ["date", "event", "issuer", "isin", "prev_pct", "new_pct", "delta_pp",
                 "ticker", "price_at_signal", "ret_5d", "ret_20d", "bench_ret_5d", "bench_ret_20d"]

_ALIASES = {
    "issuer": ["name of company", "name of share issuer", "issuer"],
    "isin": ["international securities identification number (isin)", "isin"],
    "net_short_pct": ["aggregated net short position (%)", "net short position (%)"],
    "position_date": ["position date"],
}


def parse_csv(text: str) -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(text.lstrip("\ufeff\u00ef\u00bb\u00bf")), dtype=str, keep_default_na=False)
    cols = {c.strip().lower(): c for c in raw.columns}
    out = pd.DataFrame()
    for k, names in _ALIASES.items():
        col = next((cols[n] for n in names if n in cols), None)
        if col is None:
            raise ValueError(f"FCA file missing column for {k}: {list(raw.columns)}")
        out[k] = raw[col].str.strip()
    out = out[out["isin"] != ""]
    out["net_short_pct"] = pd.to_numeric(out["net_short_pct"], errors="coerce")
    out = out.dropna(subset=["net_short_pct"])
    out["position_date"] = pd.to_datetime(out["position_date"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    return out.drop_duplicates("isin", keep="last").reset_index(drop=True)[SNAP_COLS]


def diff(prev: pd.DataFrame, cur: pd.DataFrame, today: str, threshold: float = config.FCA_CHANGE_THRESHOLD_PP) -> pd.DataFrame:
    """Events per ISIN: new, cover, increase, decrease."""
    p = prev.set_index("isin")
    c = cur.set_index("isin")
    rows = []

    def ev(kind, isin, issuer, a, b):
        rows.append({"date": today, "event": kind, "issuer": issuer, "isin": isin,
                     "prev_pct": a, "new_pct": b, "delta_pp": round(b - a, 3), "ticker": "",
                     "price_at_signal": "", "ret_5d": "", "ret_20d": "", "bench_ret_5d": "", "bench_ret_20d": ""})

    for isin, r in c.iterrows():
        if isin not in p.index:
            ev("new", isin, r["issuer"], 0.0, r["net_short_pct"])
        else:
            d = r["net_short_pct"] - p.loc[isin, "net_short_pct"]
            if abs(d) >= threshold - 1e-9:
                ev("increase" if d > 0 else "decrease", isin, r["issuer"], p.loc[isin, "net_short_pct"], r["net_short_pct"])
    for isin, r in p.iterrows():
        if isin not in c.index:
            ev("cover", isin, r["issuer"], r["net_short_pct"], 0.0)
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def latest_snapshot(directory: Path, before: str | None = None) -> pd.DataFrame:
    files = sorted(directory.glob("*.csv")) if directory.exists() else []
    if before:
        files = [f for f in files if f.stem < before]
    if not files:
        return pd.DataFrame(columns=SNAP_COLS)
    return pd.read_csv(files[-1], dtype={"isin": str, "issuer": str, "position_date": str})


def download() -> str:
    # decode ourselves: the file starts with a UTF-8 BOM that requests would mis-guess as latin-1
    raw = http.get(config.FCA_SHORTS_URL, headers={"User-Agent": "trading-signals-research"}).content
    return raw.decode("utf-8-sig")
