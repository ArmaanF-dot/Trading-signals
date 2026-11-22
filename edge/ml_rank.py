"""Can a machine-learning ranker combine weak signals into one that beats the market after costs?

Universe: point-in-time S&P 500 members (liquid US), daily Yahoo adjusted closes and volumes.
Each month-end m we compute 13 price/volume features per stock, all from data up to the day
*before* m's last close (a one-day gap so short-term reversal cannot feed on bid-ask bounce),
and rank them cross-sectionally (0..1 within the month). The label is the rank of the stock's
next-month return within the month.

Models (hyperparameters fixed in advance, never tuned):
- gbm: sklearn HistGradientBoostingRegressor, shallow and heavily regularised.
- ridge: linear regression on the same ranks, the simple baseline the GBM must beat.

Walk-forward: models are refitted every January from ML_FIRST_PREDICTION on an expanding window.
A model refitted in month T only sees formations up to T-1, whose next-month labels are known
by T's close, and predicts formations T..T+11. Nothing from the future enters a prediction
(tests corrupt future labels and check the predictions do not move).

Portfolio: buy the top slice of the predicted ranking equal-weight, hold with overlapping cohorts
(edge.momentum.run_picks). Four portfolio variants per model; the variant is picked on
2005-2012 walk-forward predictions and judged on 2013 onward, as in the momentum study.

Not included: value/quality (no free point-in-time fundamentals) and true earnings reactions
(EDGAR dates only from 2017 in this repo); jump_63, the biggest 3-day move of the last quarter,
stands in for the earnings reaction because most such moves are earnings days.
"""
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import config
from edge import momentum as mo
from edge import prices

REPORT = Path("reports/ml_rank_backtest.md")
MONTHLY_CSV = Path("reports/ml_rank_monthly.csv")
FEATURES = ["mom_12_1", "mom_6_1", "rev_1m", "rev_1w", "vol_1m", "vol_12m", "max_1m", "hi52",
            "beta_12m", "dollar_vol", "amihud", "vol_trend", "jump_63"]
PORTFOLIOS = [(0.1, 1), (0.1, 3), (0.2, 1), (0.2, 3)]  # (top fraction, holding months)
MODELS = ("gbm", "ridge")


# ---------- data ----------

