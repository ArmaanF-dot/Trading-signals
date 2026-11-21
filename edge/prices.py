"""Free daily closes from Yahoo Finance (unofficial chart endpoint), and the return-tracking columns used by every signal.

Yahoo symbols: US "AAPL", UK "VOD.L". Failures never raise: returns stay blank
and are retried on the next run.
"""
import time

import pandas as pd
import requests

import config

RETURN_COLUMNS = ["price_at_signal", "ret_5d", "ret_20d"]


def yahoo_symbol(ticker: str, market: str) -> str:
    """US: "BRK.B" -> "BRK-B". UK: "VOD" -> "VOD.L"."""
    t = ticker.strip().upper()
    if market == "uk":
        return t if t.endswith(".L") else f"{t}.L"
    return t.replace(".", "-")


def fetch_closes(symbol: str) -> pd.Series:
    """Daily adjusted closes from Yahoo's chart endpoint, indexed by date; empty on any failure.

    Retries a few times on 429/5xx. Failures never raise (returns stay blank, retried next run).
    """
    url = config.YAHOO_URL.format(symbol=symbol)
    for attempt in range(3):
        try:
            resp = requests.get(url, headers={"User-Agent": config.YAHOO_USER_AGENT}, timeout=15)
            if resp.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            if resp.status_code != 200:
                return pd.Series(dtype=float)
            res = resp.json()["chart"]["result"][0]
            adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or res["indicators"]["quote"][0]["close"]
            idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
            s = pd.Series(adj, index=idx, dtype=float).dropna()
            return s[~s.index.duplicated(keep="last")].sort_index()
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
            return pd.Series(dtype=float)
    return pd.Series(dtype=float)


def returns_for(closes: pd.Series, signal_date: str) -> dict:
    """price_at_signal = first close on/after the signal date; returns are simple,
    measured 5 and 20 trading days later. Blank if the horizon has not happened yet."""
    out = {c: "" for c in RETURN_COLUMNS}
    if closes.empty:
        return out
    after = closes[closes.index >= pd.Timestamp(signal_date)]
    if after.empty:
        return out
    p0 = after.iloc[0]
    out["price_at_signal"] = round(float(p0), 4)
    for n, col in ((5, "ret_5d"), (20, "ret_20d")):
        if len(after) > n:
            out[col] = round(float(after.iloc[n] / p0 - 1), 4)
    return out


def fill_returns(df: pd.DataFrame, ticker_col: str, date_col: str, market: str, fetch=fetch_closes) -> pd.DataFrame:
    """Fill blank return columns where possible (rows with ret_20d already set are skipped)."""
    if df.empty:
        return df
    df = df.astype(object)  # str-typed CSV frames can't hold floats
    cache: dict[str, pd.Series] = {}
    for i, row in df.iterrows():
        if row.get("ret_20d", "") != "" or not row.get(ticker_col):
            continue
        sym = yahoo_symbol(row[ticker_col], market)
        if sym not in cache:
            cache[sym] = fetch(sym)
        for k, v in returns_for(cache[sym], row[date_col]).items():
            df.at[i, k] = v
    return df
