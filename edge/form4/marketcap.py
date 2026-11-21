"""Approximate market cap = shares outstanding (SEC XBRL "dei" cover-page fact) x last buy price.

Failures return None (market cap unknown); unknown is kept by the filter, never silently dropped.
"""
import json

import pandas as pd

import config
from edge import http, store


def fetch_shares_outstanding(cik: str) -> float | None:
    url = config.SHARES_OUT_URL.format(cik=str(cik).zfill(10))
    try:
        headers = {"User-Agent": config.sec_user_agent(), "Accept-Encoding": "gzip, deflate"}
        facts = json.loads(http.get(url, headers=headers, min_interval=config.SEC_MIN_INTERVAL).text)
        rows = [r for r in facts["units"]["shares"] if r.get("val")]
        return float(max(rows, key=lambda r: r.get("end", ""))["val"])
    except Exception:  # missing concept (404), bad JSON, network: unknown
        return None


def shares_for(ciks, fetch=fetch_shares_outstanding) -> dict[str, float]:
    """Shares outstanding per CIK, cached in a CSV (it changes slowly; unknowns are retried)."""
    cache = store.read_csv(config.SHARES_CACHE_CSV)
    known = dict(zip(cache["cik"], map(float, cache["shares"]))) if not cache.empty else {}
    new = {}
    for cik in ciks:
        if cik not in known:
            v = fetch(cik)
            if v:
                known[cik] = new[cik] = v
    if new:
        config.SHARES_CACHE_CSV.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"cik": list(known), "shares": list(known.values())}).to_csv(config.SHARES_CACHE_CSV, index=False)
    return known


def apply_cap_filter(clusters: pd.DataFrame, fetch=fetch_shares_outstanding,
                     max_cap: float = config.CLUSTER_MAX_MARKET_CAP) -> pd.DataFrame:
    """Fill market_cap and drop clusters whose known cap exceeds max_cap."""
    if clusters.empty:
        return clusters
    out = clusters.copy()
    shares = shares_for(set(out["issuer_cik"]), fetch)
    out["market_cap"] = [
        round(shares[c] * float(p)) if c in shares else ""
        for c, p in zip(out["issuer_cik"], out["last_price"])
    ]
    keep = [m == "" or m <= max_cap for m in out["market_cap"]]
    return out[keep].reset_index(drop=True)
