"""Risk-adjusted record for every study and live signal: Sharpe ratio, volatility, max drawdown and
a conservative leverage-sizing line.

Two return streams per strategy:
  - net: what the book itself earned after costs (a long-only book's Sharpe is mostly the market's);
  - edge: net excess over the benchmark, i.e. a market-hedged book. Only this says whether the signal adds anything.

Event studies are turned into a monthly series by averaging the net 20-day trade return of every signal entered
that month (months with no signal earn 0, sitting in cash). With 20-day holds the cohorts barely overlap, so the
series behaves like a monthly-rebalanced book and is annualised with sqrt(12).

Leverage rule (deliberately conservative): suggest leverage only when the out-of-sample edge Sharpe net of costs is
at least LEVER_MIN_SHARPE over at least LEVER_MIN_MONTHS months. Then size to LEVER_TARGET_VOL, capped by half-Kelly
and by LEVER_CAP, rounded down to a quarter. Otherwise the line says no leverage. Not financial advice.
"""
import json
import math

import numpy as np
import pandas as pd

import config

LEVER_MIN_SHARPE = 1.0     # out-of-sample edge Sharpe net of costs needed before any leverage is suggested
LEVER_MIN_MONTHS = 36      # fewer months than this cannot establish a Sharpe of 1 (its standard error is ~1/sqrt(years))
LEVER_TARGET_VOL = 0.10    # annual volatility the sized book aims for
LEVER_CAP = 2.0            # never suggest more than this, whatever the numbers say
RISK_MD = config.REPORTS_DIR / "risk_summary.md"
RISK_JSON = config.REPORTS_DIR / "risk_summary.json"


def series_stats(r: pd.Series, periods: int = 12) -> dict:
    """Annualised return (geometric), volatility, Sharpe (rf = 0), t-stat of the mean and max drawdown."""
    r = pd.to_numeric(r, errors="coerce").dropna()
    nan = float("nan")
    if len(r) < 2:
        return {"n": len(r), "ann": nan, "vol": nan, "sharpe": nan, "t": nan, "maxdd": nan}
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    curve = (1 + r).cumprod()
    growth = float(curve.iloc[-1])
    return {"n": len(r), "ann": growth ** (periods / len(r)) - 1 if growth > 0 else -1.0, "vol": sd * math.sqrt(periods),
            "sharpe": mu / sd * math.sqrt(periods) if sd > 0 else nan, "t": mu / sd * math.sqrt(len(r)) if sd > 0 else nan,
            "maxdd": float(min((curve / curve.cummax() - 1).min(), 0.0))}


def daily_to_monthly(r: pd.Series) -> pd.Series:
    """Compound daily returns (DatetimeIndex) into calendar-month returns."""
    r = pd.to_numeric(r, errors="coerce").dropna()
    return (1 + r).groupby(r.index.to_period("M")).prod() - 1


def cohort_series(dates, returns, clip: bool = True) -> pd.Series:
    """Monthly series from per-trade returns: mean return of trades entered each month, 0 in empty months.
    Trades are clipped to the 1st-99th percentile first (same as the study tables), so data glitches cannot drive it."""
    d = pd.to_datetime(pd.Series(dates).reset_index(drop=True), errors="coerce")
    x = pd.to_numeric(pd.Series(returns).reset_index(drop=True), errors="coerce")
    ok = d.notna() & x.notna()
    d, x = d[ok], x[ok]
    if x.empty:
        return pd.Series(dtype=float)
    if clip and len(x) >= 20:
        x = x.clip(x.quantile(0.01), x.quantile(0.99))
    m = x.groupby(d.dt.to_period("M")).mean()
    full = pd.period_range(m.index.min(), m.index.max(), freq="M")
    return m.reindex(full, fill_value=0.0)


