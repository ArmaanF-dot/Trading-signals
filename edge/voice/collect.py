"""Earnings-call audio collector: vocal features per call, stored with timing and intraday prices.

Source of audio. Company IR webcasts sit behind several vendors (Q4, ON24, Notified, Chorus Call,
Zoom, each with its own player, registration walls or bot blocks; edge.media-server.com disallows
all crawlers in robots.txt, investor.apple.com returns 403). Fetching them one by one is not
feasible. Instead we use Castify's public podcast feeds (casti.fyi robots.txt allows crawling),
which republish the recording of each call as an MP3 for about 1,000 US companies, with the last
4-8 quarters in each feed. See reports/voice_feasibility.md for the checks.

What is kept. The MP3 is streamed to a temporary file, analysed (edge.voice.features) and deleted.
Only derived numbers are committed: per-call summaries, per-turn features and 5-minute prices. No
audio and no transcript, so the public repo holds nothing copyrighted.

Files (data/voice/):
  feeds.csv            ticker,slug,rss          catalogue cache, filled as tickers come up
  calls.csv            one row per call: ticker, event date, timing (bmo/amc/unknown from Nasdaq),
                       market cap, then the summary features
  turns/YYYY-MM.csv.gz one row per speaker turn
  bars/YYYY-MM.csv.gz  5-minute bars (incl. pre/post market) from the day before the call to two
                       days after; Yahoo only keeps 60 days of 5-minute history, so older
                       backfilled calls have no bars (daily returns are fetched at test time)
  seen.txt             episode ids already processed

Order of work each run: (1) calls from the last RECENT_DAYS days (seen on the Nasdaq earnings
calendar) so the intraday window is captured; (2) backfill of older episodes, newest first, until
the time budget is spent. Failures are logged and retried on a later run.
"""
from __future__ import annotations

import csv
import datetime as dt
import email.utils
import os
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

import config
from edge import http
from edge.voice import features

