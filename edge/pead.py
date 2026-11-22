"""Post-earnings announcement drift (PEAD) on liquid US stocks, from free data.

Earnings dates: every 8-K with Item 2.02 ("Results of Operations") in a company's EDGAR filing
history. Surprise: the earnings announcement return (EAR), the stock's return from the last close
before the 8-K filing date to the first close after it, minus SPY over the same days. That window
catches both pre-market and after-hours releases. (Chan, Jegadeesh and Lakonishok 1996 and Brandt
et al. 2008 show drift after EAR as well as after accounting surprises.)

No lookahead:
- the EAR is known at the close of day +1; entry is PEAD_ENTRY_LAG closes later (default: day +2);
- each event's quintile uses breakpoints from events filed in the previous PEAD_BREAKPOINT_DAYS only;
- liquidity (20-day average dollar volume and price) is measured before the filing date.

The rule was fixed before the run: buy the top EAR quintile, hold PEAD_HORIZONS days, judged out of
sample (PEAD_OOS_START onward). Survivorship: the universe is today's SEC ticker list, so companies
that were delisted or acquired are missing.
"""
import re

import numpy as np
import pandas as pd

import config
from edge import http, prices
from edge.form4 import backtest as bt
from edge.form4 import opportunistic as op

EVENT_COLS = ["cik", "ticker", "filed"]


def sec_json(url: str) -> dict:
    headers = {"User-Agent": config.sec_user_agent(), "Accept-Encoding": "gzip, deflate"}
    return http.get(url, headers=headers, min_interval=config.SEC_MIN_INTERVAL).json()


# --- universe and earnings dates ---

def universe(tickers_json: dict) -> pd.DataFrame:
    """One (cik, ticker) per company listed on NYSE or Nasdaq, plain share classes only.
    SEC lists a company's tickers in order, the main listing first."""
    df = pd.DataFrame(tickers_json["data"], columns=tickers_json["fields"])
    df = df[df["exchange"].isin(["NYSE", "Nasdaq"]) & df["ticker"].astype(str).str.fullmatch(r"[A-Z]{1,5}(-[A-Z])?")]
    df = df.drop_duplicates("cik", keep="first")
    return pd.DataFrame({"cik": df["cik"].astype(int).map(lambda c: f"{c:010d}"), "ticker": df["ticker"]}).reset_index(drop=True)


def _filings_table(block: dict) -> pd.DataFrame:
    n = len(block.get("form", []))
    items = block.get("items") or [""] * n
    return pd.DataFrame({"form": block.get("form", []), "filed": block.get("filingDate", []), "items": items})


def filings(sub: dict, fetch_more=None, since: str = config.PEAD_START) -> pd.DataFrame:
    """All filings in a submissions JSON, following the older-filings files when the recent block
    does not reach back to `since`."""
    recent = _filings_table(sub.get("filings", {}).get("recent", {}))
    frames = [recent]
    if fetch_more is not None:
        for f in sub.get("filings", {}).get("files", []):
            if f.get("filingTo", "9999") >= since:
                frames.append(_filings_table(fetch_more(f["name"])))
    out = pd.concat(frames, ignore_index=True)
    out["filed"] = pd.to_datetime(out["filed"], errors="coerce")
    return out.dropna(subset=["filed"])


def earnings_dates(fl: pd.DataFrame, since: str = config.PEAD_START, gap_days: int = config.PEAD_MIN_GAP_DAYS) -> list[pd.Timestamp]:
    """Filing dates of 8-Ks with Item 2.02, at most one per gap_days (the first; later ones in
    the window are usually corrections or pre-announcement follow-ups)."""
    is_202 = fl["items"].fillna("").astype(str).map(lambda s: "2.02" in re.split(r"[,\s]+", s))
    d = sorted(set(fl.loc[(fl["form"] == "8-K") & is_202 & (fl["filed"] >= pd.Timestamp(since)), "filed"]))
    out: list[pd.Timestamp] = []
    for x in d:
        if not out or (x - out[-1]).days >= gap_days:
            out.append(x)
    return out


# --- per-event measures ---

def _empty_measures(horizons) -> dict:
    out = {"ear": np.nan, "entry_date": "", "adv": np.nan, "price": np.nan}
    for h in horizons:
        out[f"gross_{h}d"] = np.nan
        out[f"bench_{h}d"] = np.nan
    return out