def sizing(edge: dict) -> dict:
    """Leverage suggestion from the out-of-sample edge (market-hedged, net of costs) stats."""
    s, vol, n = edge.get("sharpe"), edge.get("vol"), edge.get("n", 0)
    if n < LEVER_MIN_MONTHS:
        return {"leverage": 0.0, "text": f"None: {n} months is too short a record to size from (need {LEVER_MIN_MONTHS})."}
    if s is None or not np.isfinite(s) or s < LEVER_MIN_SHARPE:
        shown = f"{s:.2f}" if s is not None and np.isfinite(s) else "n/a"
        return {"leverage": 0.0, "text": f"None: out-of-sample edge Sharpe {shown} net of costs is below "
                                         f"{LEVER_MIN_SHARPE:.1f}. No edge to size up; leverage would only magnify costs and drawdowns."}
    mu = s * vol  # annual mean excess
    half_kelly = 0.5 * mu / vol ** 2 if vol > 0 else 0.0
    raw = min(LEVER_CAP, LEVER_TARGET_VOL / vol if vol > 0 else 0.0, half_kelly)
    lev = math.floor(raw * 4) / 4
    return {"leverage": lev, "text": f"Up to {lev:.2f}x (targets {LEVER_TARGET_VOL:.0%} volatility, capped by half-Kelly "
                                     f"and {LEVER_CAP:.0f}x). Expect drawdowns near {lev:.2f}x the {edge['maxdd']:.0%} seen; "
                                     "paper trade first."}


def assess(name: str, period: str, net: pd.Series, edge: pd.Series, note: str = "") -> dict:
    n, e = series_stats(net), series_stats(edge)
    return {"study": name, "period": period, "months": e["n"], "net": n, "edge": e, "sizing": sizing(e), "note": note}


# study name -> its report in reports/, which gets a "Risk and sizing" section
REPORT_FILES = {"12-1 momentum (S&P 500)": "momentum_backtest.md", "Short-term reversal (S&P 500)": "reversal_backtest.md",
                "ML rank, gradient boosting (S&P 500)": "ml_rank_backtest.md", "Quality and value tilts (S&P 500)": "quality_value_backtest.md",
                "Frontier country ETFs": "frontier_etf_backtest.md", "Form 4 cluster buys (US)": "form4_backtest.md",
                "Form 4 opportunistic insiders (US)": "form4_opportunistic.md", "FCA short rises, shorted (UK)": "fca_shorts_study.md",
                "Post-earnings drift, top quintile (US)": "pead_study.md",
                "Cross-asset trend following (ETFs)": "trend_following.md"}
SECTION_START, SECTION_END = "<!-- risk-sizing:start -->", "<!-- risk-sizing:end -->"


# ---------- the studies (read from the artefacts in reports/, no network) ----------

def _monthly_study(name: str, path, split: str, cost: float, note: str = "") -> dict | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    oos = df[df["formed"].astype(str) >= split]
    col = f"net_{cost:g}"
    edge = oos[col] - oos["bench_ew"] if "bench_ew" in oos else oos["long_excess"] - (oos["gross"] - oos[col])
    return assess(name, f"{oos['month'].iloc[0]} to {oos['month'].iloc[-1]}", oos[col], edge, note)


def _reversal(path, split: str, cost: float) -> dict | None:
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["day"], index_col="day")
    oos = df[df.index >= pd.Timestamp(split)]
    col = f"net_{cost:g}"
    net, edge = daily_to_monthly(oos[col]), daily_to_monthly(oos[col] - oos["bench_ew"])
    return assess("Short-term reversal (S&P 500)", f"{net.index[0]} to {net.index[-1]}", net, edge,
                  "Daily book compounded to months.")


def _events(name: str, df: pd.DataFrame, date_col: str, net, edge, note: str) -> dict | None:
    if df.empty:
        return None
    n, e = cohort_series(df[date_col], net), cohort_series(df[date_col], edge)
    if e.empty:
        return None
    return assess(name, f"{e.index[0]} to {e.index[-1]}", n, e, note)


