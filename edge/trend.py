"""Cross-asset time-series trend following on liquid ETFs, with volatility targeting.

Universe (US-listed, free Yahoo adjusted closes, all trading by early 2007): equities (SPY, IWM, EFA, EEM, EWJ, VNQ),
bonds (TLT, IEF, LQD, HYG, TIP), commodities (GLD, SLV, USO, DBC, DBA) and currencies (UUP, FXE, FXY, FXB, FXA, FXC).
Commodity and currency ETFs carry their own roll and carry returns, which is what a retail investor would actually earn.

Each month-end, per asset, a trend signal s in {-1, 0, +1} from data up to that day:
  12m:   sign of the 12-month return;
  sma10: price above or below its 10-month average of month-end closes;
  blend: mean of the signs of the 1, 3 and 12-month returns (so s can be 1/3 or 2/3).
Long/short ("ls") uses s as is; long-only ("lo") sets negative signals to zero (cash earns nothing here).
Sizing: weight_i = s_i / (N x vol_i), vol_i the trailing 60-day annualised daily vol, N the assets available;
the book is then scaled so its ex-ante volatility (trailing 126-day covariance) equals TREND_VOL_TARGET, leverage capped.
The book is held one month. Benchmark: the same sizing with s = +1 everywhere (always-long risk parity), so any "edge"
is what the trend filter adds over simply owning the same assets at the same risk. A 60/40 SPY/IEF column is also kept.

Costs: turnover (sum of |change in weight|) x half the round trip, on the weights actually held.
Variants chosen on formations before TREND_SPLIT; later months are out of sample. The 12-month rule is from the
literature (Moskowitz, Ooi, Pedersen 2012 and many follow-ups), so the idea itself was not discovered on this data.
Financing of leverage and shorts is NOT modelled (cash earns 0); ETF expense ratios are already in the prices.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

import config
from edge import momentum

REPORT = Path("reports/trend_following.md")
MONTHLY_CSV = Path("reports/trend_following_monthly.csv")

CLASSES = {
    "equities": ["SPY", "IWM", "EFA", "EEM", "EWJ", "VNQ"],
    "bonds": ["TLT", "IEF", "LQD", "HYG", "TIP"],
    "commodities": ["GLD", "SLV", "USO", "DBC", "DBA"],
    "currencies": ["UUP", "FXE", "FXY", "FXB", "FXA", "FXC"],
}
UNIVERSE = [t for v in CLASSES.values() for t in v]
SIGNALS = ["12m", "sma10", "blend"]
SIDES = ["ls", "lo"]
VARIANTS = [(s, side) for s in SIGNALS for side in SIDES]
VOL_WIN, COV_WIN, MIN_ASSETS = 60, 126, 6


# ---------- signals ----------

def month_end_closes(daily: pd.DataFrame) -> pd.DataFrame:
    m = daily.copy()
    m.index = m.index.to_period("M")
    return m[~m.index.duplicated(keep="last")]


def trend_signal(daily: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Month x asset signal using only closes up to each month-end."""
    mc = month_end_closes(daily)
    if kind == "12m":
        return np.sign(mc / mc.shift(12) - 1)
    if kind == "sma10":
        return np.sign(mc / mc.rolling(10, min_periods=10).mean() - 1)
    if kind == "blend":
        parts = [np.sign(mc / mc.shift(k) - 1) for k in (1, 3, 12)]
        out = sum(parts) / 3
        return out.where(parts[2].notna())  # needs the 12-month history
    raise ValueError(kind)


# ---------- book construction ----------

def monthly_returns(daily: pd.DataFrame) -> pd.DataFrame:
    return month_end_closes(daily).pct_change(fill_method=None)