VOICE_DIR = config.DATA_DIR / "voice"
BASE = "https://casti.fyi"
UA = "Mozilla/5.0 (compatible; trading-signals-research)"
NASDAQ_CAL = "https://api.nasdaq.com/api/calendar/earnings?date={date}"
YAHOO_5M = ("https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            "?period1={p1}&period2={p2}&interval=5m&includePrePost=true")
RECENT_DAYS = 8
MIN_INTERVAL = 1.0
MAX_AUDIO_MB = 250
MAX_FAILS = 3
SUMMARY_FIRST = ["ticker", "event_date", "episode", "guid", "timing", "mcap", "processed_at"]


def log(*a):
    print("voice:", *a, flush=True)


def parse_catalogue(html: str) -> list[dict]:
    """Rows {ticker, slug, n} from casti.fyi/listen/earnings (an inline JS list)."""
    out = []
    for name, slug, n in re.findall(r'\{n:"(.*?)",s:"(.*?)",a:".*?",c:\s*(\d+)\s*\}', html):
        m = re.search(r"\(\$([A-Z0-9.\-]+)\)\s*$", name)
        if m:
            out.append({"ticker": m.group(1), "slug": slug, "n": int(n)})
    return out


def parse_rss_id(html: str) -> str | None:
    m = re.search(r"/rss/([0-9a-f]{16,})\.xml", html)
    return m.group(1) if m else None


def parse_feed(xml_text: str) -> list[dict]:
    """Episodes {title, date, guid, url} from a Castify feed."""
    root = ET.fromstring(xml_text)
    out = []
    for it in root.iter("item"):
        enc = it.find("enclosure")
        pub = it.findtext("pubDate")
        if enc is None or not pub:
            continue
        d = email.utils.parsedate_to_datetime(pub).date().isoformat()
        url = enc.get("url")
        guid = (it.findtext("guid") or url or "").strip()
        out.append({"title": (it.findtext("title") or "").strip(), "date": d, "guid": guid, "url": url})
    return out


def parse_calendar(payload: dict) -> dict[str, dict]:
    """{ticker: {timing, mcap}} from one day of the Nasdaq calendar."""
    rows = ((payload or {}).get("data") or {}).get("rows") or []
    out = {}
    for r in rows:
        t = {"time-pre-market": "bmo", "time-after-hours": "amc"}.get(r.get("time"), "unknown")
        mc = re.sub(r"[^0-9]", "", r.get("marketCap") or "")
        out[r["symbol"]] = {"timing": t, "mcap": int(mc) if mc else ""}
    return out


def episode_id(ep: dict) -> str:
    return ep["guid"] or ep["url"]


def pick_episodes(eps: list[dict], seen: set[str]) -> list[dict]:
    return [e for e in eps if episode_id(e) not in seen]


def parse_bars(payload: dict) -> pd.DataFrame:
    cols = ["ts", "open", "high", "low", "close", "volume"]
    try:
        res = payload["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        df = pd.DataFrame({"ts": res["timestamp"], **{k: q[k] for k in cols[1:]}})
    except (KeyError, IndexError, TypeError):
        return pd.DataFrame(columns=cols)
    return df.dropna(subset=["close"]).reset_index(drop=True)


def fetch_json(url: str, get=None) -> dict | None:
    try:
        r = (get or http.get)(url, headers={"User-Agent": UA}, min_interval=MIN_INTERVAL)
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def fetch_bars(ticker: str, event_date: str, get=None) -> pd.DataFrame:
    """5-minute bars from the day before the call to two days after (empty if older than ~58 days)."""
    d = dt.date.fromisoformat(event_date)
    if (dt.date.today() - d).days > 58:
        return parse_bars({})
    p1 = int(dt.datetime.combine(d - dt.timedelta(days=2), dt.time(), dt.timezone.utc).timestamp())
    p2 = int(dt.datetime.combine(d + dt.timedelta(days=4), dt.time(), dt.timezone.utc).timestamp())
    sym = ticker.replace(".", "-")
    payload = fetch_json(YAHOO_5M.format(symbol=sym, p1=p1, p2=p2), get)
    df = parse_bars(payload or {})
    if df.empty:
        return df
    lo = int(dt.datetime.combine(d - dt.timedelta(days=1), dt.time(), dt.timezone.utc).timestamp())
    hi = int(dt.datetime.combine(d + dt.timedelta(days=3), dt.time(), dt.timezone.utc).timestamp())
    return df[(df["ts"] >= lo) & (df["ts"] < hi)].reset_index(drop=True)


def download(url: str, dest: Path) -> bool:
    """Stream an MP3 to `dest`; False on failure or if it is implausibly large."""
    try:
        with requests.get(url, headers={"User-Agent": UA}, stream=True, timeout=60) as r:
            r.raise_for_status()
            size = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    size += len(chunk)
                    if size > MAX_AUDIO_MB << 20:
                        return False
                    f.write(chunk)
        return size > 100_000
    except requests.RequestException:
        return False


def _append_monthly(df: pd.DataFrame, directory: Path, month: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / f"{month}.csv.gz"
    if p.exists():
        df = pd.concat([pd.read_csv(p), df], ignore_index=True)
    df.to_csv(p, index=False, compression="gzip")


def _append_call(row: dict, path: Path) -> None:
    """Append to calls.csv, widening the header if a new feature column appears."""
    new = pd.DataFrame([row])
    if path.exists():
        old = pd.read_csv(path, dtype={"guid": str})
        new = pd.concat([old, new], ignore_index=True)
    first = [c for c in SUMMARY_FIRST if c in new.columns]
    new = new[first + [c for c in new.columns if c not in first]]
    new.to_csv(path, index=False)


def process_episode(ticker: str, ep: dict, meta: dict, data_dir: Path, analyse=None, dl=None, get=None) -> bool:
    """Download, analyse, store features and bars, delete the audio. True if stored."""
    analyse = analyse or features.analyse
    dl = dl or download
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "call.mp3"
        if not dl(ep["url"], f):
            log(f"{ticker} {ep['date']}: download failed")
            return False
        try:
            x = features.decode(str(f))
        except Exception as exc:  # ffmpeg failure: corrupt or empty file
            log(f"{ticker} {ep['date']}: decode failed ({exc})")
            return False
    if len(x) < features.SR * 600:
        log(f"{ticker} {ep['date']}: under 10 minutes of audio, skipped")
        return False
    rows, summary = analyse(x)
    if not rows:
        log(f"{ticker} {ep['date']}: no speech found")
        return False
    month = ep["date"][:7]
    turns = pd.DataFrame(rows)
    turns.insert(0, "event_date", ep["date"])
    turns.insert(0, "ticker", ticker)
    _append_monthly(turns, data_dir / "turns", month)
    bars = fetch_bars(ticker, ep["date"], get)
    if not bars.empty:
        bars.insert(0, "event_date", ep["date"])
        bars.insert(0, "ticker", ticker)
        _append_monthly(bars, data_dir / "bars", month)
    row = {"ticker": ticker, "event_date": ep["date"], "episode": ep["title"], "guid": episode_id(ep),
           "timing": meta.get("timing", "unknown"), "mcap": meta.get("mcap", ""),
           "processed_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "bars": len(bars), **summary}
    _append_call(row, data_dir / "calls.csv")
    with open(data_dir / "seen.txt", "a") as fh:
        fh.write(episode_id(ep) + "\n")
    return True


def _load_fails(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        n, _, k = line.partition("\t")
        if k:
            out[k] = int(n)
    return out


def load_feeds(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with open(path, newline="") as fh:
        return {r["ticker"]: r for r in csv.DictReader(fh)}


def save_feeds(feeds: dict[str, dict], path: Path) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "slug", "rss"])
        w.writeheader()
        for k in sorted(feeds):
            w.writerow({c: feeds[k].get(c, "") for c in ["ticker", "slug", "rss"]})


def run(budget_s: float | None = None, max_calls: int | None = None, data_dir: Path | None = None, get=None,
        analyse=None, dl=None, today: str | None = None) -> int:
    data_dir = Path(data_dir or VOICE_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    budget_s = float(os.environ.get("VOICE_BUDGET_S", budget_s or 4 * 3600))
    start = time.monotonic()
    today_d = dt.date.fromisoformat(today) if today else dt.date.today()
    get = get or http.get

    def text(url):
        return get(url, headers={"User-Agent": UA}, min_interval=MIN_INTERVAL).text

    seen = set((data_dir / "seen.txt").read_text().split()) if (data_dir / "seen.txt").exists() else set()
    fails = _load_fails(data_dir / "fails.txt")
    seen |= {k for k, n in fails.items() if n >= MAX_FAILS}  # give up on an episode after 3 failures
    feeds = load_feeds(data_dir / "feeds.csv")
    try:
        cat = {r["ticker"]: r for r in parse_catalogue(text(f"{BASE}/listen/earnings"))}
    except requests.RequestException as exc:
        log(f"catalogue unavailable ({exc})")
        return 0
    log(f"{len(cat)} companies in the catalogue, {len(seen)} calls already processed")

    cal: dict[str, dict[str, dict]] = {}

    def cal_for(d: str) -> dict[str, dict]:
        if d not in cal:
            cal[d] = parse_calendar(fetch_json(NASDAQ_CAL.format(date=d), get) or {})
        return cal[d]

    for back in range(RECENT_DAYS + 1):
        cal_for((today_d - dt.timedelta(days=back)).isoformat())
    recent = [(t, d) for d, rows in cal.items() for t in rows if t in cat]
    recent.sort(key=lambda x: x[1], reverse=True)

    def feed_for(ticker: str) -> list[dict]:
        rec = feeds.get(ticker)
        if not rec or not rec.get("rss"):
            rid = parse_rss_id(text(f"{BASE}/listen/{cat[ticker]['slug']}"))
            if not rid:
                return []
            rec = feeds[ticker] = {"ticker": ticker, "slug": cat[ticker]["slug"], "rss": rid}
            save_feeds(feeds, data_dir / "feeds.csv")
        return parse_feed(text(f"{BASE}/rss/{rec['rss']}.xml"))

    done = failed = 0

    def go(ticker, ep, meta) -> bool:
        nonlocal done, failed
        if time.monotonic() - start > budget_s or (max_calls is not None and done >= max_calls):
            return False
        t0 = time.monotonic()
        ok = process_episode(ticker, ep, meta, data_dir, analyse=analyse, dl=dl, get=get)
        if ok:
            seen.add(episode_id(ep))
        else:
            fails[episode_id(ep)] = fails.get(episode_id(ep), 0) + 1
            (data_dir / "fails.txt").write_text("".join(f"{n}\t{k}\n" for k, n in fails.items()))
        done += ok
        failed += not ok
        log(f"{ticker} {ep['date']} {'stored' if ok else 'FAILED'} in {time.monotonic() - t0:.0f}s")
        return True

    # 1. recent calls: match feed episodes to calendar dates (episode date = call date)
    stop = False
    for ticker, d in recent:
        if stop:
            break
        try:
            eps = [e for e in pick_episodes(feed_for(ticker), seen) if e["date"] == d]
        except (requests.RequestException, ET.ParseError):
            continue
        for ep in eps:
            if not go(ticker, ep, cal_for(d)[ticker]):
                stop = True
                break

    # 2. backfill: every other unseen episode, newest first
    if not stop:
        todo = []
        for ticker in sorted(cat, key=lambda t: -cat[t]["n"]):
            if time.monotonic() - start > budget_s:
                break
            try:
                for ep in pick_episodes(feed_for(ticker), seen):
                    todo.append((ep["date"], ticker, ep))
            except (requests.RequestException, ET.ParseError):
                continue
            if len(todo) >= (max_calls or 10**9) * 3 and max_calls:
                break
        todo.sort(key=lambda x: x[0], reverse=True)
        for d, ticker, ep in todo:
            meta = cal_for(d).get(ticker) or {}
            if not go(ticker, ep, meta):
                break
    log(f"stored {done}, failed {failed}")
    return done
