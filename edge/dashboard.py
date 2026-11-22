"""Build the Hugo dashboard: copies the static page in dashboard/ to _site/ and writes
_site/data.json from the repo's signal files plus a few free delayed quotes.

Live data (Alpaca IEX, crypto, Finnhub) is fetched by the browser with keys the user types
into the page, so nothing secret ever reaches the repo or the built site.

Optional build-time secrets (environment variables, never committed):
  CLAUDE_CODE_OAUTH_TOKEN - writes the AI daily brief on the user's Claude plan via the
                       Claude Code CLI (token from `claude setup-token`).
  ANTHROPIC_API_KEY  - fallback for the AI brief (pay-per-use API); without either a
                       rule-based brief is used.
  FINNHUB_API_KEY    - pre-fills analyst recommendation trends for watchlist names.
"""
import json
import os
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

import config
from edge.store import read_csv

SOURCE_DIR = config.ROOT / "dashboard"
SITE_DIR = config.ROOT / "_site"

# Daily signal feed written by `python run.py feed` (read only here).
FEED_JSON = config.ROOT / "signals" / "feed.json"
TRACK_MD = config.ROOT / "signals" / "track_record.md"

WATCH_DAYS = 30            # Form 4 clusters shown as watchlist inputs
AVOID_LOOKBACK_DAYS = 30   # window for rising aggregate shorts
AVOID_MIN_RISE_PP = 0.5    # matches the FCA study threshold

UK_QUOTES = [("^FTSE", "FTSE 100"), ("^FTMC", "FTSE 250"), ("^FTAS", "FTSE All-Share"),
             ("GBPUSD=X", "GBP/USD"), ("EURGBP=X", "EUR/GBP")]
US_REFERENCE = [("SPY", "S&P 500 ETF"), ("QQQ", "Nasdaq 100 ETF"), ("IWM", "Russell 2000 ETF"),
                ("^VIX", "VIX"), ("GC=F", "Gold"), ("CL=F", "WTI crude"), ("^TNX", "US 10y yield")]
QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"


def _num(x):
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _records(df: pd.DataFrame, cols: list[str]) -> list[dict]:
    if df.empty:
        return []
    keep = [c for c in cols if c in df.columns]
    out = []
    for row in df[keep].to_dict("records"):
        out.append({k: (v if v != "" else None) for k, v in row.items()})
    return out


# ---------- signals ----------

def watchlist(today: date, clusters: pd.DataFrame | None = None) -> list[dict]:
    """Recent Form 4 cluster buys, newest first. A watchlist input, not a buy signal."""
    df = read_csv(config.FORM4_CLUSTERS_CSV) if clusters is None else clusters
    if df.empty or "signal_date" not in df.columns:
        return []
    cutoff = (today - timedelta(days=WATCH_DAYS)).isoformat()
    df = df[df["signal_date"] >= cutoff].copy()
    df["_v"] = pd.to_numeric(df.get("total_value"), errors="coerce")
    df = df.sort_values(["signal_date", "_v"], ascending=[False, False])
    rows = _records(df, ["signal_date", "ticker", "issuer", "n_insiders", "total_value", "insiders",
                         "market_cap", "last_price", "price_at_signal", "ret_5d", "ret_20d"])
    for r in rows:
        for k in ("n_insiders", "total_value", "market_cap", "last_price", "price_at_signal", "ret_5d", "ret_20d"):
            r[k] = _num(r.get(k))
    return rows


def load_snapshots(directory: Path = config.FCA_SNAPSHOT_DIR) -> dict[str, pd.DataFrame]:
    snaps = {}
    for p in sorted(directory.glob("*.csv")):
        df = read_csv(p)
        if not df.empty and "isin" in df.columns:
            df["net_short_pct"] = pd.to_numeric(df["net_short_pct"], errors="coerce")
            snaps[p.stem] = df
    return snaps


def _ticker_map() -> dict[str, str]:
    df = read_csv(config.ISIN_TICKER_CSV)
    if df.empty:
        return {}
    return {r["isin"]: r["ticker"] for r in df.to_dict("records") if r.get("ticker")}