def vol_scaled_weights(sig: pd.Series, daily_rets: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
    """Weights at date asof from signals and trailing daily returns only (no look-ahead)."""
    hist = daily_rets[daily_rets.index <= asof]
    vol = hist.tail(VOL_WIN).std() * math.sqrt(252)
    ok = sig.dropna().index.intersection(vol.dropna().index)
    ok = [a for a in ok if vol[a] > 0]
    if len(ok) < MIN_ASSETS:
        return pd.Series(dtype=float)
    w = pd.Series({a: sig[a] / (len(ok) * vol[a]) for a in ok})
    cov = hist.tail(COV_WIN)[ok].cov() * 252
    pv = float(np.sqrt(w.values @ cov.values @ w.values))
    if not pv or np.isnan(pv):
        return pd.Series(dtype=float)
    return w * min(config.TREND_LEVERAGE_CAP, config.TREND_VOL_TARGET / pv)


def run_book(daily: pd.DataFrame, sigs: pd.DataFrame, costs, first: str) -> pd.DataFrame:
    """Hold month-t weights through month t+1; rows are the realised months."""
    dr = daily.pct_change(fill_method=None)
    mr = monthly_returns(daily)
    rows, prev = [], pd.Series(dtype=float)
    for m in sigs.index[sigs.index >= pd.Period(first, "M")]:
        if m == sigs.index[-1] or (m + 1) not in mr.index:
            continue
        w = vol_scaled_weights(sigs.loc[m], dr, m.to_timestamp(how="end").normalize())
        if w.empty:
            continue
        r = mr.loc[m + 1].reindex(w.index).fillna(0.0)
        gross = float((w * r).sum())
        turn = float(w.sub(prev, fill_value=0).abs().sum())
        prev = w
        row = {"month": str(m + 1), "formed": str(m), "n": len(w), "gross": gross, "turnover": turn,
               "gross_leverage": float(w.abs().sum()), "net_long_share": float(w.sum() / w.abs().sum()) if w.abs().sum() else 0.0}
        for c in costs:
            row[f"net_{c:g}"] = gross - turn * c / 2
        rows.append(row)
    return pd.DataFrame(rows)


def run_variant(daily: pd.DataFrame, kind: str, side: str, costs, first: str) -> pd.DataFrame:
    sig = trend_signal(daily, kind)
    if side == "lo":
        sig = sig.clip(lower=0)
    book = run_book(daily, sig, costs, first)
    base = trend_signal(daily, kind)
    bench = run_book(daily, base.notna().astype(float).where(base.notna()), costs, first)
    book["bench_ew"] = bench.set_index("formed")[f"net_{costs[0]:g}"].reindex(book["formed"]).values
    book["bench_ew_gross"] = bench.set_index("formed")["gross"].reindex(book["formed"]).values
    mr = monthly_returns(daily)
    sixty = (0.6 * mr["SPY"] + 0.4 * mr["IEF"]).reindex([pd.Period(m, "M") for m in book["month"]])
    book["bench_6040"] = sixty.values
    return book


# ---------- statistics ----------

def sharpe_se(sharpe: float, n_months: int) -> float:
    """Approximate standard error of an annualised Sharpe ratio (iid returns)."""
    years = n_months / 12
    return math.sqrt((1 + 0.5 * sharpe ** 2) / years) if years > 0 and not np.isnan(sharpe) else float("nan")


def tstat(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) else float("nan")


def pick(results: dict, split: str, cost: float):
    best, best_s = None, -np.inf
    for key, df in results.items():
        s = momentum.stats(df[df["formed"] < split][f"net_{cost:g}"])["sharpe"]
        if pd.notna(s) and s > best_s:
            best, best_s = key, s
    return best


def verdict(oos: pd.DataFrame, costs) -> str:
    """EDGE only if the trend book beats the always-long book on a risk-adjusted basis, net of costs, with t >= 2."""
    real = f"net_{costs[0]:g}"
    excess = oos[real] - oos["bench_ew"]
    t, mean = tstat(excess), excess.mean() * 12
    sr = momentum.stats(oos[real])["sharpe"]
    house = f"{oos[f'net_{costs[-1]:g}'].mean() * 12:+.1%} a year at the house {costs[-1]:.1%} round trip"
    tag = "EDGE" if mean > 0 and t >= 2 else "NO EDGE"
    return (f"{tag}: out of sample the trend book earns {oos[real].mean() * 12:+.1%} a year (Sharpe {sr:.2f}) at {costs[0]:.1%} costs, "
            f"{mean:+.1%} a year versus the always-long book at the same risk (t {t:.2f}); {house}.")


def breakeven(df: pd.DataFrame) -> float:
    """Round-trip cost at which the trend book's mean net return is zero: gross / (turnover / 2)."""
    t = df["turnover"].mean()
    return float(2 * df["gross"].mean() / t) if t else float("nan")


def row_stats(df: pd.DataFrame, cols: list) -> list:
    out = []
    for name, col in cols:
        s = momentum.stats(df[col])
        out.append((name, s["ann"], s["vol"], s["sharpe"], sharpe_se(s["sharpe"], s["n"]), s["maxdd"], s["t"]))
    return out


def stat_table(df: pd.DataFrame, costs) -> list:
    cols = [("trend, gross", "gross")] + [(f"trend, net at {c:.2%} round trip", f"net_{c:g}") for c in costs]
    cols += [(f"always-long, net at {costs[0]:.2%}", "bench_ew"), ("60/40 SPY/IEF", "bench_6040")]
    lines = ["| series | ann. return | vol | Sharpe (+/- s.e.) | max drawdown | t-stat |", "|---|---|---|---|---|---|"]
    for n, a, v, s, se, d, t in row_stats(df, cols):
        lines.append(f"| {n} | {a:.1%} | {v:.1%} | {s:.2f} (+/- {se:.2f}) | {d:.0%} | {t:.2f} |")
    return lines


def yearly(df: pd.DataFrame, cost: float) -> list:
    d = df.copy()
    d["year"] = d["month"].str[:4]
    g = d.groupby("year").apply(lambda x: pd.Series({
        "trend": (1 + x[f"net_{cost:g}"]).prod() - 1, "always": (1 + x["bench_ew"]).prod() - 1,
        "sixty": (1 + x["bench_6040"]).prod() - 1}), include_groups=False)
    lines = ["| year | trend (net) | always-long | 60/40 |", "|---|---|---|---|"]
    for y, r in g.iterrows():
        lines.append(f"| {y} | {r['trend']:+.1%} | {r['always']:+.1%} | {r['sixty']:+.1%} |")
    return lines


def report(results: dict, chosen, costs, split: str, coverage: dict, missing: list) -> str:
    df = results[chosen]
    ins, oos = df[df["formed"] < split], df[df["formed"] >= split]
    side = {"ls": "long/short", "lo": "long-only (flat when the trend is down)"}[chosen[1]]
    lines = ["# Cross-asset trend following (ETFs, volatility targeted)", "", f"**Verdict:** {verdict(oos, costs)}", "",
             "Rule: each month-end, per asset, a trend signal from past prices only (12-month return sign, 10-month moving average, or a 1/3/12-month blend); "
             f"positions sized by inverse trailing volatility and the whole book scaled to {config.TREND_VOL_TARGET:.0%} ex-ante volatility "
             f"(leverage cap {config.TREND_LEVERAGE_CAP:g}x), held one month. {len(UNIVERSE)} liquid ETFs across equities, bonds, commodities and currencies. "
             "Costs: turnover x half the round trip. The comparison that matters is the always-long book with identical sizing: "
             "it says whether the trend filter adds anything beyond owning the assets.", "",
             f"Chosen in sample (best net Sharpe at {costs[0]:.2%}, formations before {split}): **{chosen[0]} signal, {side}**.", "",
             "## All variants (net Sharpe at each cost; excess = trend minus always-long, annualised)", "",
             "| variant | sample | Sharpe, realistic cost | Sharpe, house cost | excess vs always-long (t) | monthly turnover |", "|---|---|---|---|---|---|"]
    for key, d in results.items():
        for label, part in (("in", d[d["formed"] < split]), ("out of", d[d["formed"] >= split])):
            ex = part[f"net_{costs[0]:g}"] - part["bench_ew"]
            lines.append(f"| {key[0]}, {key[1]} | {label} sample | {momentum.stats(part[f'net_{costs[0]:g}'])['sharpe']:.2f} | "
                         f"{momentum.stats(part[f'net_{costs[-1]:g}'])['sharpe']:.2f} | {ex.mean() * 12:+.1%} ({tstat(ex):.2f}) | {part['turnover'].mean():.0%} |")
    for name, part in (("In sample", ins), ("Out of sample", oos)):
        lines += ["", f"## {name}: {part['month'].iloc[0]} to {part['month'].iloc[-1]} ({len(part)} months)", ""] + stat_table(part, costs)
        lines.append(f"\nBreak-even round-trip cost (where the net return reaches zero): {breakeven(part):.2%}.")
        lines.append(f"Average gross leverage {part['gross_leverage'].mean():.2f}x, average net long share {part['net_long_share'].mean():+.0%}.")
    lines += ["", "## Out-of-sample years (chosen variant)", ""] + yearly(oos, costs[0])
    lines += ["", "## Data, biases and caveats", "",
              "- ETFs priced: " + ", ".join(f"{k} ({v})" for k, v in coverage.items()) + (f"; no data for {', '.join(missing)}" if missing else "") + ".",
              f"- Sample is short for a trend study: about {len(df)} months from {df['month'].iloc[0]}. Classic results cover 1985 onwards with futures; the 2010s were a hard decade for trend (bond and equity whipsaws), so a low Sharpe here is partly the decade. Sharpe standard errors above show how little {len(oos)} months can say.",
              "- Variant selection used in-sample months only, but with 6 variants and heavily overlapping signals the in-sample winner is mildly optimistic; all variants are shown, including out of sample, for transparency.",
              "- ETFs only: no futures, so no direct short exposure beyond shorting the ETF (borrow and CFD financing not modelled; cash earns 0, so long-only and leveraged results ignore interest and leverage financing).",
              "- Commodity ETFs (USO, DBC, DBA) lose to contango; that is in the prices, and it is why a long-only commodity sleeve looks poor.",
              "- Survivorship: all chosen ETFs still exist; liquid dead ETFs are rare in this set, so the bias is small but not zero.",
              f"- Realistic ETF costs are well under 0.1% round trip; the house {costs[-1]:.1%} figure is deliberately punitive for monthly rebalancing of a book with average turnover {df['turnover'].mean():.0%} of equity a month.",
              "", f"Monthly series: `{MONTHLY_CSV}`."]
    return "\n".join(lines) + "\n"


def fetch_panel(symbols) -> pd.DataFrame:
    from concurrent.futures import ThreadPoolExecutor
    from edge import prices
    with ThreadPoolExecutor(3) as ex:
        got = dict(ex.map(lambda t: (t, prices.fetch_bars(t, config.YAHOO_DAILY_MAX_URL)["close"]), sorted(symbols)))
    missing = sorted(t for t, s in got.items() if s.empty)
    print(f"trend: no data for {missing}")
    return pd.DataFrame({t: s for t, s in got.items() if not s.empty}).sort_index()


def main() -> None:
    costs, split, first = config.TREND_COSTS, config.TREND_SPLIT, config.TREND_FIRST_FORMATION
    daily = fetch_panel(set(UNIVERSE) | {"SPY", "IEF"})
    print(f"trend: {daily.shape[1]} symbols priced, {daily.index[0].date()} to {daily.index[-1].date()}")
    results = {v: run_variant(daily, v[0], v[1], costs, first) for v in VARIANTS}
    results = {k: d for k, d in results.items() if not d.empty}
    chosen = pick(results, split, costs[0])
    coverage = {t: str(daily[t].first_valid_index().date()) for t in UNIVERSE if t in daily}
    missing = [t for t in UNIVERSE if t not in daily]
    MONTHLY_CSV.parent.mkdir(exist_ok=True)
    results[chosen].to_csv(MONTHLY_CSV, index=False)
    md = report(results, chosen, costs, split, coverage, missing)
    REPORT.write_text(md)
    print(md)