def measures(bars: pd.DataFrame, bench: pd.Series, filed, horizons=config.PEAD_HORIZONS,
             lag: int = config.PEAD_ENTRY_LAG) -> dict:
    """EAR (close before filing day to first close after it, minus SPY), liquidity before the
    filing day, and forward returns of the stock and SPY from entry (lag closes after day +1)."""
    out = _empty_measures(horizons)
    if bars.empty or bench.empty:
        return out
    t = pd.Timestamp(filed)
    before, after = bars[bars.index < t], bars[bars.index > t]
    if len(before) < config.MIN_BARS_BEFORE or after.empty:
        return out
    if (t - before.index[-1]).days > config.MAX_ENTRY_GAP_DAYS or (after.index[0] - t).days > config.MAX_ENTRY_GAP_DAYS:
        return out  # price history does not cover the announcement (e.g. recycled ticker)
    d_prev, d1 = before.index[-1], after.index[0]
    b_prev, b1 = bench.asof(d_prev), bench.asof(d1)
    if not (pd.notna(b_prev) and pd.notna(b1)):
        return out
    out["ear"] = float(after["close"].iloc[0] / before["close"].iloc[-1] - 1) - float(b1 / b_prev - 1)
    tail = before.tail(20)
    vol = tail["volume"].where(tail["volume"] > 0)
    if vol.notna().sum() >= 10:
        out["adv"] = float((tail["close"] * vol).mean())
    out["price"] = float(before["close"].iloc[-1])
    if len(after) <= lag:
        return out
    entry = after.index[lag]
    out["entry_date"] = entry.strftime("%Y-%m-%d")
    p0, q0 = float(after["close"].iloc[lag]), bench.asof(entry)
    for h in horizons:
        if len(after) > lag + h:
            out[f"gross_{h}d"] = float(after["close"].iloc[lag + h]) / p0 - 1
            qh = bench.asof(after.index[lag + h])
            if pd.notna(q0) and pd.notna(qh):
                out[f"bench_{h}d"] = float(qh) / float(q0) - 1
    return out


def evaluate(events: pd.DataFrame, bars: dict, bench: pd.Series, horizons=config.PEAD_HORIZONS) -> pd.DataFrame:
    rows = []
    empty = pd.DataFrame(columns=["close", "volume"], dtype=float)
    for e in events.itertuples(index=False):
        m = measures(bars.get(prices.yahoo_symbol(e.ticker, "us"), empty), bench, e.filed, horizons)
        rows.append({"cik": e.cik, "ticker": e.ticker, "filed": pd.Timestamp(e.filed), **m})
    ev = pd.DataFrame(rows)
    if ev.empty:
        return ev
    ev["liquid"] = (ev["adv"] >= config.PEAD_MIN_ADV) & (ev["price"] >= config.PEAD_MIN_PRICE)
    ev["cost"] = ev["adv"].map(op.round_trip_cost)
    for h in horizons:
        ev[f"excess_{h}d"] = ev[f"gross_{h}d"] - ev[f"bench_{h}d"]
    return ev


def add_quintiles(ev: pd.DataFrame, days: int = config.PEAD_BREAKPOINT_DAYS, min_n: int = config.PEAD_MIN_BREAKPOINT_EVENTS) -> pd.DataFrame:
    """Quintile 1 (worst reaction) to 5 (best) from EAR breakpoints of events filed in the previous
    `days` calendar days (strictly before the event's filing date). Liquid events with an EAR only."""
    ev = ev.copy()
    ev["quintile"] = np.nan
    ok = ev["liquid"] & ev["ear"].notna()
    base = ev[ok].sort_values("filed")
    dates, ears = base["filed"].values, base["ear"].values
    cuts = {}
    for d in np.unique(dates):
        lo, hi = np.searchsorted(dates, d - np.timedelta64(days, "D")), np.searchsorted(dates, d)
        if hi - lo >= min_n:
            cuts[d] = np.quantile(ears[lo:hi], [0.2, 0.4, 0.6, 0.8])
    for i in base.index:
        c = cuts.get(np.datetime64(ev.at[i, "filed"]))
        if c is not None:
            ev.at[i, "quintile"] = 1 + int(np.searchsorted(c, ev.at[i, "ear"], side="right"))
    return ev


