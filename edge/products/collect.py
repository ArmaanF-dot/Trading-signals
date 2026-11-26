"""Daily snapshot of product pages for US-listed retailers and brands whose shops run on Shopify.

Shopify shops publish their catalogue at /products.json (the same file their storefront reads; it is
public, paginated and cheap). Once a day, for each site in sites.csv, we record: products listed, how many are
on sale (a compare-at price above the price), the average discount on those, the share in stock, new
listings and delistings since the last snapshot, and the median price. One request per page, at most
one a second, a plain identifying User-Agent. Nothing is stored per product except price and stock in
data/products/state.json, used to see what changed.

There is no free history of retail prices, so this only becomes testable as data accumulates. Many
listed retailers (and all the biggest) do not use Shopify or block automated reads; only the sites that
answered a test on 26 Nov 2026 are in the list. Coverage is therefore thin and skewed to small consumer brands.
"""
import csv
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import config

SITES_CSV = Path(__file__).with_name("sites.csv")
DAILY = config.ROOT / "data" / "products" / "daily.csv"
STATE = config.ROOT / "data" / "products" / "state.json"
COLS = ["date", "ticker", "status", "products", "on_sale", "avg_discount", "in_stock", "added", "removed", "median_price"]
MAX_PAGES = 12
UA = "Mozilla/5.0 (compatible; trading-signals-research; catalogue snapshot once a day)"


def load_sites(path=SITES_CSV) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def parse(products: list[dict]) -> dict[str, list]:
    """{product id: [price, compare_at (0 if none), in_stock 0/1]} (cheapest variant's price)."""
    out = {}
    for p in products:
        vs = p.get("variants") or []
        if not vs:
            continue
        price = min(float(v.get("price") or 0) for v in vs)
        cmp_ = max((float(v.get("compare_at_price") or 0) for v in vs), default=0.0)
        out[str(p["id"])] = [price, cmp_ if cmp_ > price else 0.0, int(any(v.get("available") for v in vs))]
    return out


def summarise(cur: dict[str, list], prev: dict[str, list] | None) -> dict:
    n = len(cur)
    sale = [(c - p) / c for p, c, _ in cur.values() if c > 0 and p > 0]
    return {"products": n, "on_sale": len(sale), "avg_discount": round(float(np.mean(sale)), 4) if sale else 0.0,
            "in_stock": round(sum(v[2] for v in cur.values()) / n, 4) if n else "",
            "added": len(set(cur) - set(prev)) if prev is not None else "",
            "removed": len(set(prev) - set(cur)) if prev is not None else "",
            "median_price": round(float(np.median([v[0] for v in cur.values()])), 2) if n else ""}


def fetch_site(site: str, get=requests.get, sleep=lambda s: None) -> list[dict]:
    out: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        r = get(f"https://www.{site}/products.json?limit=250&page={page}", headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        items = r.json()["products"]
        out += items
        if len(items) < 250:
            break
        sleep(1)
    return out


def run(today: str | None = None, get=requests.get, sleep=None) -> None:
    import time
    sleep = sleep or time.sleep
    today = today or dt.date.today().isoformat()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    rows = []
    for s in load_sites():
        try:
            cur = parse(fetch_site(s["site"], get, sleep))
            if not cur:
                raise ValueError("no products")
            rows.append({"date": today, "ticker": s["ticker"], "status": "ok", **summarise(cur, state.get(s["ticker"]))})
            state[s["ticker"]] = cur
        except Exception as exc:  # a failed site keeps its old state so one outage is not a mass delisting
            print(f"{s['ticker']} {s['site']}: {type(exc).__name__}: {exc}")
            rows.append({"date": today, "ticker": s["ticker"], "status": "error"})
        sleep(1)
    DAILY.parent.mkdir(parents=True, exist_ok=True)
    new = not DAILY.exists()
    with open(DAILY, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerows({c: r.get(c, "") for c in COLS} for r in rows)
    STATE.write_text(json.dumps(state, separators=(",", ":")))
    print(f"{sum(r['status'] == 'ok' for r in rows)}/{len(rows)} sites ok")


def features_at(daily: pd.DataFrame, ticker: str, event, recent_days: int = 14, base_gap: tuple[int, int] = (76, 90)) -> dict:
    """Change in discounting and stock availability before an earnings date: the average of the
    last `recent_days` days minus the average of days base_gap[0]..base_gap[1] before it (a quarter earlier).
    Blank until about 90 days of history exist."""
    e = pd.Timestamp(event)
    g = daily[(daily["ticker"] == ticker) & (daily["status"] == "ok")].copy()
    g["date"] = pd.to_datetime(g["date"])
    g["share_sale"] = g["on_sale"] / g["products"]
    age = (e - g["date"]).dt.days
    cur, base = g[(age >= 1) & (age <= recent_days)], g[(age >= base_gap[0]) & (age <= base_gap[1])]
    if len(cur) < 5 or len(base) < 5:
        return {"d_sale_share": np.nan, "d_discount": np.nan, "d_in_stock": np.nan}
    return {"d_sale_share": float(cur["share_sale"].mean() - base["share_sale"].mean()),
            "d_discount": float(cur["avg_discount"].mean() - base["avg_discount"].mean()),
            "d_in_stock": float(cur["in_stock"].astype(float).mean() - base["in_stock"].astype(float).mean())}
