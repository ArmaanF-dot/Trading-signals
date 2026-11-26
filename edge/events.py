"""Upcoming events for Baco: company earnings, the macro calendar and market headlines.

All free, no keys, fetched at build time (so the live site never calls these from the browser):
  - Earnings: Nasdaq's public earnings calendar, one request per weekday, kept to the biggest
    companies plus any ticker we are told to care about (watchlist, insider clusters).
  - Macro: the Forex Factory weekly calendar JSON, kept to USD, GBP and EUR events that move markets.
  - Headlines: BBC News business RSS and Yahoo Finance's market RSS (titles and links only).
Every function takes `get` so the tests run offline against fixtures.
"""
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
NASDAQ_EARNINGS = "https://api.nasdaq.com/api/calendar/earnings?date={day}"
MACRO_URLS = ["https://nfs.faireconomy.media/ff_calendar_thisweek.json",
              "https://nfs.faireconomy.media/ff_calendar_nextweek.json"]
NEWS_FEEDS = [("BBC News", "https://feeds.bbci.co.uk/news/business/rss.xml"),
              ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex")]

EARNINGS_DAYS = 14          # look-ahead window
EARNINGS_MIN_CAP = 20e9     # always keep companies at least this big
EARNINGS_MAX_ROWS = 80
TIME_LABEL = {"time-pre-market": "Before open", "time-after-hours": "After close", "time-not-supplied": "Time not given"}
MACRO_CCY = {"USD", "GBP", "EUR"}
MACRO_IMPACT = {"High": 2, "Medium": 1}


def _money(text) -> float | None:
    s = re.sub(r"[^\d.]", "", str(text or ""))
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _eps(text) -> float | None:
    s = str(text or "").strip()
    neg = s.startswith("(") or s.startswith("-")
    v = _money(s)
    return None if v is None else (-v if neg else v)


def earnings(today: date, get=requests.get, extra: set[str] | None = None, days: int = EARNINGS_DAYS,
             pause: float = 0.25) -> list[dict]:
    """Earnings reports in the next `days` days: the biggest companies plus tickers in `extra`."""
    extra = {t.upper() for t in (extra or set())}
    rows = []
    for i in range(days + 1):
        day = today + timedelta(days=i)
        if day.weekday() >= 5:
            continue
        try:
            r = get(NASDAQ_EARNINGS.format(day=day.isoformat()),
                    headers={"User-Agent": BROWSER_UA, "Accept": "application/json"}, timeout=20)
            body = (r.json() or {}).get("data") or {}
            raw = body.get("rows") or []
        except (requests.RequestException, ValueError, AttributeError):
            continue
        for x in raw:
            sym = (x.get("symbol") or "").strip().upper()
            cap = _money(x.get("marketCap"))
            if not sym or not ((cap or 0) >= EARNINGS_MIN_CAP or sym in extra):
                continue
            rows.append({"date": day.isoformat(), "symbol": sym, "name": (x.get("name") or "").strip(),
                         "market_cap": cap, "time": TIME_LABEL.get(x.get("time"), "Time not given"),
                         "eps_forecast": _eps(x.get("epsForecast")), "estimates": _money(x.get("noOfEsts")),
                         "quarter": x.get("fiscalQuarterEnding"), "watch": sym in extra})
        if pause:
            time.sleep(pause)
    rows.sort(key=lambda r: (r["date"], -(r["market_cap"] or 0)))
    # Keep every watched name, then fill with the biggest.
    keep = [r for r in rows if r["watch"]]
    rest = sorted((r for r in rows if not r["watch"]), key=lambda r: -(r["market_cap"] or 0))[:max(0, EARNINGS_MAX_ROWS - len(keep))]
    return sorted(keep + rest, key=lambda r: (r["date"], -(r["market_cap"] or 0)))


def macro(get=requests.get) -> list[dict]:
    """High and medium impact USD, GBP and EUR releases this week and next, in UTC."""
    out, seen = [], set()
    for url in MACRO_URLS:
        try:
            r = get(url, headers={"User-Agent": BROWSER_UA}, timeout=20)
            items = r.json() if r.status_code == 200 else []
        except (requests.RequestException, ValueError):
            continue
        for x in items if isinstance(items, list) else []:
            if x.get("country") not in MACRO_CCY or x.get("impact") not in MACRO_IMPACT:
                continue
            try:
                when = datetime.fromisoformat(x["date"]).astimezone(timezone.utc)
            except (KeyError, ValueError):
                continue
            key = (when.isoformat(), x.get("country"), x.get("title"))
            if key in seen:
                continue
            seen.add(key)
            out.append({"when": when.isoformat(timespec="minutes"), "country": x["country"], "title": x.get("title"),
                        "impact": x["impact"], "forecast": x.get("forecast") or None, "previous": x.get("previous") or None})
    out.sort(key=lambda r: (r["when"], -MACRO_IMPACT[r["impact"]]))
    return out


def _feed_items(xml_text: str, source: str, limit: int) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not title or not link.startswith("http"):
            continue
        stamp = None
        try:
            stamp = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc).isoformat(timespec="minutes")
        except (TypeError, ValueError):
            pass
        items.append({"title": title, "link": link, "source": source, "published": stamp})
        if len(items) >= limit:
            break
    return items


def news(get=requests.get, per_feed: int = 8) -> list[dict]:
    """Latest business headlines, newest first. Titles and links only; the reader opens the source."""
    out = []
    for source, url in NEWS_FEEDS:
        try:
            r = get(url, headers={"User-Agent": BROWSER_UA}, timeout=20)
            if r.status_code == 200:
                out += _feed_items(r.text, source, per_feed)
        except requests.RequestException:
            continue
    out.sort(key=lambda r: r["published"] or "", reverse=True)
    return out