# --- statistics and report ---

def monthly_t(values: pd.Series, months: pd.Series) -> tuple[float, int]:
    """t-statistic of the mean of monthly averages (events in the same month are not independent)."""
    m = pd.Series(values.values, index=months.values).dropna().groupby(level=0).mean()
    if len(m) < 3 or m.std(ddof=1) == 0:
        return float("nan"), len(m)
    return float(m.mean() / (m.std(ddof=1) / np.sqrt(len(m)))), len(m)


def _cell(g: pd.DataFrame, col: str, cost=0.0) -> str:
    x = (g[col] - cost).dropna()
    if len(x) < 10:
        return "n/a"
    t, _ = monthly_t(g[col] - cost, pd.to_datetime(g["entry_date"]).dt.to_period("M"))
    return f"{op._wmean(x):+.2%} (t {t:.1f})"


def spread_series(g: pd.DataFrame, col: str) -> pd.Series:
    """Monthly top-minus-bottom quintile excess return."""
    g = g.assign(month=pd.to_datetime(g["entry_date"]).dt.to_period("M"))
    top = g[g["quintile"] == 5].groupby("month")[col].mean()
    bot = g[g["quintile"] == 1].groupby("month")[col].mean()
    return (top - bot).dropna()


def period_stats(g: pd.DataFrame, h: int, stress: float = config.ROUND_TRIP_COST) -> dict:
    """Numbers the verdict uses for one period and horizon."""
    col = f"excess_{h}d"
    q5 = g[(g["quintile"] == 5) & g[col].notna()]
    months = pd.to_datetime(q5["entry_date"]).dt.to_period("M")
    ls = spread_series(g, col)
    t_ls = float(ls.mean() / (ls.std(ddof=1) / np.sqrt(len(ls)))) if len(ls) > 2 and ls.std(ddof=1) > 0 else float("nan")
    return {"n_q5": len(q5), "q5_gross": op._wmean(q5[col]) if len(q5) else float("nan"),
            "q5_net": op._wmean(q5[col] - q5["cost"]) if len(q5) else float("nan"),
            "q5_net_t": monthly_t(q5[col] - q5["cost"], months)[0],
            "q5_stress": op._wmean(q5[col] - stress) if len(q5) else float("nan"),
            "ls": float(ls.mean()) if len(ls) else float("nan"), "ls_t": t_ls}


def verdict(oos: dict) -> str:
    if oos["n_q5"] < 100:
        return "Too few out-of-sample events to judge."
    if oos["q5_net"] > 0 and oos["q5_net_t"] >= 2:
        return "Edge: the top quintile beat SPY out of sample after realistic costs, with t >= 2."
    if oos["q5_gross"] > 0 and oos["ls"] > 0:
        return "Drift is there before costs but too small to trade after them: no tradeable edge."
    return "No edge: the top quintile did not beat SPY out of sample."


