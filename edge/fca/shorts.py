"""FCA daily short-position spreadsheet: parse, snapshot, diff."""
from datetime import date
from pathlib import Path

import pandas as pd

import config
from edge import http

SNAP_COLS = ["holder", "issuer", "isin", "net_short_pct", "position_date"]
EVENT_COLUMNS = ["date", "event", "holder", "issuer", "isin", "prev_pct", "new_pct", "delta_pp",
                 "ticker", *["price_at_signal", "ret_5d", "ret_20d"]]

_ALIASES = {
    "holder": ["position holder"],
    "issuer": ["name of share issuer", "issuer"],
    "isin": ["isin"],
    "net_short_pct": ["net short position (%)", "net short position"],
    "position_date": ["position date"],
}


def parse_xlsx(source) -> pd.DataFrame:
    """Read the 'Current Disclosures' sheet (header row located by the ISIN column)."""
    sheets = pd.read_excel(source, sheet_name=None, header=None, dtype=str)
    name = next((n for n in sheets if "current" in n.lower()), next(iter(sheets)))
    raw = sheets[name].fillna("")
    hdr = next(i for i in range(len(raw)) if any(str(v).strip().lower() == "isin" for v in raw.iloc[i]))
    cols = [str(v).strip().lower() for v in raw.iloc[hdr]]
    body = raw.iloc[hdr + 1:].copy()
    body.columns = cols
    out = pd.DataFrame()
    for k, names in _ALIASES.items():
        col = next((c for c in cols if c in names), None)
        if col is None:
            raise ValueError(f"FCA sheet missing column for {k}: {cols}")
        out[k] = body[col].astype(str).str.strip()
    out = out[out["isin"] != ""].reset_index(drop=True)
    out["net_short_pct"] = pd.to_numeric(out["net_short_pct"], errors="coerce")
    out = out.dropna(subset=["net_short_pct"])
    out["position_date"] = pd.to_datetime(out["position_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    return out.reset_index(drop=True)[SNAP_COLS]


def diff(prev: pd.DataFrame, cur: pd.DataFrame, today: str, threshold: float = config.FCA_CHANGE_THRESHOLD_PP) -> pd.DataFrame:
    """Events per (holder, isin): new, cover, increase, decrease."""
    key = ["holder", "isin"]
    p = prev.set_index(key) if not prev.empty else pd.DataFrame(columns=SNAP_COLS).set_index(key)
    c = cur.set_index(key)
    rows = []

    def ev(kind, k, issuer, a, b):
        rows.append({"date": today, "event": kind, "holder": k[0], "issuer": issuer, "isin": k[1],
                     "prev_pct": a, "new_pct": b, "delta_pp": round(b - a, 3), "ticker": "",
                     "price_at_signal": "", "ret_5d": "", "ret_20d": ""})

    for k, r in c.iterrows():
        if k not in p.index:
            ev("new", k, r["issuer"], 0.0, r["net_short_pct"])
        else:
            d = r["net_short_pct"] - p.loc[k, "net_short_pct"]
            if abs(d) >= threshold - 1e-9:
                ev("increase" if d > 0 else "decrease", k, r["issuer"], p.loc[k, "net_short_pct"], r["net_short_pct"])
    for k, r in p.iterrows():
        if k not in c.index:
            ev("cover", k, r["issuer"], r["net_short_pct"], 0.0)
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def latest_snapshot(directory: Path, before: str | None = None) -> pd.DataFrame:
    files = sorted(directory.glob("*.csv")) if directory.exists() else []
    if before:
        files = [f for f in files if f.stem < before]
    if not files:
        return pd.DataFrame(columns=SNAP_COLS)
    return pd.read_csv(files[-1], dtype={"isin": str, "holder": str, "issuer": str, "position_date": str})


def download() -> bytes:
    return http.get(config.FCA_SHORTS_URL, headers={"User-Agent": "trading-signals-research"}).content
