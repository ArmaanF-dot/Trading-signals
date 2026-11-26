"""Job postings, second pass: more features, more outcomes, and an honest power check.

Builds on edge/jobs/study.py (same Internet Archive history, same no-lookahead rules) and adds:
- features: total change, engineering and sales/go-to-market postings separately (classified from
  job titles), and the rate of new postings (adds) and of postings taken down (removals) between the
  two snapshots, as fractions of the older count;
- outcomes: the earnings-day reaction (EAR), drift over 20, 60, 120 and 250 trading days, and the
  revenue surprise in the quarter being reported, measured as revenue acceleration from SEC XBRL
  (year-on-year growth this quarter minus year-on-year growth the quarter before). There is no free
  consensus revenue or guidance history, so acceleration stands in for 'beat or miss';
- statistics: quarter-by-quarter rank correlation (IC) for every feature and outcome, tercile
  returns net of costs at the longer holds, and the sample needed to detect a realistic effect.
"""
import re

import numpy as np
import pandas as pd

import config
from edge import pead, prices
from edge.form4 import backtest as bt
from edge.form4 import opportunistic as op
from edge.jobs import collect, study
from edge.quality_value import tidy_facts

HORIZONS = (20, 60, 120, 250)
FEATURES = {"d_total": "Total postings, change", "d_eng": "Engineering postings, change",
            "d_sales": "Sales and go-to-market postings, change", "add_rate": "New postings (adds) / older count",
            "remove_rate": "Postings taken down / older count", "net_flow": "Adds minus removals / older count"}
OUTCOMES = {"ear": "Earnings-day reaction (EAR)", "rev_accel": "Revenue acceleration (quarter reported)",
            **{f"excess_{h}d": f"Drift {h}d after report" for h in HORIZONS}}

ENG = re.compile(r"engineer|developer|software|\bsre\b|devops|data scien|machine learning|\bml\b|\bai\b|architect|"
                 r"firmware|hardware|security analyst|infrastructure|platform|technical lead|programmer|scientist", re.I)
SALES = re.compile(r"sales|account executive|account manager|business development|\bsdr\b|\bbdr\b|customer success|"
                   r"partner manager|solutions consultant|solutions engineer|pre-sales|presales|marketing|growth|"
                   r"revenue|channel|demand gen", re.I)
UUID = study.UUID


def classify(title: str) -> str:
    """'sales' (go-to-market, checked first so 'sales engineer' counts as sales), 'eng', 'other' or ''."""
    t = (title or "").strip()
    if not t:
        return ""
    if SALES.search(t):
        return "sales"
    if ENG.search(t):
        return "eng"
    return "other"


def parse_postings(ats: str, token: str, text: str) -> dict[str, str] | None:
    """{posting id: title} from one archived board page or feed ('' where the title is not readable).
    None for pages that do not look like a working board, as in study.count_postings."""
    if study.count_postings(ats, token, text) is None:
        return None
    s = (text or "").lstrip()
    out: dict[str, str] = {}
    if s.startswith("{") or s.startswith("["):
        import json
        js = json.loads(s)
        jobs = js if isinstance(js, list) else js.get("jobs", [])
        for j in jobs:
            if isinstance(j, dict) and j.get("id") is not None:
                out[str(j["id"])] = str(j.get("title") or j.get("text") or "")
        return out or None
    t = re.escape(token)
    if ats == "greenhouse":
        for jid, title in re.findall(rf'href="[^"]*?(?:/{t}/jobs/|gh_jid=|token=)(\d+)[^"]*"[^>]*>\s*([^<]*)<', text, flags=re.I):
            if title.strip() or jid not in out:
                out[jid] = title.strip()
        for jid in re.findall(rf"/{t}/jobs/(\d+)", text, flags=re.I) + re.findall(r"gh_jid=(\d+)", text):
            out.setdefault(jid, "")
    elif ats == "lever":
        for seg in re.split(r'(?=data-qa-posting-id=")', text)[1:]:
            m = re.match(rf'data-qa-posting-id="({UUID})"', seg)
            if m:
                n = re.search(r'data-qa="posting-name"[^>]*>([^<]+)<', seg[:4000])
                out[m.group(1)] = n.group(1).strip() if n else ""
        for jid in re.findall(rf"/{t}/({UUID})", text, flags=re.I):
            out.setdefault(jid, "")
    else:
        for jid in re.findall(rf"/{t}/({UUID})", text, flags=re.I):
            out.setdefault(jid, "")
    return out or None


