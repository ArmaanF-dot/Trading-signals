"""Backtest of 12-1 month cross-sectional momentum on S&P 500 members (Jegadeesh-Titman style).

Each month-end t we rank the stocks that were S&P 500 members *on that date* by their return from
the end of month t-12 to the end of month t-1 (the latest month is skipped, the usual short-term
reversal guard). We buy the top slice equal-weight and hold for H months, with H overlapping
cohorts (so with H=2 half the book is rebuilt each month). Returns are monthly, from Yahoo
adjusted closes (dividends and splits included).

Costs: turnover is sum(|w_new - w_old|) each month, charged at half the round-trip cost per unit.

Out-of-sample: the four variants (top decile/quintile x hold 1/2 months) are compared on
formations before config.MOMENTUM_SPLIT only; the in-sample winner is then reported on later
months it never saw. The 12-1 rule itself comes from the literature (1993), so the whole of
2000 onwards is already out of sample for the idea.

Known biases, repeated in the report:
- Survivorship: membership is point-in-time, but Yahoo has no prices for many delisted or
  renamed members, so those drop out of the ranking. Coverage per month is reported.
- Recycled tickers: a symbol now used by another company can carry the wrong history. Stock-month
  returns above config.MOMENTUM_MAX_MONTHLY_RET are dropped as bad data and counted.
"""
import io
import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import config
from edge import prices

REPORT = Path("reports/momentum_backtest.md")
MONTHLY_CSV = Path("reports/momentum_monthly.csv")
VARIANTS = [(0.1, 1), (0.1, 2), (0.2, 1), (0.2, 2)]  # (top fraction, holding months)


# ---------- data ----------

def load_membership(text: str) -> pd.Series:
    """CSV with columns date,tickers (comma-joined) -> Series of frozensets indexed by date."""
    df = pd.read_csv(io.StringIO(text))
    df["date"] = pd.to_datetime(df["date"])
    s = df.set_index("date")["tickers"].map(lambda t: frozenset(x.strip() for x in str(t).split(",") if x.strip()))
    return s.sort_index()


def members_at_month_ends(membership: pd.Series, months: pd.PeriodIndex) -> dict:
    """{month: set of members on that month's last day} using the last list on or before it."""
    out = {}
    for m in months:
        before = membership[membership.index <= m.to_timestamp(how="end")]
        if not before.empty:
            out[m] = before.iloc[-1]
    return out


def monthly_closes(bars: pd.DataFrame) -> pd.Series:
    """Yahoo monthly bars (timestamped at month start) -> adjusted close per calendar month."""
    if bars.empty:
        return pd.Series(dtype=float)
    s = bars["close"].copy()
    s.index = s.index.to_period("M")
    return s[~s.index.duplicated(keep="last")]


def fetch_panel(tickers, fetch=None, workers: int = 3, retry_pause: float = 30.0) -> pd.DataFrame:
    """Month x ticker panel of adjusted closes; tickers with no Yahoo data are absent.
    Tickers that come back empty get one more try after a pause (Yahoo rate limits bursts)."""
    fetch = fetch or (lambda sym: prices.fetch_bars(sym, config.YAHOO_MONTHLY_MAX_URL))
    todo, series = sorted(set(tickers)), {}

    def one(t):
        return t, monthly_closes(fetch(prices.yahoo_symbol(t, "us")))

    for attempt in range(2):
        with ThreadPoolExecutor(workers) as ex:
            got = dict(ex.map(one, todo))
        series.update({t: s for t, s in got.items() if not s.empty})
        todo = [t for t in todo if t not in series]
        print(f"momentum: pass {attempt + 1}: {len(series)} priced, {len(todo)} empty")
        if not todo or attempt == 1:
            break
        time.sleep(retry_pause)
    return pd.DataFrame(series).sort_index()


def gap_share(panel: pd.DataFrame) -> float:
    """Share of priced tickers with a hole inside their monthly history (a sign of coarsened data)."""
    holes = [s.loc[s.first_valid_index():s.last_valid_index()].isna().any() for _, s in panel.items() if s.notna().any()]
    return float(np.mean(holes)) if holes else 0.0


# ---------- backtest ----------