def fetch_daily(tickers, fetch=None, workers: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Date x ticker panels of adjusted close and volume; tickers with no Yahoo data are absent."""
    fetch = fetch or (lambda sym: prices.fetch_bars(sym, config.YAHOO_DAILY_MAX_URL))
    todo, bars = sorted(set(tickers)), {}
    for attempt in range(2):
        with ThreadPoolExecutor(workers) as ex:
            got = dict(ex.map(lambda t: (t, fetch(prices.yahoo_symbol(t, "us"))), todo))
        bars.update({t: b for t, b in got.items() if not b.empty})
        todo = [t for t in todo if t not in bars]
        print(f"ml_rank: pass {attempt + 1}: {len(bars)} priced, {len(todo)} empty")
        if not todo:
            break
    close = pd.DataFrame({t: b["close"] for t, b in bars.items()}).sort_index()
    volume = pd.DataFrame({t: b["volume"] for t, b in bars.items()}).reindex(close.index)
    keep = close.notna().sum(axis=1) >= max(5, 0.05 * close.shape[1])  # drop odd dates only a few tickers trade
    return close[keep], volume[keep]


# ---------- features ----------

def month_end_dates(index: pd.DatetimeIndex) -> pd.Series:
    """Last trading date of each calendar month, indexed by month Period."""
    s = pd.Series(index, index=index.to_period("M"))
    return s.groupby(level=0).max()


def _jump(r3: np.ndarray, end: int, window: int) -> np.ndarray:
    """Signed value of the largest absolute entry in rows end-window+1..end, per column (NaN if none)."""
    w = r3[max(0, end - window + 1):end + 1]
    a = np.where(np.isnan(w), -1.0, np.abs(w))
    idx = a.argmax(axis=0)
    out = w[idx, np.arange(w.shape[1])]
    out[a.max(axis=0) < 0] = np.nan
    return out


def daily_features(close: pd.DataFrame, volume: pd.DataFrame) -> dict:
    """{feature: month x ticker frame}. Values for month m use data up to the trading day before m's last close."""
    r = close.pct_change(fill_method=None)
    r = r.mask((r > 1) | (r <= -1))  # a daily move above +100% is almost always bad data
    mkt = r.mean(axis=1)
    dv = close * volume
    roll = lambda x, n, mp: x.rolling(n, min_periods=mp)
    m_mean, m_var = roll(mkt, 252, 200).mean(), roll(mkt, 252, 200).var()
    cov = roll(r.mul(mkt, axis=0), 252, 200).mean() - roll(r, 252, 200).mean().mul(m_mean, axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        feats = {
            "mom_12_1": close.shift(21) / close.shift(252) - 1,
            "mom_6_1": close.shift(21) / close.shift(126) - 1,
            "rev_1m": close / close.shift(21) - 1,
            "rev_1w": close / close.shift(5) - 1,
            "vol_1m": roll(r, 21, 15).std(),
            "vol_12m": roll(r, 252, 200).std(),
            "max_1m": roll(r, 21, 15).max(),
            "hi52": close / roll(close, 252, 200).max(),
            "beta_12m": cov.div(m_var, axis=0),  # scale is irrelevant: only within-month ranks are used
            "dollar_vol": np.log(roll(dv, 21, 15).mean().where(lambda x: x > 0)),
            "amihud": np.log((r.abs() / dv.where(dv > 0)).rolling(21, min_periods=15).mean() + 1e-15),
            "vol_trend": roll(volume, 21, 15).mean() / roll(volume, 252, 200).mean(),
        }
    me = month_end_dates(close.index)
    pos = close.index.get_indexer(me.values) - 1  # the day before the month's last close
    ok = pos >= 0
    months, pos = me.index[ok], pos[ok]
    out = {k: pd.DataFrame(v.to_numpy()[pos], index=months, columns=close.columns) for k, v in feats.items()}
    r3 = (close / close.shift(3) - 1).to_numpy()
    out["jump_63"] = pd.DataFrame(np.vstack([_jump(r3, p, 63) for p in pos]), index=months, columns=close.columns)
    return {k: out[k] for k in FEATURES}


def monthly_from_daily(close: pd.DataFrame) -> pd.DataFrame:
    """Close on each month's last trading day (carried up to 5 days for a halted name)."""
    me = month_end_dates(close.index)
    m = close.ffill(limit=5).loc[me.values]
    m.index = me.index
    return m


def build_dataset(feats: dict, monthly: pd.DataFrame, members: dict, first: str) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Long table (month, ticker, ranked features, raw fwd return, ranked label) for eligible member-months,
    plus the cleaned monthly returns and how many bad stock-months were dropped."""
    rets, bad = mo.clean_returns(monthly)
    fwd = rets.shift(-1)
    rows = []
    for m in monthly.index[monthly.index >= pd.Period(first, "M")]:
        if m not in members:
            continue
        cols = [t for t in members[m] if t in monthly.columns]
        f = pd.DataFrame({k: feats[k].loc[m, cols] for k in FEATURES}) if m in feats["mom_12_1"].index else None
        if f is None:
            continue
        f = f[monthly.loc[m, cols].notna() & f["mom_12_1"].notna() & f["vol_1m"].notna()]
        if len(f) < 50:
            continue
        f = f.rank(pct=True)
        f["month"], f["ticker"], f["fwd"] = m, f.index, fwd.loc[m, f.index].to_numpy()
        f["label"] = f["fwd"].rank(pct=True) - 0.5
        f["members"] = len(members[m])
        rows.append(f.reset_index(drop=True))
    return pd.concat(rows, ignore_index=True), rets, bad


# ---------- models and walk-forward ----------

def make_model(kind: str):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    if kind == "gbm":
        return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=500,
                                             l2_regularization=1.0, early_stopping=False, random_state=0)
    return Ridge(alpha=1.0)


def _x(df: pd.DataFrame, kind: str) -> np.ndarray:
    x = df[FEATURES].to_numpy(dtype=float)
    return x if kind == "gbm" else np.nan_to_num(x, nan=0.5)  # ridge needs no gaps: a missing rank is the median


def walk_forward(data: pd.DataFrame, kind: str, first_pred: str, refit_months: int = 12) -> tuple[pd.Series, object]:
    """Out-of-sample score per row (NaN before first_pred) and the last fitted model.
    A model fitted at month T trains on formations <= T-1 with a known label and scores T..T+refit-1."""
    months = sorted(data["month"].unique())
    start = pd.Period(first_pred, "M")
    pred = pd.Series(np.nan, index=data.index)
    model, refit = None, [m for m in months if m >= start][::refit_months]
    for i, t in enumerate(refit):
        train = data[(data["month"] <= t - 1) & data["label"].notna()]
        end = refit[i + 1] if i + 1 < len(refit) else months[-1] + 1
        test = data[(data["month"] >= t) & (data["month"] < end)]
        if len(train) < 1000 or test.empty:
            continue
        model = make_model(kind).fit(_x(train, kind), train["label"].to_numpy())
        pred.loc[test.index] = model.predict(_x(test, kind))
    return pred, model


def picks_from_scores(data: pd.DataFrame, score: pd.Series, top: float) -> tuple[dict, dict]:
    """{month: equal weights of the top-scored names} and {month: (eligible, members)}, like momentum.cohorts."""
    picks, sizes = {}, {}
    d = data.assign(score=score).dropna(subset=["score"])
    for m, g in d.groupby("month"):
        sizes[m] = (len(g), int(g["members"].iloc[0]))
        n = max(1, int(round(len(g) * top)))
        winners = g.nlargest(n, "score")["ticker"]
        picks[m] = pd.Series(1.0 / n, index=winners.to_numpy())
    return picks, sizes


def monthly_ic(data: pd.DataFrame, score: pd.Series) -> pd.DataFrame:
    """Per month: Spearman rank IC of score vs next-month return, and the gross top-minus-bottom decile spread."""
    d = data.assign(score=score).dropna(subset=["score", "fwd"])
    out = []
    for m, g in d.groupby("month"):
        if len(g) < 50:
            continue
        ic = g["score"].rank().corr(g["fwd"].rank())
        q = g["score"].rank(pct=True)
        out.append({"formed": str(m), "ic": ic, "spread": g.loc[q > 0.9, "fwd"].mean() - g.loc[q <= 0.1, "fwd"].mean()})
    return pd.DataFrame(out)


def feature_ics(data: pd.DataFrame, since: str) -> pd.DataFrame:
    """Mean monthly rank IC of each single feature (sign as given) from `since` on, with t-stats."""
    d = data[data["month"] >= pd.Period(since, "M")]
    rows = []
    for f in FEATURES:
        ics = monthly_ic(d, d[f])["ic"]
        rows.append({"feature": f, "ic": ics.mean(), "t": ics.mean() / (ics.std(ddof=1) / math.sqrt(len(ics)))})
    return pd.DataFrame(rows)


# ---------- report ----------

def _ic_line(ic: pd.DataFrame) -> str:
    t = ic["ic"].mean() / (ic["ic"].std(ddof=1) / math.sqrt(len(ic)))
    st = ic["spread"].mean() / (ic["spread"].std(ddof=1) / math.sqrt(len(ic)))
    return f"{ic['ic'].mean():+.3f} | {t:.2f} | {ic['spread'].mean() * 12:+.1%} | {st:.2f}"


def verdict(oos: pd.DataFrame, costs, name: str) -> str:
    real = f"net_{costs[0]:g}"
    x = oos[real] - oos["bench_ew"]
    t = mo.stats(x)["t"]
    house = "; ".join(f"at {c:.0%} round trip {(oos[f'net_{c:g}'] - oos['bench_ew']).mean() * 12:+.1%} a year" for c in costs[1:])
    if x.mean() > 0 and t >= 2:
        return f"EDGE: out of sample ({name}) the picks beat the equal-weight universe by {x.mean() * 12:+.1%} a year (t {t:.2f}) at {costs[0]:.1%} costs ({house})."
    return f"NO EDGE: out of sample ({name}) the excess over the equal-weight universe is {x.mean() * 12:+.1%} a year (t {t:.2f}) at {costs[0]:.1%} costs, not reliably above zero ({house})."


def _label(key) -> str:
    return f"{key[0]}, top {key[1]:.0%}, hold {key[2]}"


def report(results: dict, ics: dict, chosen: tuple, costs, split: str, fic: pd.DataFrame, coefs: dict, info: dict) -> str:
    df = results[chosen]
    ins, oos = df[df["formed"] < split], df[df["formed"] >= split]
    lines = ["# Machine-learning ranking of weak signals (S&P 500 members)", "",
             f"**Verdict:** {verdict(oos, costs, _label(chosen))}", "",
             "Method: each month-end, 13 price/volume features per point-in-time S&P 500 member (computed to the day before the "
             "month's last close), ranked within the month. A gradient-boosted tree model and a ridge baseline learn the rank of "
             "next-month return. Walk-forward: refitted each January on an expanding window of past months only; hyperparameters "
             "fixed in advance. Buy the top slice equal-weight at the month-end close, overlapping cohorts. Benchmark: equal weight "
             "over all priced members. Costs: turnover x half the round trip.", "",
             f"Features: {', '.join(FEATURES)}.", "",
             f"Chosen on {info['first_pred']} to {split} walk-forward predictions (best net Sharpe at {costs[0]:.1%}): **{_label(chosen)}**.", "",
             "## Does the model rank stocks at all? (monthly rank IC, all names)", "",
             "| model | period | mean IC | IC t-stat | top-bottom decile spread (ann., gross) | spread t |", "|---|---|---|---|---|---|"]
    for kind, ic in ics.items():
        for name, part in (("selection", ic[ic["formed"] < split]), ("test", ic[ic["formed"] >= split])):
            lines.append(f"| {kind} | {name} | {_ic_line(part)} |")
    lines += ["", "## Variant comparison (selection period)", "",
              "| variant | gross CAGR | net CAGR at realistic cost | net Sharpe | monthly turnover |", "|---|---|---|---|---|"]
    for key, d in results.items():
        i = d[d["formed"] < split]
        g, n = mo.stats(i["gross"]), mo.stats(i[f"net_{costs[0]:g}"])
        lines.append(f"| {_label(key)} | {g['ann']:.1%} | {n['ann']:.1%} | {n['sharpe']:.2f} | {i['turnover'].mean():.0%} |")
    for name, part in (("Selection period", ins), ("Held-out test", oos)):
        lines += ["", f"## {name}: {part['month'].iloc[0]} to {part['month'].iloc[-1]} ({len(part)} months), {_label(chosen)}", ""]
        lines += mo._fmt_table(mo.summary(part, costs))
    lines += ["", "## Every variant on the held-out test (excess over EW universe, ann.)", "",
              "| variant | gross | net at " + " | net at ".join(f"{c:.1%}" for c in costs) + " | t at realistic cost |",
              "|---|---|" + "---|" * len(costs) + "---|"]
    for key, d in results.items():
        o = d[d["formed"] >= split]
        ex = lambda col: (o[col] - o["bench_ew"]).mean() * 12
        t = mo.stats(o[f"net_{costs[0]:g}"] - o["bench_ew"])["t"]
        lines.append(f"| {_label(key)} | {ex('gross'):+.1%} | " + " | ".join(f"{ex(f'net_{c:g}'):+.1%}" for c in costs) + f" | {t:.2f} |")
    lines += ["", f"## Single features on the held-out test (mean monthly rank IC from {split})", "",
              "| feature | mean IC | t-stat | ridge weight (last fit) |", "|---|---|---|---|"]
    for r in fic.itertuples():
        lines.append(f"| {r.feature} | {r.ic:+.3f} | {r.t:.2f} | {coefs.get(r.feature, float('nan')):+.4f} |")
    lines += ["", "## Data and biases", "",
              f"- {info['n_tickers']} tickers were ever members; {info['n_priced']} have Yahoo daily history. "
              f"{info['rows']:,} stock-months in the dataset, median {info['per_month']:.0f} names a month "
              f"({info['coverage']:.0%} of members). Missing names are mostly delisted or acquired (survivorship bias, which flatters "
              "every variant and the benchmark alike).",
              f"- {info['bad']} stock-month returns above +{config.MOMENTUM_MAX_MONTHLY_RET:.0%} (or at -100%) were dropped as bad data.",
              "- Held names with no next-month price are dropped and the book reweighted, so delisting losses are missed.",
              "- Features stop the day before the trade close; trades fill at the month-end adjusted close.",
              "- No value, quality or true earnings-surprise features: there is no free point-in-time source for 2000 onwards.",
              f"- {len(results)} variants were compared (2 models x 4 portfolios) and one picked before the test period; the "
              "held-out table shows them all so the choice can be checked.",
              f"- The {costs[0]:.1%} round trip is realistic for S&P 500 names; {', '.join(f'{c:.0%}' for c in costs[1:])} are the "
              "project's house assumptions, shown as a stress test.",
              "", f"Monthly series of the chosen variant: `{MONTHLY_CSV}`."]
    return "\n".join(lines) + "\n"


def run_all(data: pd.DataFrame, rets: pd.DataFrame, members: dict, costs, first_pred: str, split: str):
    results, ics, coefs = {}, {}, {}
    for kind in MODELS:
        score, model = walk_forward(data, kind, first_pred)
        ics[kind] = monthly_ic(data, score)
        if kind == "ridge" and model is not None:
            coefs = dict(zip(FEATURES, model.coef_))
        for top, hold in PORTFOLIOS:
            picks, sizes = picks_from_scores(data, score, top)
            results[(kind, top, hold)] = mo.run_picks(picks, sizes, rets, members, hold, costs)
    chosen = mo.pick_variant(results, split, costs[0])
    return results, ics, coefs, chosen


def main() -> None:
    costs, split = config.ML_COSTS, str(pd.Period(config.ML_SPLIT, "M"))
    first_pred = str(pd.Period(config.ML_FIRST_PREDICTION, "M"))
    membership = mo.load_membership(requests.get(config.SP500_MEMBERSHIP_URL, timeout=60).text)
    tickers = set().union(*membership.tolist())
    print(f"ml_rank: {len(tickers)} tickers ever in the S&P 500; fetching daily prices")
    close, volume = fetch_daily(tickers)
    print(f"ml_rank: daily panel {close.shape}, {close.index.min().date()} to {close.index.max().date()}")
    monthly = monthly_from_daily(close).iloc[:-1]  # drop the current, unfinished month
    feats = daily_features(close, volume)
    members = mo.members_at_month_ends(membership, monthly.index)
    data, rets, bad = build_dataset(feats, monthly, members, config.ML_FIRST_FORMATION)
    print(f"ml_rank: {len(data):,} stock-months, {data['month'].nunique()} months")
    results, ics, coefs, chosen = run_all(data, rets, members, costs, first_pred, split)
    per = data.groupby("month").size()
    info = {"n_tickers": len(tickers), "n_priced": close.shape[1], "rows": len(data), "per_month": per.median(),
            "coverage": (per / data.groupby("month")["members"].first()).median(), "bad": bad, "first_pred": first_pred}
    REPORT.parent.mkdir(exist_ok=True)
    results[chosen].to_csv(MONTHLY_CSV, index=False)
    md = report(results, ics, chosen, costs, split, feature_ics(data, split), coefs, info)
    REPORT.write_text(md)
    print(md)