def studies(reports=None) -> list[dict]:
    R = reports or config.REPORTS_DIR
    out = [
        _monthly_study("12-1 momentum (S&P 500)", R / "momentum_monthly.csv", config.MOMENTUM_SPLIT, config.MOMENTUM_COSTS[0]),
        _reversal(R / "reversal_daily.csv", config.REVERSAL_SPLIT, config.REVERSAL_COSTS[0]),
        _monthly_study("ML rank, gradient boosting (S&P 500)", R / "ml_rank_monthly.csv", config.ML_SPLIT, config.ML_COSTS[0]),
        _monthly_study("Quality and value tilts (S&P 500)", R / "quality_value_monthly.csv", config.QV_SPLIT, config.MOMENTUM_COSTS[0]),
        _monthly_study("Frontier country ETFs", R / "frontier_etf_monthly.csv", config.FRONTIER_SPLIT, config.FRONTIER_COSTS[0],
                       "Edge is the long-only excess over the equal-weight ETF basket, net of costs."),
        _monthly_study("Cross-asset trend following (ETFs)", R / "trend_following_monthly.csv", config.TREND_SPLIT, config.TREND_COSTS[0],
                       "Edge is the trend book minus the always-long book with identical sizing, net of costs; no leverage financing."),
    ]
    p = R / "form4_backtest_clusters.csv"
    if p.exists():
        df = pd.read_csv(p)
        df = df[df["have_prices"].astype(str) == "True"]
        out.append(_events("Form 4 cluster buys (US)", df, "entry_date", df["net_20d"], df["excess_20d"],
                           f"20-day trades, {config.ROUND_TRIP_COST:.1%} round trip, edge vs {config.BACKTEST_BENCHMARK}. No fitted parameters."))
    p = R / "form4_opportunistic_events.csv"
    if p.exists():
        df = pd.read_csv(p)
        df = df[(df["have_prices"].astype(str) == "True") & (df["kind"] == "opportunistic")]
        out.append(_events("Form 4 opportunistic insiders (US)", df, "entry_date", df["net_20d"], df["excess_20d"],
                           "20-day trades, liquidity-tiered costs."))
    p = R / "fca_short_events.csv"
    if p.exists():
        df = pd.read_csv(p)
        df = df[(df["have_prices"].astype(str) == "True") & (df["kind"] == "rise")]
        # traded as a short: profit when the stock falls, same round-trip cost
        out.append(_events("FCA short rises, shorted (UK)", df, "entry_date", -df["gross_20d"] - df["cost"],
                           -df["gexcess_20d"] - df["cost"], "Short the stock for 20 days after a rise; borrow cost ignored, so this flatters it."))
    p = R / "pead_events.csv.gz"
    if p.exists():
        df = pd.read_csv(p)
        df = df[(df["quintile"] == 5) & (df["liquid"].astype(str) == "True") & (df["filed"] >= config.PEAD_OOS_START)]
        out.append(_events("Post-earnings drift, top quintile (US)", df, "entry_date", df["gross_20d"] - df["cost"],
                           df["excess_20d"] - df["cost"], f"Out of sample from {config.PEAD_OOS_START[:4]}; 20-day trades, edge vs SPY."))
    return [s for s in out if s]


# ---------- formatting ----------

def _f(x, spec: str) -> str:
    return format(x, spec) if x is not None and np.isfinite(x) else "n/a"