def avoid_list(today: date, snaps: dict[str, pd.DataFrame] | None = None,
               events: pd.DataFrame | None = None, tickers: dict[str, str] | None = None) -> list[dict]:
    """UK names whose aggregate net short rose by >= 0.5pp within the lookback. The FCA study
    found these lag the market by about 1.4% over 60 days, so they are flagged to avoid."""
    snaps = load_snapshots() if snaps is None else snaps
    events = read_csv(config.FCA_EVENTS_CSV) if events is None else events
    tickers = _ticker_map() if tickers is None else tickers
    cutoff = (today - timedelta(days=AVOID_LOOKBACK_DAYS)).isoformat()
    found: dict[str, dict] = {}

    # 1) From snapshots: compare the latest with the last snapshot before the window
    #    (or the oldest one inside it).
    keys = sorted(snaps)
    before = [k for k in keys if k < cutoff]
    base_key = before[-1] if before else (keys[0] if keys else None)
    if base_key and base_key != keys[-1]:
        base, cur = snaps[base_key], snaps[keys[-1]]
        b = base.set_index("isin")["net_short_pct"]
        for r in cur.to_dict("records"):
            new = r["net_short_pct"]
            prev = b.get(r["isin"], 0.0)
            prev = 0.0 if pd.isna(prev) else float(prev)
            if pd.notna(new) and new - prev >= AVOID_MIN_RISE_PP - 1e-9:
                found[r["isin"]] = {"isin": r["isin"], "issuer": r["issuer"], "prev_pct": round(prev, 2),
                                    "new_pct": round(float(new), 2), "delta_pp": round(float(new) - prev, 2),
                                    "since": base_key, "date": keys[-1]}

    # 2) From the event log (cumulative rise per ISIN within the window).
    if not events.empty and "date" in events.columns:
        ev = events[events["date"] >= cutoff].copy()
        ev["delta_pp"] = pd.to_numeric(ev["delta_pp"], errors="coerce").fillna(0)
        ev["new_pct"] = pd.to_numeric(ev["new_pct"], errors="coerce")
        ev["prev_pct"] = pd.to_numeric(ev["prev_pct"], errors="coerce")
        for isin, g in ev.sort_values("date").groupby("isin"):
            rise = float(g["delta_pp"].sum())
            if rise >= AVOID_MIN_RISE_PP - 1e-9 and isin not in found:
                last = g.iloc[-1]
                first = g.iloc[0]
                found[isin] = {"isin": isin, "issuer": last["issuer"],
                               "prev_pct": _num(first["prev_pct"]) or 0.0,
                               "new_pct": _num(last["new_pct"]), "delta_pp": round(rise, 2),
                               "since": first["date"], "date": last["date"]}

    rows = sorted(found.values(), key=lambda r: -r["delta_pp"])
    for r in rows:
        r["ticker"] = tickers.get(r["isin"])
    return rows


def most_shorted(snaps: dict[str, pd.DataFrame] | None = None, n: int = 15) -> list[dict]:
    snaps = load_snapshots() if snaps is None else snaps
    if not snaps:
        return []
    key = sorted(snaps)[-1]
    df = snaps[key].dropna(subset=["net_short_pct"]).sort_values("net_short_pct", ascending=False).head(n)
    tickers = _ticker_map()
    return [{"issuer": r["issuer"], "isin": r["isin"], "net_short_pct": float(r["net_short_pct"]),
             "position_date": r.get("position_date"), "ticker": tickers.get(r["isin"]), "as_of": key}
            for r in df.to_dict("records")]


def combo_hits() -> list[dict]:
    df = read_csv(config.COMBO_CSV)
    return _records(df, ["signal_date", "company", "isin", "ticker", "n_directors", "director_value_gbp",
                         "total_net_short_pct", "ret_5d", "ret_20d"])


def feed(path: Path = FEED_JSON, track: Path = TRACK_MD) -> dict | None:
    """The daily signal feed (signals/feed.json) and its track record, shown as-is."""
    try:
        f = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    cols = ["date", "stance", "symbol", "market", "summary", "evidence"]
    rows = [{c: s.get(c) for c in cols} for s in f.get("signals", [])]
    order = {"avoid": 0, "watch": 1}
    rows.sort(key=lambda r: str(r["date"] or ""), reverse=True)
    rows.sort(key=lambda r: order.get(r["stance"], 2))
    return {"as_of": f.get("as_of"), "disclaimer": f.get("disclaimer"), "columns": cols, "rows": rows[:100],
            "track_record": track.read_text()[:6000] if track.exists() else None}


# ---------- delayed quotes ----------

