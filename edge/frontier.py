"""Do commodity-linked country ETFs lag the commodity that drives them?

Idea (from the exotic-markets request): slow, local information about a commodity-dependent country
should reach its listed proxy with a delay. Mongolia, Tajikistan and similar markets have no
tradeable proxy, so the test uses the liquid US-listed single-country ETFs that do (Colombia, Chile,
Peru, South Africa, Norway, Canada, Australia, Mexico, Saudi Arabia, Argentina) and the futures that
drive them.

Each month-end, for every ETF with a history, two signals over a 1 or 3 month look-back:
  raw: the return of its linked commodity;
  gap: beta x commodity return - ETF return (the part of the commodity move the ETF has not yet priced),
       beta = trailing 24-month slope of ETF on commodity returns, known at the time.
Rank ETFs, long the top third, short the bottom third (equal weight), hold one month. The variant is
chosen on formations before FRONTIER_SPLIT; the rest is out of sample. Costs: turnover x half the round trip.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

import config
from edge import momentum

REPORT = Path("reports/frontier_etf_backtest.md")
MONTHLY_CSV = Path("reports/frontier_etf_monthly.csv")

# ETF -> (commodity future, label). Colombia: oil; Chile/Peru/Australia: copper; South Africa: gold;
# Norway: Brent; Canada/Mexico/Saudi: oil; Argentina: soybeans.
PAIRS = {
    "GXG": ("CL=F", "Colombia / oil"), "ECH": ("HG=F", "Chile / copper"), "EPU": ("HG=F", "Peru / copper"),
    "EZA": ("GC=F", "South Africa / gold"), "ENOR": ("BZ=F", "Norway / Brent"), "EWC": ("CL=F", "Canada / oil"),
    "EWA": ("HG=F", "Australia / copper"), "EWW": ("CL=F", "Mexico / oil"), "KSA": ("CL=F", "Saudi Arabia / oil"),
    "ARGT": ("ZS=F", "Argentina / soybeans"),
}
VARIANTS = [(kind, lb) for kind in ("raw", "gap") for lb in (1, 3)]
BETA_WINDOW, BETA_MIN, MIN_ETFS = 24, 18, 6


def cum(rets: pd.Series | pd.DataFrame, lb: int):
    return np.expm1(np.log1p(rets).rolling(lb, min_periods=lb).sum())


def rolling_beta(y: pd.Series, x: pd.Series) -> pd.Series:
    """Trailing slope of y on x (both monthly returns), using only data up to and including month t."""
    cov = y.rolling(BETA_WINDOW, min_periods=BETA_MIN).cov(x)
    var = x.rolling(BETA_WINDOW, min_periods=BETA_MIN).var()
    return cov / var


def signals(rets: pd.DataFrame, kind: str, lb: int) -> pd.DataFrame:
    """Month x ETF signal known at the end of month t (uses returns up to t)."""
    out = {}
    for etf, (fut, _) in PAIRS.items():
        if etf not in rets or fut not in rets:
            continue
        c, e = cum(rets[fut], lb), cum(rets[etf], lb)
        out[etf] = c if kind == "raw" else rolling_beta(rets[etf], rets[fut]) * c - e
    return pd.DataFrame(out)


def run_variant(rets: pd.DataFrame, kind: str, lb: int, costs, first: str) -> pd.DataFrame:
    sig = signals(rets, kind, lb)
    nxt = rets[[c for c in sig.columns]].shift(-1)  # return realised in month t+1
    rows, prev = [], pd.Series(dtype=float)
    for m in sig.index[sig.index >= pd.Period(first, "M")]:
        s, r = sig.loc[m].dropna(), nxt.loc[m]
        ok = s.index[r.reindex(s.index).notna()]
        if len(ok) < MIN_ETFS or m == sig.index[-1]:
            continue
        s, r = s[ok], r[ok]
        k = max(1, len(s) // 3)
        order = s.sort_values()
        short, long = order.index[:k], order.index[-k:]
        w = pd.Series(0.0, index=ok)
        w[long], w[short] = 1 / k, -1 / k
        turn = w.sub(prev, fill_value=0).abs().sum()
        prev = w
        gross = float((w * r).sum())
        ic = s.rank().corr(r.rank())
        row = {"month": str(m + 1), "formed": str(m), "n": len(s), "gross": gross, "turnover": turn,
               "long_excess": float(r[long].mean() - r.mean()), "ic": ic}
        for c in costs:
            row[f"net_{c:g}"] = gross - turn * c / 2
        rows.append(row)
    return pd.DataFrame(rows)


def tstat(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) else float("nan")


def part_stats(df: pd.DataFrame, costs) -> pd.DataFrame:
    rows = []
    for col in ["gross"] + [f"net_{c:g}" for c in costs]:
        s = momentum.stats(df[col])
        rows.append({"series": col, "ann": s["ann"], "sharpe": s["sharpe"], "maxdd": s["maxdd"], "t": s["t"]})
    return pd.DataFrame(rows)


def pick(results: dict, split: str, cost: float):
    best, best_s = None, -np.inf
    for key, df in results.items():
        s = momentum.stats(df[df["formed"] < split][f"net_{cost:g}"])["sharpe"]
        if pd.notna(s) and s > best_s:
            best, best_s = key, s
    return best


def verdict(oos: pd.DataFrame, costs) -> str:
    real = f"net_{costs[0]:g}"
    t = tstat(oos[real])
    house = "; ".join(f"at {c:.0%} round trip {oos[f'net_{c:g}'].mean() * 12:+.1%} a year" for c in costs[1:])
    mean = oos[real].mean() * 12
    if mean > 0 and t >= 2:
        return f"EDGE: out of sample the long-short earns {mean:+.1%} a year (t {t:.2f}) at {costs[0]:.1%} costs ({house})."
    return f"NO EDGE: out of sample the long-short earns {mean:+.1%} a year (t {t:.2f}) at {costs[0]:.1%} costs ({house})."


def report(results: dict, chosen, costs, split: str, coverage: dict, missing: list) -> str:
    df = results[chosen]
    ins, oos = df[df["formed"] < split], df[df["formed"] >= split]
    lines = ["# Commodity-linked country ETFs: do they lag their commodity?", "",
             f"**Verdict:** {verdict(oos, costs)}", "",
             "Rule: each month-end rank single-country ETFs by a commodity signal (raw = linked commodity return; gap = beta x commodity "
             "return minus the ETF's own return, i.e. the move not yet priced), long the top third, short the bottom third, equal weight, "
             "hold one month. Monthly Yahoo adjusted closes for ETFs and continuous front-month futures. "
             "Costs: turnover x half the round trip.", "",
             f"Chosen in sample (best net Sharpe at {costs[0]:.1%}, formations before {split}): **{chosen[0]} signal, {chosen[1]} month look-back**.", "",
             "## In-sample variant comparison", "",
             "| variant | gross ann. | net Sharpe | mean rank IC | IC t | monthly turnover |", "|---|---|---|---|---|---|"]
    for key, d in results.items():
        i = d[d["formed"] < split]
        g, n = momentum.stats(i["gross"]), momentum.stats(i[f"net_{costs[0]:g}"])
        lines.append(f"| {key[0]}, {key[1]}m | {g['ann']:.1%} | {n['sharpe']:.2f} | {i['ic'].mean():+.3f} | {tstat(i['ic']):.2f} | {i['turnover'].mean():.0%} |")
    lines += ["", "## Out-of-sample variant comparison (for transparency, not used to choose)", "",
              "| variant | gross ann. | net Sharpe | mean rank IC | IC t |", "|---|---|---|---|---|"]
    for key, d in results.items():
        o = d[d["formed"] >= split]
        g, n = momentum.stats(o["gross"]), momentum.stats(o[f"net_{costs[0]:g}"])
        lines.append(f"| {key[0]}, {key[1]}m | {g['ann']:.1%} | {n['sharpe']:.2f} | {o['ic'].mean():+.3f} | {tstat(o['ic']):.2f} |")
    for name, part in (("In sample", ins), ("Out of sample", oos)):
        lines += ["", f"## {name}: {part['month'].iloc[0]} to {part['month'].iloc[-1]} ({len(part)} months)", "",
                  "| series | ann. return | Sharpe | max drawdown | t-stat |", "|---|---|---|---|---|"]
        for r in part_stats(part, costs).itertuples():
            lines.append(f"| {r.series} | {r.ann:.1%} | {r.sharpe:.2f} | {r.maxdd:.0%} | {r.t:.2f} |")
        lines.append(f"\nLong leg minus the equal-weight ETF universe: {part['long_excess'].mean() * 12:+.1%} a year gross (t {tstat(part['long_excess']):.2f}). "
                     f"Mean rank IC {part['ic'].mean():+.3f} (t {tstat(part['ic']):.2f}).")
    lines += ["", "## Data and biases", "",
              "- ETFs priced: " + ", ".join(f"{k} (from {v})" for k, v in coverage.items()) + (f"; no Yahoo history for {', '.join(missing)} (delisted)" if missing else "") + ".",
              "- Only ETFs that still trade are included (dead ones such as the Russia and Nigeria ETFs are missing): survivorship bias flatters long positions.",
              "- Only 10 ETFs and 3 per leg, so results are noisy; in-sample window is short (about 4.5 years).",
              "- Futures are Yahoo continuous front-month series; roll gaps add noise to commodity returns.",
              "- Shorting these ETFs from a UK retail account means CFDs or spread bets with financing costs not modelled here; the long leg is the practical one.",
              f"- Average monthly turnover of the chosen variant: {df['turnover'].mean():.0%}.",
              "", f"Monthly series: `{MONTHLY_CSV}`."]
    return "\n".join(lines) + "\n"


def daily_to_monthly(bars: pd.DataFrame) -> pd.Series:
    """Daily bars -> last close of each calendar month (daily data has no holes, unlike Yahoo's monthly futures bars)."""
    if bars.empty:
        return pd.Series(dtype=float)
    s = bars["close"].copy()
    s.index = s.index.to_period("M")
    return s[~s.index.duplicated(keep="last")]


def fetch_panel(symbols) -> pd.DataFrame:
    from concurrent.futures import ThreadPoolExecutor
    from edge import prices
    with ThreadPoolExecutor(3) as ex:
        got = dict(ex.map(lambda t: (t, daily_to_monthly(prices.fetch_bars(t, config.YAHOO_DAILY_MAX_URL))), sorted(symbols)))
    missing = sorted(t for t, s in got.items() if s.empty)
    print(f"frontier: no data for {missing}")
    return pd.DataFrame({t: s for t, s in got.items() if not s.empty}).sort_index()


def main() -> None:
    costs, split, first = config.FRONTIER_COSTS, config.FRONTIER_SPLIT, config.FRONTIER_FIRST_FORMATION
    symbols = set(PAIRS) | {f for f, _ in PAIRS.values()}
    panel = fetch_panel(symbols)
    print(f"frontier: {panel.shape[1]} of {len(symbols)} symbols priced")
    rets, bad = momentum.clean_returns(panel)
    results = {v: run_variant(rets, v[0], v[1], costs, first) for v in VARIANTS}
    results = {k: d for k, d in results.items() if not d.empty}
    chosen = pick(results, split, costs[0])
    coverage = {e: str(panel[e].first_valid_index()) for e in PAIRS if e in panel}
    missing = [e for e in PAIRS if e not in panel]
    REPORT.parent.mkdir(exist_ok=True)
    results[chosen].to_csv(MONTHLY_CSV, index=False)
    md = report(results, chosen, costs, split, coverage, missing)
    REPORT.write_text(md)
    print(md)