def snapshot_row(ticker: str, date, postings: dict[str, str]) -> dict:
    kinds = [classify(t) for t in postings.values()]
    return {"ticker": ticker, "date": pd.Timestamp(date), "open": len(postings), "titled": sum(k != "" for k in kinds),
            "eng": kinds.count("eng"), "sales": kinds.count("sales"), "ids": ";".join(sorted(postings))}


def history(board: dict, log=bt.log) -> pd.DataFrame:
    rows = []
    for p in study.PATTERNS[board["ats"]]:
        rows += study.cdx_rows(p.format(t=board["token"]))
    out = []
    for ts, orig in study.pick_monthly(rows):
        url = orig if orig.startswith("http") else "https://" + orig
        r = study.wb_get(study.SNAP_URL.format(ts=ts, url=url))
        try:
            p = parse_postings(board["ats"], board["token"], r.text) if r is not None else None
        except ValueError:
            p = None
        if p:
            out.append(snapshot_row(board["ticker"], ts[:8], p))
    log(f"{board['ticker']}: {len(rows)} captures listed, {len(out)} usable months")
    return pd.DataFrame(out, columns=["ticker", "date", "open", "titled", "eng", "sales", "ids"])


def features_at(hist: pd.DataFrame, e, recent_max: int = config.JOBS_RECENT_MAX_DAYS,
                lookback: int = config.JOBS_LOOKBACK_DAYS, lookback_max: int = config.JOBS_LOOKBACK_MAX_DAYS) -> dict:
    """All features from the latest snapshot before e and one about a quarter older; NaN without data."""
    out = {k: np.nan for k in FEATURES}
    e = pd.Timestamp(e)
    h = hist.sort_values("date")
    recent = h[(h["date"] < e) & (h["date"] >= e - pd.Timedelta(days=recent_max))]
    if recent.empty:
        return out
    r = recent.iloc[-1]
    past = h[(h["date"] <= r["date"] - pd.Timedelta(days=lookback)) & (h["date"] >= r["date"] - pd.Timedelta(days=lookback_max))]
    if past.empty:
        return out
    p = past.iloc[-1]
    out["d_total"] = float(np.log1p(r["open"]) - np.log1p(p["open"]))
    if r["titled"] >= 0.8 * r["open"] and p["titled"] >= 0.8 * p["open"]:
        out["d_eng"] = float(np.log1p(r["eng"]) - np.log1p(p["eng"]))
        out["d_sales"] = float(np.log1p(r["sales"]) - np.log1p(p["sales"]))
    ri, pi = set(str(r["ids"]).split(";")) - {""}, set(str(p["ids"]).split(";")) - {""}
    if pi:
        out["add_rate"] = len(ri - pi) / len(pi)
        out["remove_rate"] = len(pi - ri) / len(pi)
        out["net_flow"] = out["add_rate"] - out["remove_rate"]
    return out


# --- revenue surprise from XBRL ---

def quarterly_revenue(facts: pd.DataFrame) -> pd.Series:
    """Quarterly revenue by period end, from ~3-month XBRL values, with Q4 derived as the fiscal year
    minus the three quarters inside it. Uses the most preferred revenue tag available per period."""
    f = facts[facts["concept"] == "revenue"].dropna(subset=["start", "end"]).copy()
    if f.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    f["days"] = (f["end"] - f["start"]).dt.days
    f = f.sort_values(["prio", "filed"]).drop_duplicates(["start", "end"], keep="first")
    q = f[f["days"].between(80, 100)].set_index("end")["val"]
    q = q[~q.index.duplicated()]
    for y in f[f["days"].between(350, 380)].itertuples(index=False):
        inside = q[(q.index > y.start) & (q.index < y.end - pd.Timedelta(days=20))]
        if len(inside) == 3 and not (abs((q.index - y.end).days) <= 10).any():
            q.loc[y.end] = y.val - inside.sum()
    return q.sort_index()


def rev_accel_at(q: pd.Series, e) -> float:
    """Acceleration of year-on-year revenue growth for the latest quarter ending before date e."""
    e = pd.Timestamp(e)
    if q.empty or not isinstance(q.index, pd.DatetimeIndex):
        return np.nan  # no usable revenue history (e.g. no XBRL revenue tag)
    q = q[q > 0]
    done = q[(q.index < e) & (q.index >= e - pd.Timedelta(days=100))]
    if done.empty:
        return np.nan
    t = done.index[-1]

    def near(d):
        x = q[abs((q.index - d).days) <= 15]
        return float(x.iloc[0]) if len(x) else np.nan

    prev = q[q.index < t - pd.Timedelta(days=60)]
    if prev.empty:
        return np.nan
    t1 = prev.index[-1]
    g0 = float(q[t]) / near(t - pd.Timedelta(days=364)) - 1
    g1 = float(q[t1]) / near(t1 - pd.Timedelta(days=364)) - 1
    return g0 - g1 if np.isfinite(g0) and np.isfinite(g1) else np.nan