def fetch_quote(symbol: str, name: str, get=requests.get) -> dict | None:
    """Last price and previous close from Yahoo's chart endpoint. Delayed (UK ~15 min)."""
    try:
        resp = get(QUOTE_URL.format(symbol=requests.utils.quote(symbol)),
                   headers={"User-Agent": config.YAHOO_USER_AGENT}, timeout=15)
        if resp.status_code != 200:
            return None
        res = resp.json()["chart"]["result"][0]
        meta = res["meta"]
        price = _num(meta.get("regularMarketPrice"))
        closes = [c for c in (res.get("indicators", {}).get("quote", [{}])[0].get("close") or []) if c is not None]
        prev = _num(meta.get("chartPreviousClose"))
        if len(closes) >= 2:
            prev = closes[-2]
        if price is None:
            return None
        ts = meta.get("regularMarketTime")
        return {"symbol": symbol, "name": name, "price": price, "prev_close": prev,
                "change_pct": (price / prev - 1) * 100 if prev else None,
                "currency": meta.get("currency"),
                "time": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None,
                "closes": [round(c, 4) for c in closes[-5:]]}
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        return None


def quotes(pairs: list[tuple[str, str]], get=requests.get) -> list[dict]:
    return [q for q in (fetch_quote(s, n, get) for s, n in pairs) if q]


def uk_name_quotes(avoid: list[dict], combos: list[dict], get=requests.get, limit: int = 12) -> list[dict]:
    seen, pairs = set(), []
    for r in combos + avoid:
        t = (r.get("ticker") or "").strip().upper()
        if t and t not in seen:
            seen.add(t)
            pairs.append((t if t.endswith(".L") else f"{t}.L", r.get("issuer") or r.get("company") or t))
    return quotes(pairs[:limit], get)


# ---------- analyst trends (optional, build time) ----------

def analyst_trends(tickers: list[str], key: str | None, get=requests.get) -> dict:
    if not key:
        return {}
    out = {}
    for t in tickers[:25]:
        try:
            r = get("https://finnhub.io/api/v1/stock/recommendation",
                    params={"symbol": t, "token": key}, timeout=15)
            if r.status_code == 200 and isinstance(r.json(), list) and r.json():
                out[t] = r.json()[:4]
        except (requests.RequestException, ValueError):
            continue
    return out


# ---------- brief ----------

def _fmt_money(v):
    if v is None:
        return "?"
    return f"${v / 1e6:.1f}m" if v >= 1e6 else f"${v / 1e3:.0f}k"


def rule_brief(data: dict) -> str:
    lines = []
    us = {q["symbol"]: q for q in data["markets"]["us_reference"]}
    uk = {q["symbol"]: q for q in data["markets"]["uk_delayed"]}
    moves = []
    for sym, label, src in (("SPY", "S&P 500", us), ("IWM", "Russell 2000", us), ("^FTSE", "FTSE 100", uk),
                            ("^FTMC", "FTSE 250", uk), ("^VIX", "VIX", us)):
        q = src.get(sym)
        if q and q.get("change_pct") is not None:
            moves.append(f"{label} {q['change_pct']:+.1f}%")
    if moves:
        lines.append("Last close: " + ", ".join(moves) + ".")
    w = data["signals"]["watchlist"]
    if w:
        top = w[:3]
        lines.append(f"{len(w)} US insider cluster buy(s) in the last {WATCH_DAYS} days. Newest: "
                     + "; ".join(f"{r['ticker'] or r['issuer']} ({int(r['n_insiders'] or 0)} insiders, "
                                 f"{_fmt_money(r['total_value'])})" for r in top)
                     + ". Treat these as names to research, not buys: the backtest found no edge after costs.")
    else:
        lines.append("No new US insider cluster buys this month.")
    a = data["signals"]["avoid"]
    if a:
        lines.append(f"{len(a)} UK name(s) saw aggregate shorts rise by 0.5pp or more: "
                     + ", ".join(f"{r['issuer']} (+{r['delta_pp']:.1f}pp to {r['new_pct']:.1f}%)" for r in a[:4])
                     + ". Historically these lagged the market, so avoid new longs.")
    else:
        lines.append("No UK names crossed the rising-shorts avoid threshold.")
    c = data["signals"]["combo"]
    if c:
        lines.append(f"UK combo (director buy on a shorted name): {', '.join(r['company'] for r in c[:4])}.")
    return " ".join(lines)


def brief_prompt(data: dict) -> str:
    compact = {"markets": data["markets"], "signals": {k: v[:10] for k, v in data["signals"].items() if isinstance(v, list)}}
    return (
        "You write a short morning brief for a retail investor's dashboard (a UK student; British spelling). "
        "Use only the JSON below. 120 to 180 words, plain prose, no headings, no bullet lists. "
        "Cover: what markets did at the last close, the notable US insider cluster buys (framed as a watchlist "
        "to research, because the project's backtest found no standalone edge after costs), and UK names with "
        "rising aggregate short interest (framed as names to avoid for new longs). Do not invent prices, news "
        "or numbers that are not in the data, and do not give personalised financial advice.\n\n"
        + json.dumps(compact, default=str)[:60000]
    )


