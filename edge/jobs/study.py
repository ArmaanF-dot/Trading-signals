"""Do job postings predict earnings? A backtest from Internet Archive snapshots of job boards.

History: the Wayback Machine's CDX index lists every archived copy of a company's job board
(Greenhouse, Lever, Ashby pages and their JSON feeds). For each company we take at most one copy
per month, count the distinct posting ids in it, and so rebuild a monthly series of open roles.

Signal, fixed before the run: at each earnings date E (8-K Item 2.02 filing date from EDGAR, as in
edge/pead.py), the change in log(1 + open postings) between the latest snapshot in
[E - JOBS_RECENT_MAX_DAYS, E - 1] and the latest snapshot at least JOBS_LOOKBACK_DAYS before that.
Events are put into terciles using breakpoints from events in the previous JOBS_BREAKPOINT_DAYS,
so no event's rank depends on later data.

Outcomes:
- the earnings announcement return (EAR): close before the filing day to the first close after it,
  minus SPY. Trading it means buying at the close before the report, one round trip per event;
- drift after the report: excess return over SPY for PEAD_HORIZONS days, entered as in edge/pead.py.

Caveats are in the report: the universe is companies whose boards exist on these ATSs today
(survivors, tech-heavy), and archive coverage is patchy.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

import config
from edge import pead, prices
from edge.form4 import backtest as bt
from edge.form4 import opportunistic as op
from edge.jobs import collect

CDX_URL = "https://web.archive.org/cdx/search/cdx"
SNAP_URL = "https://web.archive.org/web/{ts}id_/{url}"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

# archived URL patterns per ATS; {t} is the board token
PATTERNS = {
    "greenhouse": ["boards.greenhouse.io/{t}", "job-boards.greenhouse.io/{t}", "boards.greenhouse.io/embed/job_board?for={t}",
                   "boards-api.greenhouse.io/v1/boards/{t}/jobs", "api.greenhouse.io/v1/boards/{t}/jobs"],
    "lever": ["jobs.lever.co/{t}", "api.lever.co/v0/postings/{t}"],
    "ashby": ["jobs.ashbyhq.com/{t}", "api.ashbyhq.com/posting-api/job-board/{t}"],
}

_session = requests.Session()
_session.headers["User-Agent"] = config.JOBS_USER_AGENT


def wb_get(url: str, params=None, tries: int = 4) -> requests.Response | None:
    """Polite GET to the Wayback Machine; None after repeated failure."""
    delay = 5.0
    for _ in range(tries):
        time.sleep(config.JOBS_WAYBACK_INTERVAL)
        try:
            r = _session.get(url, params=params, timeout=90)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(delay)
        delay *= 2
    return None


# --- counting postings in an archived page ---

def count_postings(ats: str, token: str, text: str) -> int | None:
    """Distinct open postings in one archived board page or feed. None when the page does not look
    like a working board (error pages, redirects, empty shells): zero is treated as missing, since
    a listed company with no openings at all is far rarer than a broken capture."""
    text = text or ""
    s = text.lstrip()
    if s.startswith("{") or s.startswith("["):
        try:
            js = json.loads(s)
        except ValueError:
            return None
        if isinstance(js, list):
            n = len({str(j.get("id")) for j in js if isinstance(j, dict)})
        elif isinstance(js, dict) and isinstance(js.get("jobs"), list):
            n = len({str(j.get("id")) for j in js["jobs"] if isinstance(j, dict)})
        else:
            return None
        return n or None
    t = re.escape(token)
    if ats == "greenhouse":
        ids = set(re.findall(rf"/{t}/jobs/(\d+)", text, flags=re.I)) | set(re.findall(r"gh_jid=(\d+)", text)) \
            | set(re.findall(rf"job_app\?for={t}&(?:amp;)?token=(\d+)", text, flags=re.I))
    elif ats == "lever":
        ids = set(re.findall(rf'data-qa-posting-id="({UUID})"', text)) | set(re.findall(rf"/{t}/({UUID})", text, flags=re.I))
    elif ats == "ashby":
        ids = set(re.findall(rf"/{t}/({UUID})", text, flags=re.I)) | set(re.findall(rf'"jobPostingId"\s*:\s*"({UUID})"', text))
    else:
        return None
    return len(ids) or None


# --- rebuilding a company's history ---

def cdx_rows(url: str, since: str = config.JOBS_STUDY_START) -> list[tuple[str, str]]:
    """(timestamp, original url) of 200-status captures, at most one per month."""
    r = wb_get(CDX_URL, {"url": url, "output": "json", "filter": "statuscode:200", "collapse": "timestamp:6",
                         "fl": "timestamp,original", "from": since[:4]})
    if r is None:
        return []
    try:
        rows = r.json()[1:]
    except ValueError:
        return []
    return [(a, b) for a, b in rows]


def pick_monthly(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """One capture per calendar month across all URL patterns (feeds preferred: they are complete,
    while HTML boards can be paginated or rendered by script)."""
    best: dict[str, tuple[int, str, str]] = {}
    for ts, orig in rows:
        m = ts[:6]
        rank = 0 if ("api." in orig or "boards-api." in orig) else 1
        if m not in best or rank < best[m][0]:
            best[m] = (rank, ts, orig)
    return [(ts, orig) for _, ts, orig in (best[m] for m in sorted(best))]


def history(board: dict, log=bt.log) -> pd.DataFrame:
    rows = []
    for p in PATTERNS[board["ats"]]:
        rows += cdx_rows(p.format(t=board["token"]))
    out = []
    for ts, orig in pick_monthly(rows):
        url = orig if orig.startswith("http") else "https://" + orig
        r = wb_get(SNAP_URL.format(ts=ts, url=url))
        n = count_postings(board["ats"], board["token"], r.text) if r is not None else None
        if n is not None:
            out.append({"ticker": board["ticker"], "date": pd.Timestamp(ts[:8]), "open": n, "source": orig})
    log(f"{board['ticker']}: {len(rows)} captures listed, {len(out)} usable months")
    return pd.DataFrame(out, columns=["ticker", "date", "open", "source"])


# --- the signal at each earnings date ---

def signal_at(hist: pd.DataFrame, e, recent_max: int = config.JOBS_RECENT_MAX_DAYS,
              lookback: int = config.JOBS_LOOKBACK_DAYS, lookback_max: int = config.JOBS_LOOKBACK_MAX_DAYS) -> dict:
    """Change in log(1 + postings) up to the day before earnings date e, or NaN without fresh data."""
    e = pd.Timestamp(e)
    h = hist.sort_values("date")
    recent = h[(h["date"] < e) & (h["date"] >= e - pd.Timedelta(days=recent_max))]
    if recent.empty:
        return {"jobs_now": np.nan, "jobs_then": np.nan, "signal": np.nan}
    r = recent.iloc[-1]
    past = h[(h["date"] <= r["date"] - pd.Timedelta(days=lookback)) & (h["date"] >= r["date"] - pd.Timedelta(days=lookback_max))]
    if past.empty:
        return {"jobs_now": float(r["open"]), "jobs_then": np.nan, "signal": np.nan}
    p = past.iloc[-1]
    return {"jobs_now": float(r["open"]), "jobs_then": float(p["open"]),
            "signal": float(np.log1p(r["open"]) - np.log1p(p["open"]))}


def add_terciles(ev: pd.DataFrame, days: int = config.JOBS_BREAKPOINT_DAYS, min_n: int = config.JOBS_MIN_BREAKPOINT_EVENTS) -> pd.DataFrame:
    """Tercile 1 (cutting postings hardest) to 3 (adding fastest), from breakpoints of events in the
    previous `days` days only."""
    ev = ev.copy()
    ev["tercile"] = np.nan
    ok = ev["signal"].notna() & (ev["liquid"].fillna(False).astype(bool) if "liquid" in ev else True)
    base = ev[ok].sort_values("filed")
    dates, sig = base["filed"].values, base["signal"].values
    for i, d in zip(base.index, dates):
        lo, hi = np.searchsorted(dates, d - np.timedelta64(days, "D")), np.searchsorted(dates, d)
        if hi - lo >= min_n:
            c = np.quantile(sig[lo:hi], [1 / 3, 2 / 3])
            ev.at[i, "tercile"] = 1 + int(np.searchsorted(c, ev.at[i, "signal"], side="right"))
    return ev


def rank_ic_by_quarter(ev: pd.DataFrame, col: str) -> pd.Series:
    """Spearman correlation of signal and outcome within each calendar quarter (>= 8 events)."""
    g = ev[ev["signal"].notna() & ev[col].notna()].assign(q=lambda d: d["filed"].dt.to_period("Q"))
    out = {}
    for q, x in g.groupby("q"):
        if len(x) >= 8:
            out[q] = x["signal"].rank().corr(x[col].rank())
    return pd.Series(out, dtype=float)


def _t(s: pd.Series) -> float:
    s = s.dropna()
    return float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))) if len(s) > 2 and s.std(ddof=1) > 0 else float("nan")


# --- report ---

def coverage_table(hists: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for t, h in hists.items():
        rows.append({"ticker": t, "months": len(h), "first": h["date"].min().strftime("%Y-%m") if len(h) else "",
                     "last": h["date"].max().strftime("%Y-%m") if len(h) else ""})
    return pd.DataFrame(rows)


def report(ev: pd.DataFrame, cov: pd.DataFrame, horizons=config.PEAD_HORIZONS) -> str:
    stress = config.ROUND_TRIP_COST
    sig = ev[ev["signal"].notna()]
    ranked = ev[ev["tercile"].notna()]
    usable = cov[cov["months"] >= 12]
    L = ["# Job postings and earnings (US, liquid stocks)", "",
         f"Companies with a public Greenhouse, Lever or Ashby board today: {len(cov)}. "
         f"With at least 12 archived months since {config.JOBS_STUDY_START[:4]}: {len(usable)}. "
         f"Median archived months per company: {cov['months'].median():.0f}.", "",
         f"Earnings dates (8-K Item 2.02): {len(ev)}; with a fresh postings change before the report: {len(sig)}; "
         f"ranked into terciles: {len(ranked)}.", "",
         f"Signal: change in log(1 + open postings) from a snapshot at least {config.JOBS_LOOKBACK_DAYS} days old to the "
         f"latest snapshot within {config.JOBS_RECENT_MAX_DAYS} days before the report. Terciles use breakpoints from "
         f"the previous {config.JOBS_BREAKPOINT_DAYS} days of events. EAR is the stock's move over the report "
         "(close before the filing day to first close after) minus SPY. Cells: mean (winsorised 1-99%) and t-statistic "
         "of monthly averages.", ""]
    if len(ranked) < 30:
        L += ["## Verdict", "", "Too few events with archived postings to test anything. The archive does not hold "
              "enough job-board history for these companies; the daily collector (python run.py jobs) builds it forward."]
        return "\n".join(L)
    cols = ["ear"] + [f"excess_{h}d" for h in horizons]
    L += ["## By tercile", "", "| tercile | n | median change | EAR | " + " | ".join(f"{h}d drift" for h in horizons) + " |",
          "|---|---|---|---|" + "---|" * len(horizons)]
    for k in (1, 2, 3):
        g = ranked[ranked["tercile"] == k]
        name = {1: "T1 (cutting)", 2: "T2", 3: "T3 (adding)"}[k]
        cells = []
        for c in cols:
            x = g[c].dropna()
            if len(x) < 10:
                cells.append("n/a")
                continue
            t, _ = pead.monthly_t(g[c], g["filed"].dt.to_period("M"))
            cells.append(f"{op._wmean(x):+.2%} (t {t:.1f})")
        L.append(f"| {name} | {len(g)} | {np.expm1(g['signal'].median()):+.0%} | " + " | ".join(cells) + " |")
    L.append("")
    ic = rank_ic_by_quarter(sig, "ear")
    L += [f"Rank correlation of signal with EAR, quarter by quarter: mean {ic.mean():+.3f} over {len(ic)} quarters (t {_t(ic):.1f}).", ""]
    t3, t1 = ranked[ranked["tercile"] == 3], ranked[ranked["tercile"] == 1]
    m = lambda g: g.assign(month=g["filed"].dt.to_period("M"))
    spread = (m(t3).groupby("month")["ear"].mean() - m(t1).groupby("month")["ear"].mean()).dropna()
    t3_net = (t3["ear"] - t3["cost"]).dropna()
    L += ["## Trading it", "",
          "| rule | mean per event | t |", "|---|---|---|",
          f"| Long T3 over the report, net of realistic cost | {op._wmean(t3_net):+.2%} | {pead.monthly_t(t3['ear'] - t3['cost'], t3['filed'].dt.to_period('M'))[0]:.1f} |",
          f"| Long T3 over the report, net of {stress:.1%} | {op._wmean((t3['ear'] - stress).dropna()):+.2%} | |",
          f"| T3 minus T1 over the report, before costs (monthly) | {spread.mean():+.2%} | {_t(spread):.1f} |", ""]
    ok = len(t3_net) >= 100 and op._wmean(t3_net) > 0 and pead.monthly_t(t3["ear"] - t3["cost"], t3["filed"].dt.to_period("M"))[0] >= 2
    if ok:
        v = "Possible edge: companies adding postings fastest beat SPY over their reports after realistic costs, with t >= 2. Needs forward confirmation."
    elif len(t3_net) < 100:
        v = "Too few events for a reliable answer; read the numbers as indicative only. No tradeable edge shown."
    elif spread.mean() > 0 and ic.mean() > 0:
        v = "The sign is right (more hiring, better reaction) but too weak to trade after costs: no tradeable edge."
    else:
        v = "No edge: postings growth did not predict the reaction to earnings."
    L += ["## Verdict", "", "Pre-set rule: buy the top tercile at the close before the report, sell after it. " + v, "",
          "Caveats: the universe is today's boards (survivors, mostly tech and fintech, many listed only since 2020); "
          "archive captures are irregular, so 'recent' can be up to "
          f"{config.JOBS_RECENT_MAX_DAYS} days stale; an HTML capture can miss roles on paginated boards; "
          "companies move between ATSs, which shows up as missing months. Not financial advice."]
    return "\n".join(L)


def main() -> None:
    boards = collect.load_boards()
    bt.log(f"rebuilding job-board history for {len(boards)} companies from the Internet Archive")
    with ThreadPoolExecutor(max_workers=2) as ex:
        hists = dict(zip([b["ticker"] for b in boards], ex.map(history, boards)))
    allh = pd.concat(hists.values(), ignore_index=True)
    config.REPORTS_DIR.mkdir(exist_ok=True)
    allh.to_csv(config.REPORTS_DIR / "jobs_history.csv", index=False)
    cov = coverage_table(hists)

    uni = pead.universe(pead.sec_json(config.SEC_TICKERS_EXCHANGE_URL))
    uni = uni[uni["ticker"].isin(hists)]
    rows = []
    for r in uni.itertuples(index=False):
        try:
            sub = pead.sec_json(config.SEC_SUBMISSIONS_URL.format(cik=r.cik))
            fl = pead.filings(sub, lambda name: pead.sec_json(config.SEC_SUBMISSIONS_FILE_URL.format(name=name)),
                              since=config.JOBS_STUDY_START)
            rows += [{"cik": r.cik, "ticker": r.ticker, "filed": d} for d in pead.earnings_dates(fl, since=config.JOBS_STUDY_START)]
        except Exception as exc:
            bt.log(f"{r.ticker}: {type(exc).__name__}: {exc}")
    events = pd.DataFrame(rows, columns=pead.EVENT_COLS)
    syms = {prices.yahoo_symbol(t, "us") for t in events["ticker"].unique()} | {config.PEAD_BENCHMARK}
    bars = bt.prefetch(syms, prices.fetch_bars)
    ev = pead.evaluate(events, bars, bars[config.PEAD_BENCHMARK]["close"])
    sigs = pd.DataFrame([signal_at(hists[t], f) for t, f in zip(ev["ticker"], ev["filed"])], index=ev.index)
    ev = add_terciles(pd.concat([ev, sigs], axis=1))
    ev.to_csv(config.REPORTS_DIR / "jobs_events.csv", index=False)
    text = report(ev, cov)
    (config.REPORTS_DIR / "jobs_study.md").write_text(text + "\n")
    print(text)
