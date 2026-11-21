"""ISIN -> London ticker via Yahoo's search endpoint, cached in data/isin_ticker.csv (isin,ticker)."""
import pandas as pd
import requests

import config
from edge import store


def search_ticker(isin: str) -> str | None:
    try:
        r = requests.get(config.YAHOO_SEARCH_URL.format(q=isin), headers={"User-Agent": config.YAHOO_USER_AGENT}, timeout=15)
        if r.status_code != 200:
            return None
        quotes = [q for q in r.json().get("quotes", []) if q.get("quoteType") == "EQUITY" and str(q.get("symbol", "")).endswith(".L")]
        return quotes[0]["symbol"] if quotes else None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def map_isins(isins, search=search_ticker, workers: int = 4) -> dict[str, str]:
    """Known mappings come from the cache; unknown ISINs are searched once (misses are cached as blank)."""
    from concurrent.futures import ThreadPoolExecutor
    cache = store.read_csv(config.ISIN_TICKER_CSV)
    known = dict(zip(cache["isin"], cache["ticker"])) if not cache.empty else {}
    todo = sorted(set(isins) - set(known))
    if todo:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for isin, t in zip(todo, ex.map(search, todo)):
                known[isin] = t or ""
        config.ISIN_TICKER_CSV.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"isin": list(known), "ticker": list(known.values())}).to_csv(config.ISIN_TICKER_CSV, index=False)
    return {k: v for k, v in known.items() if v}