def clean_returns(panel: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Monthly simple returns with implausible values (bad data) set to NaN; also returns how many were dropped."""
    r = panel.pct_change(fill_method=None)
    bad = (r > config.MOMENTUM_MAX_MONTHLY_RET) | (r <= -1)
    return r.mask(bad), int(bad.sum().sum())


def signal(rets: pd.DataFrame) -> pd.DataFrame:
    """12-1 momentum known at the end of month t: close(t-1) / close(t-12) - 1, compounded from the
    11 cleaned monthly returns so a bad-data jump removes the stock instead of topping the ranking."""
    return np.expm1(np.log1p(rets).shift(1).rolling(11, min_periods=11).sum())


def cohorts(panel: pd.DataFrame, rets: pd.DataFrame, members: dict, top: float, first: str) -> tuple[dict, dict]:
    """{formation month: equal weights of winners} and {month: (eligible, members)}."""
    mom = signal(rets)
    picks, sizes = {}, {}
    for m in panel.index[panel.index >= pd.Period(first, "M")]:
        if m not in members:
            continue
        cols = [t for t in members[m] if t in panel.columns]
        row = mom.loc[m, cols]
        ok = row.dropna()
        ok = ok[panel.loc[m, ok.index].notna()]
        sizes[m] = (len(ok), len(members[m]))
        if len(ok) < 50:
            continue
        n = max(1, int(round(len(ok) * top)))
        winners = ok.sort_values(ascending=False).index[:n]
        picks[m] = pd.Series(1.0 / n, index=winners)
    return picks, sizes


def run_strategy(panel: pd.DataFrame, rets: pd.DataFrame, members: dict, top: float, hold: int,
                 costs, first: str) -> pd.DataFrame:
    """Monthly rows (labelled by the month the return is earned) with gross, net-per-cost,
    equal-weight universe benchmark, turnover and holdings count."""
    picks, sizes = cohorts(panel, rets, members, top, first)
    return run_from_picks(picks, sizes, rets, members, hold, costs)


def run_from_picks(picks: dict, sizes: dict, rets: pd.DataFrame, universe: dict, hold: int, costs) -> pd.DataFrame:
    """Hold each formation's picks for `hold` months as overlapping cohorts. picks: {formation month:
    weights}; sizes: {month: (eligible, members)}; universe: {month: tickers} for the cost-free
    equal-weight benchmark, rebalanced monthly."""
    months = sorted(picks)
    rows, prev_w = [], pd.Series(dtype=float)
    for m in months:
        nxt = m + 1
        if nxt not in rets.index:
            break
        live = [picks[k] for k in (m - j for j in range(hold)) if k in picks]
        w = pd.concat(live, axis=1).fillna(0).sum(axis=1) / len(live)
        r = rets.loc[nxt, w.index]
        held = r.notna()
        if held.sum() == 0:
            continue
        w_eff = w[held] / w[held].sum()  # names with no next-month price (delisted, bad data) are dropped
        gross = float((w_eff * r[held]).sum())
        turnover = float(w.sub(prev_w, fill_value=0).abs().sum())
        uni = [t for t in universe[m] if t in rets.columns]
        ur = rets.loc[nxt, uni].dropna()
        bench = float(ur.mean()) if len(ur) else np.nan
        row = {"month": str(nxt), "formed": str(m), "gross": gross, "bench_ew": bench, "turnover": turnover,
               "holdings": int(held.sum()), "eligible": sizes[m][0], "members": sizes[m][1]}
        for c in costs:
            row[f"net_{c:g}"] = gross - turnover * c / 2
        rows.append(row)
        prev_w = w
    return pd.DataFrame(rows)


# ---------- stats and report ----------

def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 2:
        return {"n": len(r), "ann": np.nan, "vol": np.nan, "sharpe": np.nan, "t": np.nan, "maxdd": np.nan}
    mu, sd = r.mean(), r.std(ddof=1)
    curve = (1 + r).cumprod()
    return {"n": len(r), "ann": (1 + r).prod() ** (12 / len(r)) - 1, "vol": sd * math.sqrt(12),
            "sharpe": mu / sd * math.sqrt(12) if sd else np.nan, "t": mu / (sd / math.sqrt(len(r))) if sd else np.nan,
            "maxdd": float((curve / curve.cummax() - 1).min())}


def summary(df: pd.DataFrame, costs) -> pd.DataFrame:
    """One row per (series): annualised return, Sharpe, and the excess over the EW universe with its t-stat."""
    out = []
    for col in ["gross"] + [f"net_{c:g}" for c in costs]:
        s, x = stats(df[col]), stats(df[col] - df["bench_ew"])
        out.append({"series": col, "ann": s["ann"], "sharpe": s["sharpe"], "maxdd": s["maxdd"],
                    "excess_ann_mean": (df[col] - df["bench_ew"]).mean() * 12, "excess_t": x["t"]})
    b = stats(df["bench_ew"])
    out.append({"series": "bench_ew", "ann": b["ann"], "sharpe": b["sharpe"], "maxdd": b["maxdd"],
                "excess_ann_mean": 0.0, "excess_t": np.nan})
    return pd.DataFrame(out)


def pick_variant(results: dict, split: str, cost: float) -> tuple:
    """In-sample choice: highest net Sharpe at the given cost on months before the split."""
    best, best_s = None, -np.inf
    for key, df in results.items():
        ins = df[df["formed"] < split]
        s = stats(ins[f"net_{cost:g}"])["sharpe"]
        if pd.notna(s) and s > best_s:
            best, best_s = key, s
    return best


def _fmt_table(sm: pd.DataFrame) -> list[str]:
    lines = ["| series | CAGR | Sharpe | max drawdown | excess vs EW universe (ann.) | t-stat |", "|---|---|---|---|---|---|"]
    for r in sm.itertuples():
        t = "" if pd.isna(r.excess_t) else f"{r.excess_t:.2f}"
        lines.append(f"| {r.series} | {r.ann:.1%} | {r.sharpe:.2f} | {r.maxdd:.0%} | {r.excess_ann_mean:+.1%} | {t} |")
    return lines


def verdict(oos: pd.DataFrame, costs) -> str:
    """Edge = out-of-sample net excess over the EW universe that is positive with t >= 2 at the realistic cost."""
    real = f"net_{costs[0]:g}"
    x = oos[real] - oos["bench_ew"]
    t = stats(x)["t"]
    house = [(c, (oos[f"net_{c:g}"] - oos["bench_ew"]).mean() * 12) for c in costs[1:]]
    house_txt = "; ".join(f"at {c:.0%} round trip {v:+.1%} a year" for c, v in house)
    if x.mean() > 0 and t >= 2:
        return f"EDGE: out of sample the winners beat the equal-weight universe by {x.mean() * 12:+.1%} a year (t {t:.2f}) at {costs[0]:.1%} costs ({house_txt})."
    return f"NO EDGE: out of sample the excess over the equal-weight universe is {x.mean() * 12:+.1%} a year (t {t:.2f}) at {costs[0]:.1%} costs, not reliably above zero ({house_txt})."


def report(results: dict, chosen: tuple, costs, split: str, bad: int, n_tickers: int, n_priced: int) -> str:
    df = results[chosen]
    ins, oos = df[df["formed"] < split], df[df["formed"] >= split]
    cov = (df["eligible"] / df["members"]).describe()
    lines = ["# 12-1 momentum on S&P 500 members", "",
             f"**Verdict:** {verdict(oos, costs)}", "",
             "Rule: each month-end rank point-in-time S&P 500 members by return from month t-12 to t-1, buy the top slice "
             "equal-weight, hold with overlapping cohorts. Monthly Yahoo adjusted closes. Benchmark: equal weight over all priced "
             "members at formation (isolates the stock selection from the market). Costs: turnover x half the round trip.", "",
             f"Chosen in sample (best net Sharpe at {costs[0]:.1%}, formations before {split}): **top {chosen[0]:.0%}, hold {chosen[1]} month(s)**.", "",
             "## In-sample variant comparison (formations before the split)", "",
             "| variant | gross CAGR | net CAGR at realistic cost | net Sharpe | monthly turnover |", "|---|---|---|---|---|"]
    for key, d in results.items():
        i = d[d["formed"] < split]
        g, n = stats(i["gross"]), stats(i[f"net_{costs[0]:g}"])
        lines.append(f"| top {key[0]:.0%}, hold {key[1]} | {g['ann']:.1%} | {n['ann']:.1%} | {n['sharpe']:.2f} | {i['turnover'].mean():.0%} |")
    for name, part in (("In sample", ins), ("Out of sample", oos)):
        lines += ["", f"## {name}: {part['month'].iloc[0]} to {part['month'].iloc[-1]} ({len(part)} months)", ""]
        lines += _fmt_table(summary(part, costs))
    lines += ["", "## Data and biases", "",
              f"- {n_tickers} tickers were ever members; {n_priced} have Yahoo history. Eligible share of members per month: "
              f"median {cov['50%']:.0%}, min {cov['min']:.0%}. Missing names are mostly delisted or acquired companies (survivorship bias).",
              f"- {bad} stock-month returns above +{config.MOMENTUM_MAX_MONTHLY_RET:.0%} (or at -100%) were dropped as bad data.",
              "- Held names with no next-month price are dropped and the book reweighted, so delisting losses are missed.",
              f"- Average monthly turnover of the chosen variant: {df['turnover'].mean():.0%} (sum of absolute weight changes).",
              f"- The {costs[0]:.1%} round trip is realistic for S&P 500 names; {', '.join(f'{c:.0%}' for c in costs[1:])} are the project's "
              "small-cap house assumptions and are shown as a stress test.",
              "", f"Monthly series: `{MONTHLY_CSV}`."]
    return "\n".join(lines) + "\n"


def main() -> None:
    costs, split, first = config.MOMENTUM_COSTS, config.MOMENTUM_SPLIT, config.MOMENTUM_FIRST_FORMATION
    text = requests.get(config.SP500_MEMBERSHIP_URL, timeout=60).text
    membership = load_membership(text)
    tickers = set().union(*membership.tolist())
    print(f"momentum: {len(tickers)} tickers ever in the S&P 500; fetching monthly prices")
    panel = fetch_panel(tickers)
    print(f"momentum: {panel.shape[1]} tickers priced, {panel.index.min()} to {panel.index.max()}, "
          f"{gap_share(panel):.0%} with gaps inside their history")
    rets, bad = clean_returns(panel)
    members = members_at_month_ends(membership, panel.index)
    results = {v: run_strategy(panel, rets, members, v[0], v[1], costs, first) for v in VARIANTS}
    chosen = pick_variant(results, str(pd.Period(split, "M")), costs[0])
    REPORT.parent.mkdir(exist_ok=True)
    results[chosen].to_csv(MONTHLY_CSV, index=False)
    md = report(results, chosen, costs, str(pd.Period(split, "M")), bad, len(tickers), panel.shape[1])
    REPORT.write_text(md)
    print(md)