# --- statistics ---

def ic_table(ev: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for f in FEATURES:
        for o in OUTCOMES:
            g = ev[ev[f].notna() & ev[o].notna()]
            ic = study.rank_ic_by_quarter(g.assign(signal=g[f]), o)
            rows.append({"feature": f, "outcome": o, "n": len(g), "quarters": len(ic),
                         "ic": float(ic.mean()) if len(ic) else np.nan, "t": study._t(ic)})
    return pd.DataFrame(rows)


def events_needed(ic: float, z: float = 2.8) -> int:
    """Independent events needed to detect a rank correlation `ic` (5% two-sided, 80% power)."""
    return int(np.ceil((z / ic) ** 2))


def mde(n: int, z: float = 2.8) -> float:
    """Smallest rank correlation detectable with n independent events (5% two-sided, 80% power)."""
    return z / np.sqrt(n) if n > 0 else np.nan


def tercile_rows(ev: pd.DataFrame, stress: float) -> list[str]:
    L = ["| tercile | n | " + " | ".join(f"{h}d net of {stress:.1%}" for h in HORIZONS) + " |", "|---|---|" + "---|" * len(HORIZONS)]
    for k, name in ((1, "T1 (cutting)"), (2, "T2"), (3, "T3 (adding)")):
        g = ev[ev["tercile"] == k]
        cells = []
        for h in HORIZONS:
            x = (g[f"excess_{h}d"] - stress).dropna()
            if len(x) < 10:
                cells.append("n/a")
                continue
            t, _ = pead.monthly_t(g[f"excess_{h}d"] - stress, g["filed"].dt.to_period("M"))
            cells.append(f"{op._wmean(x):+.2%} (t {t:.1f})")
        L.append(f"| {name} | {len(g)} | " + " | ".join(cells) + " |")
    return L


def report(ev: pd.DataFrame, cov: pd.DataFrame, ics: pd.DataFrame) -> str:
    stress = config.ROUND_TRIP_COST
    with_sig = ev[ev["d_total"].notna()]
    n = len(with_sig)
    L = ["# Job postings and earnings, second pass", "",
         f"Companies with a public Greenhouse, Lever or Ashby board today: {len(cov)}; with at least 12 archived months "
         f"since {config.JOBS_STUDY_START[:4]}: {int((cov['months'] >= 12).sum())}. Earnings reports with a postings "
         f"change measured before the report: {n} (liquid: {int(with_sig['liquid'].sum())}). Workday-hosted companies "
         "(most non-tech) cannot be rebuilt from the archive: their boards load through a POST request the archive does not keep.", "",
         "Every cell below is a rank correlation (IC) between a feature measured before the report and an outcome, "
         "computed within each calendar quarter and averaged; t is across quarters. Positive means more of the "
         "feature goes with a better outcome. |t| below 2 is noise.", "",
         "| feature | " + " | ".join(OUTCOMES.values()) + " |", "|---|" + "---|" * len(OUTCOMES)]
    for f, fname in FEATURES.items():
        cells = []
        for o in OUTCOMES:
            r = ics[(ics["feature"] == f) & (ics["outcome"] == o)].iloc[0]
            cells.append("n/a" if not np.isfinite(r["ic"]) else f"{r['ic']:+.3f} (t {r['t']:.1f}, n {r['n']})")
        L.append(f"| {fname} | " + " | ".join(cells) + " |")
    sig = ics[(ics["t"].abs() >= 2) & (ics["quarters"] >= 8)]
    n_tests = int(ics["ic"].notna().sum())
    L += ["", f"Cells with |t| >= 2: {len(sig)} of {n_tests}. With this many tests, about {0.05 * n_tests:.0f} would pass by chance alone.", ""]
    L += ["## Total postings change, by tercile, longer holds", "",
          f"Liquid events only; each trade pays {stress:.1%} once (the project's cost rule). Mean excess over SPY "
          "(winsorised 1-99%) and t of monthly averages.", ""]
    L += tercile_rows(ev[ev["liquid"]], stress)
    ears = with_sig["ear"].dropna()
    sd = float(ears.std()) if len(ears) > 2 else np.nan
    L += ["", "## How big a sample would settle it", "",
          f"With {n} events the smallest rank correlation this test can reliably detect is about {mde(n):.2f} "
          "(5% significance, 80% power, treating events as independent; overlapping events make it worse). "
          "Signals that quant funds trade, job postings included, typically have rank correlations of "
          "roughly 0.02 to 0.05 with later returns or surprises (a rule of thumb, not a measured figure for this data). Detecting 0.05 needs about "
          f"{events_needed(0.05):,} events; 0.03 needs about {events_needed(0.03):,}. "
          f"The earnings-day move has a standard deviation of {sd:.1%} here, so a long-short tercile gap of 1% per "
          f"report would need about {int(np.ceil(2 * (2.8 * sd / 0.01) ** 2 * 1.5)):,} events in total." if np.isfinite(sd) else "",
          "", "## Verdict", ""]
    strong = sig[sig["outcome"].isin(["ear", "rev_accel"])]
    if len(sig) <= max(1, 0.05 * n_tests) * 2 and strong.empty:
        v = ("No feature predicts the reaction, the revenue surprise or the drift beyond what chance gives. "
             "The sample is far too small to rule out the small effects quant funds trade, but nothing here is "
             "large enough to trade on our costs.")
    else:
        v = ("Some cells pass |t| >= 2 (listed above). Treat them as leads for the forward test, not an edge: "
             "they were found among many tests on a small, tech-heavy sample.")
    L += [v, "", "Caveats: survivors only (today's boards); job titles classified by keywords; archive captures are "
          "irregular and an HTML capture can miss roles on paginated boards; revenue acceleration is a stand-in for "
          "the consensus surprise, which is not free. Not financial advice."]
    return "\n".join(L)


def main() -> None:
    boards = [b for b in collect.load_boards() if b["ats"] in study.PATTERNS]
    bt.log(f"rebuilding job-board history for {len(boards)} companies")
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as ex:
        hists = dict(zip([b["ticker"] for b in boards], ex.map(history, boards)))
    config.REPORTS_DIR.mkdir(exist_ok=True)
    pd.concat(hists.values(), ignore_index=True).to_csv(config.REPORTS_DIR / "jobs_deep_history.csv.gz", index=False)
    cov = study.coverage_table(hists)
    keep = {t for t, h in hists.items() if len(h) >= 2}
    uni = pead.universe(pead.sec_json(config.SEC_TICKERS_EXCHANGE_URL))
    uni = uni[uni["ticker"].isin(keep)]
    rows, revs = [], {}
    for r in uni.itertuples(index=False):
        try:
            sub = pead.sec_json(config.SEC_SUBMISSIONS_URL.format(cik=r.cik))
            fl = pead.filings(sub, lambda name: pead.sec_json(config.SEC_SUBMISSIONS_FILE_URL.format(name=name)),
                              since=config.JOBS_STUDY_START)
            rows += [{"cik": r.cik, "ticker": r.ticker, "filed": d} for d in pead.earnings_dates(fl, since=config.JOBS_STUDY_START)]
            revs[r.ticker] = quarterly_revenue(tidy_facts(pead.sec_json(config.SEC_COMPANYFACTS_URL.format(cik=r.cik))))
        except Exception as exc:
            bt.log(f"{r.ticker}: {type(exc).__name__}: {exc}")
    events = pd.DataFrame(rows, columns=pead.EVENT_COLS)
    syms = {prices.yahoo_symbol(t, "us") for t in events["ticker"].unique()} | {config.PEAD_BENCHMARK}
    bars = bt.prefetch(syms, prices.fetch_bars)
    ev = pead.evaluate(events, bars, bars[config.PEAD_BENCHMARK]["close"], horizons=HORIZONS)
    feats = pd.DataFrame([features_at(hists[t], f) for t, f in zip(ev["ticker"], ev["filed"])], index=ev.index)
    ev = pd.concat([ev, feats], axis=1)
    ev["rev_accel"] = [rev_accel_at(revs.get(t, pd.Series(dtype=float)), f) for t, f in zip(ev["ticker"], ev["filed"])]
    ev = study.add_terciles(ev.assign(signal=ev["d_total"]))
    ev.to_csv(config.REPORTS_DIR / "jobs_deep_events.csv", index=False)
    text = report(ev, cov, ic_table(ev))
    (config.REPORTS_DIR / "jobs_deep_study.md").write_text(text + "\n")
    print(text)
