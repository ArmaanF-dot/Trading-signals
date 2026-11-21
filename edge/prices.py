"""Free daily closes from Stooq, and the return-tracking columns used by every signal.

Stooq symbols: US "aapl.us", UK "vod.uk". Failures never raise: returns stay blank
and are retried on the next run.
"""
import io

import pandas as pd
import requests

import config

RETURN_COLUMNS = ["price_at_signal", "ret_5d", "ret_20d"]


def stooq_symbol(ticker: str, market: str) -> str:
    t = ticker.strip().lower().replace(".l", "")
    return f"{t}.{'uk' if market == 'uk' else 'us'}"


def fetch_closes(symbol: str) -> pd.Series:
    """Daily close series indexed by date; empty on any failure."""
    try:
        resp = requests.get(config.STOOQ_URL.format(symbol=symbol), timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        if "Close" not in df or df.empty:
            return pd.Series(dtype=float)
        return df.set_index(pd.to_datetime(df["Date"]))["Close"].astype(float).sort_index()
    except (requests.RequestException, ValueError, KeyError):
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
        sym = stooq_symbol(row[ticker_col], market)
        if sym not in cache:
            cache[sym] = fetch(sym)
        for k, v in returns_for(cache[sym], row[date_col]).items():
            df.at[i, k] = v
    return df