def report(ev: pd.DataFrame, n_companies: int, horizons=config.PEAD_HORIZONS) -> str:
    q = ev[ev["quintile"].notna()]
    oos_start = pd.Timestamp(config.PEAD_OOS_START)
    periods = {f"In sample ({config.PEAD_START[:4]} to {oos_start.year - 1})": q[q["filed"] < oos_start],
               f"Out of sample ({oos_start.year} onward)": q[q["filed"] >= oos_start]}
    stress = config.ROUND_TRIP_COST
    L = ["# Post-earnings announcement drift (US, liquid stocks)", "",
         f"Companies: {n_companies} (NYSE/Nasdaq, today's SEC list). Earnings 8-Ks (Item 2.02): {len(ev)}; "
         f"priced with a reaction: {int(ev['ear'].notna().sum())}; liquid (20-day ADV >= ${config.PEAD_MIN_ADV / 1e6:g}m, "
         f"price >= ${config.PEAD_MIN_PRICE:g}) and ranked: {len(q)}.", "",
         f"Surprise = earnings announcement return (close before the filing day to the first close after, minus SPY). "
         f"Entry {config.PEAD_ENTRY_LAG} close(s) after that, so no lookahead. Quintile breakpoints come from the previous "
         f"{config.PEAD_BREAKPOINT_DAYS} days of announcements. Cells: mean excess return over SPY (winsorised 1-99%) "
         "and t-statistic of monthly averages. Realistic cost uses the liquidity tiers in config.py "
         f"(0.4% round trip for these names); stress cost is the project's {stress:.1%} rule.", ""]
    stats = {}
    for name, g in periods.items():
        L += [f"## {name}: {len(g)} events", "",
              "| quintile | n | " + " | ".join(f"{h}d excess" for h in horizons) + " |", "|---|---|" + "---|" * len(horizons)]
        for k in range(1, 6):
            gk = g[g["quintile"] == k]
            L.append(f"| Q{k}{' (worst reaction)' if k == 1 else ' (best reaction)' if k == 5 else ''} | {len(gk)} | "
                     + " | ".join(_cell(gk, f"excess_{h}d") for h in horizons) + " |")
        L.append("")
        L += ["| rule | " + " | ".join(f"{h}d" for h in horizons) + " |", "|---|" + "---|" * len(horizons)]
        ps = {h: period_stats(g, h, stress) for h in horizons}
        stats[name] = ps
        L.append("| Q5 long, net of realistic cost | " + " | ".join(f"{ps[h]['q5_net']:+.2%} (t {ps[h]['q5_net_t']:.1f})" for h in horizons) + " |")
        L.append(f"| Q5 long, net of {stress:.1%} | " + " | ".join(f"{ps[h]['q5_stress']:+.2%}" for h in horizons) + " |")
        L.append("| Q5 minus Q1, before costs (monthly) | " + " | ".join(f"{ps[h]['ls']:+.2%} (t {ps[h]['ls_t']:.1f})" for h in horizons) + " |")
        L.append("")
    oos = list(stats.values())[-1][max(horizons)]
    L += ["## Verdict", "", f"Pre-set rule: buy the top quintile, hold {max(horizons)} days, judged out of sample. "
          + verdict(oos), "",
          "Caveats: survivorship (delisted and acquired companies are missing, which flatters long returns); "
          "Item 2.02 also covers some pre-announcements and restatements; the long-short line ignores borrow costs "
          "and needs two round trips; trades overlap in time, which the monthly t-statistic only partly allows for. "
          "Not financial advice."]
    return "\n".join(L)


def main() -> None:
    uni = universe(sec_json(config.SEC_TICKERS_EXCHANGE_URL))
    bt.log(f"universe: {len(uni)} NYSE/Nasdaq companies")
    min_adv = config.PEAD_MIN_ADV

    def fetch_liquid(sym: str) -> pd.DataFrame:
        b = prices.fetch_bars(sym)
        if b.empty:
            return b
        adv = (b["close"] * b["volume"]).rolling(20).mean()
        return b if adv.max() >= min_adv else b.iloc[0:0]  # never liquid enough: drop to save memory

    syms = {prices.yahoo_symbol(t, "us") for t in uni["ticker"]} | {config.PEAD_BENCHMARK}
    bars = bt.prefetch(syms, fetch_liquid)
    bench = bars[config.PEAD_BENCHMARK]["close"]
    keep = uni[uni["ticker"].map(lambda t: not bars.get(prices.yahoo_symbol(t, "us"), pd.DataFrame()).empty)]
    bt.log(f"{len(keep)} companies were ever liquid enough; reading their EDGAR filing histories")
    rows = []
    for i, r in enumerate(keep.itertuples(index=False), 1):
        try:
            sub = sec_json(config.SEC_SUBMISSIONS_URL.format(cik=r.cik))
            fl = filings(sub, lambda name: sec_json(config.SEC_SUBMISSIONS_FILE_URL.format(name=name)))
            rows += [{"cik": r.cik, "ticker": r.ticker, "filed": d} for d in earnings_dates(fl)]
        except Exception as exc:  # one company's failure must not stop the study
            bt.log(f"{r.ticker}: {type(exc).__name__}: {exc}")
        if i % 200 == 0:
            bt.log(f"filings {i}/{len(keep)}; {len(rows)} earnings dates so far")
    events = pd.DataFrame(rows, columns=EVENT_COLS)
    ev = add_quintiles(evaluate(events, bars, bench))
    config.REPORTS_DIR.mkdir(exist_ok=True)
    ev.to_csv(config.REPORTS_DIR / "pead_events.csv.gz", index=False)
    text = report(ev, len(keep))
    (config.REPORTS_DIR / "pead_study.md").write_text(text + "\n")
    print(text)
