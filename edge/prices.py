"""Free daily closes from Yahoo Finance (unofficial chart endpoint), and the return-tracking columns used by every signal.

Yahoo symbols: US "AAPL", UK "VOD.L". Failures never raise: returns stay blank
and are retried on the next run.
"""
import time

import pandas as pd
import requests

import config

RETURN_COLUMNS = ["price_at_signal", "ret_5d", "ret_20d", "bench_ret_5d", "bench_ret_20d"]


def yahoo_symbol(ticker: str, market: str) -> str:
    """US: "BRK.B" -> "BRK-B". UK: "VOD" -> "VOD.L"."""
    t = ticker.strip().upper()
    if market == "uk":
        return t if t.endswith(".L") else f"{t}.L"
    return t.replace(".", "-")


def fetch_bars(symbol: str, url_template: str | None = None) -> pd.DataFrame:
    """Daily bars from Yahoo's chart endpoint: columns close (dividend/split adjusted) and
    volume (raw shares), indexed by date. Empty frame on any failure; never raises.
    Retries a few times on 429/5xx."""
    empty = pd.DataFrame(columns=["close", "volume"], dtype=float)
    url = (url_template or config.YAHOO_URL).format(symbol=symbol)
    for attempt in range(3):
        try:
            resp = requests.get(url, headers={"User-Agent": config.YAHOO_USER_AGENT}, timeout=15)
            if resp.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            if resp.status_code != 200:
                return empty
            res = resp.json()["chart"]["result"][0]
            quote = res["indicators"]["quote"][0]
            adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or quote["close"]
            idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
            df = pd.DataFrame({"close": pd.Series(adj, index=idx, dtype=float),
                               "volume": pd.Series(quote.get("volume") or [None] * len(idx), index=idx, dtype=float)})
            df = df.dropna(subset=["close"])
            return df[~df.index.duplicated(keep="last")].sort_index()
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
            return empty
    return empty


def fetch_closes(symbol: str) -> pd.Series:
    """Daily adjusted closes indexed by date; empty on any failure."""
    bars = fetch_bars(symbol)
    return bars["close"] if not bars.empty else pd.Series(dtype=float)


def returns_for(closes: pd.Series, public_date: str, bench: pd.Series | None = None) -> dict:
    """Entry = first close strictly after public_date (and within MAX_ENTRY_GAP_DAYS of it).
    Returns are simple, 5 and 20 trading days after entry; blank until the horizon has happened.
    If a benchmark series is given, bench_ret_* cover the same dates."""
    out = {c: "" for c in RETURN_COLUMNS}
    if closes.empty:
        return out
    t = pd.Timestamp(public_date)
    after = closes[closes.index > t]
    if after.empty or (after.index[0] - t).days > config.MAX_ENTRY_GAP_DAYS:
        return out
    p0 = float(after.iloc[0])
    out["price_at_signal"] = round(p0, 4)
    b0 = bench.asof(after.index[0]) if bench is not None and not bench.empty else None
    for n, col, bcol in ((5, "ret_5d", "bench_ret_5d"), (20, "ret_20d", "bench_ret_20d")):
        if len(after) > n:
            out[col] = round(float(after.iloc[n]) / p0 - 1, 4)
            if b0 is not None and pd.notna(b0):
                bn = bench.asof(after.index[n])
                if pd.notna(bn):
                    out[bcol] = round(float(bn) / float(b0) - 1, 4)
    return out


def fill_returns(df: pd.DataFrame, ticker_col: str, date_col: str, market: str, fetch=fetch_closes,
                 bench_symbol: str | None = None, fallback_col: str | None = None, fallback_days: int = 0) -> pd.DataFrame:
    """Fill blank return columns where possible (rows with ret_20d already set are skipped).

    date_col is the date the signal became public; if a row has none, fallback_col plus fallback_days is used."""
    if df.empty:
        return df
    df = df.copy()
    for c in RETURN_COLUMNS:
        if c not in df:
            df[c] = ""
    df = df.astype(object)  # str-typed CSV frames cannot hold floats
    cache: dict[str, pd.Series] = {}
    bench = None
    for i, row in df.iterrows():
        if row.get("ret_20d", "") not in ("", None) and str(row.get("ret_20d")) != "nan" or not row.get(ticker_col):
            continue
        d = row.get(date_col, "")
        if d in ("", None) or str(d) == "nan":
            if not fallback_col:
                continue
            d = (pd.Timestamp(row[fallback_col]) + pd.Timedelta(days=fallback_days)).strftime("%Y-%m-%d")
        sym = yahoo_symbol(row[ticker_col], market)
        if sym not in cache:
            cache[sym] = fetch(sym)
        if bench_symbol and bench is None:
            bench = fetch(bench_symbol)
        for k, v in returns_for(cache[sym], d, bench).items():
            df.at[i, k] = v
    return df