def table(rows: list[dict], label: str = "study") -> list[str]:
    L = [f"| {label} | period | net Sharpe | net max drawdown | edge Sharpe | edge vol | edge max drawdown | suggested leverage |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        n, e = r["net"], r["edge"]
        lev = f"{r['sizing']['leverage']:.2f}x" if r["sizing"]["leverage"] else "none"
        L.append(f"| {r['study']} | {r['period']} | {_f(n['sharpe'], '.2f')} | {_f(n['maxdd'], '.0%')} | {_f(e['sharpe'], '.2f')} | "
                 f"{_f(e['vol'], '.1%')} | {_f(e['maxdd'], '.0%')} | {lev} |")
    return L


GUIDANCE = (f"Leverage is suggested only when the out-of-sample edge Sharpe, net of costs, is at least {LEVER_MIN_SHARPE:.1f} "
            f"over {LEVER_MIN_MONTHS}+ months; it then targets {LEVER_TARGET_VOL:.0%} volatility, capped by half-Kelly and "
            f"{LEVER_CAP:.0f}x. Not financial advice.")


def report(rows: list[dict]) -> str:
    L = ["# Risk-adjusted record of the studies", "",
         "**Verdict:** " + ("no study earns leverage: none showed an edge out of sample. " if not any(r["sizing"]["leverage"] for r in rows) else "") + GUIDANCE, "",
         "Out-of-sample periods where a study chose a variant (whole sample for event rules with nothing fitted), at the realistic cost for each universe. **Net** is the book itself after costs; a long-only "
         "book's Sharpe is mostly the market's, so read **edge** (net excess over the benchmark, i.e. a market-hedged book) to "
         "judge the signal. Event studies are monthly cohorts of 20-day trades (cash in months with no signal), annualised with sqrt(12).", ""]
    L += table(rows) + [""]
    L += ["## Notes", ""] + [f"- **{r['study']}**: {r['sizing']['text']}" + (f" {r['note']}" if r["note"] else "") for r in rows]
    L += ["", "A Sharpe estimated from N years has a standard error of roughly 1/sqrt(N), so 10 years cannot tell 0.3 from 0.9. "
          "Several variants were tried in each study, which biases the best one upwards. Built by `python run.py risk`."]
    return "\n".join(L)


def section(row: dict) -> str:
    """The block appended to a study's own report (rebuilt in place on every run)."""
    n, e = row["net"], row["edge"]
    return "\n".join([SECTION_START, "## Risk and sizing", "",
                      f"Period {row['period']} ({row['months']} months), realistic costs. Net book: Sharpe {_f(n['sharpe'], '.2f')}, "
                      f"volatility {_f(n['vol'], '.1%')}, max drawdown {_f(n['maxdd'], '.0%')}. Edge (net excess over the benchmark): "
                      f"Sharpe {_f(e['sharpe'], '.2f')}, volatility {_f(e['vol'], '.1%')}, max drawdown {_f(e['maxdd'], '.0%')}.", "",
                      f"**Suggested leverage:** {row['sizing']['text']}", "", GUIDANCE, "",
                      "All studies side by side: `reports/risk_summary.md`.", SECTION_END])


def stamp_reports(rows: list[dict], reports=None) -> list:
    """Write or replace the Risk and sizing section at the end of each study's report."""
    R, done = reports or config.REPORTS_DIR, []
    for row in rows:
        path = R / REPORT_FILES.get(row["study"], "_none_")
        if not path.exists():
            continue
        text = path.read_text()
        if SECTION_START in text and SECTION_END in text:
            text = text[:text.index(SECTION_START)] + text[text.index(SECTION_END) + len(SECTION_END):]
        path.write_text(text.rstrip() + "\n\n" + section(row) + "\n")
        done.append(path)
    return done


def clean(o):
    """JSON-safe copy: numpy numbers to Python, NaN to None, floats to 4 places."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (float, np.floating)):
        return round(float(o), 4) if np.isfinite(o) else None
    if isinstance(o, np.integer):
        return int(o)
    return o


def run(reports=None) -> str:
    R = reports or config.REPORTS_DIR
    rows = studies(R)
    text = report(rows)
    stamp_reports(rows, R)
    (R / RISK_MD.name).write_text(text + "\n")
    (R / RISK_JSON.name).write_text(json.dumps({"guidance": GUIDANCE, "studies": [clean(r) for r in rows]}, indent=1) + "\n")
    return text