def cli_brief(data: dict, token: str | None, run=subprocess.run) -> str | None:
    """Brief via the Claude Code CLI on the user's Claude plan (CLAUDE_CODE_OAUTH_TOKEN from
    `claude setup-token`). The prompt goes on stdin; no tools are allowed."""
    if not token or not shutil.which("claude"):
        return None
    try:
        res = run(["claude", "-p", "--output-format", "text", "--disallowedTools", "Bash,Edit,Write,WebFetch,WebSearch"],
                  input=brief_prompt(data), capture_output=True, text=True, timeout=300,
                  env={**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": token})
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Claude CLI brief failed: {type(exc).__name__}")
        return None
    text = (res.stdout or "").strip()
    if res.returncode != 0 or not text:
        print(f"Claude CLI brief failed: exit {res.returncode}")
        return None
    return text


def ai_brief(data: dict, key: str | None) -> str | None:
    """Fallback: brief via the API with ANTHROPIC_API_KEY (billed per token)."""
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    prompt = brief_prompt(data)
    try:
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-opus-5-5",
            max_tokens=2000,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason == "refusal":
            return None
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text or None
    except anthropic.APIError as exc:
        print(f"AI brief failed: {type(exc).__name__}")
        return None


# ---------- build ----------

def build_data(today: date | None = None, get=requests.get, env=os.environ) -> dict:
    today = today or datetime.now(timezone.utc).date()
    snaps = load_snapshots()
    w = watchlist(today)
    a = avoid_list(today, snaps=snaps)
    c = combo_hits()
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "markets": {
            "uk_delayed": quotes(UK_QUOTES, get),
            "us_reference": quotes(US_REFERENCE, get),
        },
        "signals": {
            "watchlist": w,
            "avoid": a,
            "most_shorted": most_shorted(snaps),
            "combo": c,
        },
        "feed": feed(),
        "uk_names": uk_name_quotes(a, c, get),
        "analyst": analyst_trends([r["ticker"] for r in w if r.get("ticker")], env.get("FINNHUB_API_KEY"), get),
    }
    prev = previous_brief(env.get("PREVIOUS_DATA_URL"), today, get)
    ai = (prev or cli_brief(data, env.get("CLAUDE_CODE_OAUTH_TOKEN"))
          or ai_brief(data, env.get("ANTHROPIC_API_KEY")))
    data["brief"] = {"text": ai or rule_brief(data), "source": "ai" if ai else "rules", "date": today.isoformat()}
    return data


def previous_brief(url: str | None, today: date, get=requests.get) -> str | None:
    """Reuse today's AI brief from the live site so the AI is called once a day, not every rebuild."""
    if not url:
        return None
    try:
        prev = get(url, timeout=15).json().get("brief") or {}
        if prev.get("source") == "ai" and prev.get("date") == today.isoformat():
            return prev.get("text")
    except (requests.RequestException, ValueError, AttributeError):
        pass
    return None


APP_DIR = config.ROOT / "app"


def package_windows_app(out_dir: Path, app_dir: Path = APP_DIR) -> Path | None:
    """Zip the Windows installer (bat files and icon) into the site, so the page can offer
    a real download. A raw .bat link on GitHub only shows the code."""
    files = sorted(p for p in app_dir.glob("*") if p.suffix in (".bat", ".ico")) if app_dir.exists() else []
    if not files:
        return None
    import zipfile
    (out_dir / "app").mkdir(parents=True, exist_ok=True)
    zpath = out_dir / "app" / "hugo-app.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f"Hugo/{f.name}")
        z.writestr("Hugo/README.txt", "Unzip this folder, then double-click install-app.bat.\r\n"
                   "It adds Hugo to the Start Menu and desktop and opens it in its own window.\r\n"
                   "If Windows SmartScreen warns you, click More info, then Run anyway.\r\n"
                   "Undo with app-remove.bat.\r\n")
    return zpath


def main(out_dir: Path = SITE_DIR) -> Path:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(SOURCE_DIR, out_dir)
    package_windows_app(out_dir)
    data = build_data()
    (out_dir / "data.json").write_text(json.dumps(data, default=str, indent=1))
    print(f"dashboard: wrote {out_dir} ({len(data['signals']['watchlist'])} watch, "
          f"{len(data['signals']['avoid'])} avoid, brief={data['brief']['source']})")
    return out_dir
