"""Backtest of short-term mean reversion ("buy the dip") on S&P 500 members.

Each trading day t, after the close, we rank the stocks that were S&P 500 members *on that day* by
their return over the last k trading days (close t-k to close t). We buy the worst slice (the
biggest losers) equal-weight at the next day's open and sell at the open h trading days later.
A new cohort is formed every day and h cohorts are live at once, each with 1/h of the money.
An optional trend filter only buys dips in stocks trading above their 200-day average.

Returns are open to open, from Yahoo prices adjusted for splits and dividends (the open is scaled
by the same factor as the close). Entering at the next open, not at the signal close, matters
for this strategy: buying at the very close that defines the dip books the bid-ask bounce as profit.

Costs: daily turnover is sum(|w_today - w_yesterday|), charged at half the round-trip cost per unit.

Out-of-sample: the variants (lookback x hold x trend filter) are compared on days before
config.REVERSAL_SPLIT only; the in-sample winner is then reported on later days it never saw.
Daily returns are compounded to months for the statistics, so t-stats are not inflated by
day-to-day overlap between cohorts.

Known biases, repeated in the report:
- Survivorship: membership is point-in-time, but Yahoo has no prices for many delisted or renamed
  members, so those drop out of the ranking. Coverage per day is reported.
- Recycled tickers and bad prints: daily returns above config.REVERSAL_MAX_DAILY_RET are dropped.
- Equal weight rebalanced daily, for the strategy and the benchmark alike.
"""
import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import config
from edge import momentum as mo
from edge import prices

REPORT = Path("reports/reversal_backtest.md")
DAILY_CSV = Path("reports/reversal_daily.csv")
# (lookback trading days, hold trading days, trend filter on)
VARIANTS = [(k, h, f) for k in (3, 5) for h in (5, 10) for f in (False, True)]
MIN_ELIGIBLE = 50


# ---------- data ----------

def parse_chart(payload: dict) -> pd.DataFrame:
    """Yahoo chart JSON -> daily frame with adjusted open and close. Open is scaled by adjclose/close."""
    res = payload["chart"]["result"][0]
    quote = res["indicators"]["quote"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
    raw_close = pd.Series(quote["close"], index=idx, dtype=float)
    raw_open = pd.Series(quote["open"], index=idx, dtype=float)
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose")
    adj_close = pd.Series(adj, index=idx, dtype=float) if adj else raw_close
    factor = adj_close / raw_close
    df = pd.DataFrame({"open": raw_open * factor, "close": adj_close})
    df = df[(df["close"] > 0) & (df["open"] > 0)].dropna()
    return df[~df.index.duplicated(keep="last")].sort_index()


def fetch_daily(symbol: str) -> pd.DataFrame:
    """Full daily history for one symbol; empty frame on any failure, never raises."""
    empty = pd.DataFrame(columns=["open", "close"], dtype=float)
    url = config.YAHOO_DAILY_MAX_URL.format(symbol=symbol)
    for attempt in range(4):
        try:
            resp = requests.get(url, headers={"User-Agent": config.YAHOO_USER_AGENT}, timeout=30)
            if resp.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            if resp.status_code != 200:
                return empty
            return parse_chart(resp.json())
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
            return empty
    return empty


def fetch_panels(tickers, fetch=None, workers: int = 3, retry_pause: float = 30.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(opens, closes): day x ticker panels from a common calendar. Empty tickers get one more try."""
    fetch = fetch or fetch_daily
    todo, frames = sorted(set(tickers)), {}

    def one(t):
        return t, fetch(prices.yahoo_symbol(t, "us"))

    for attempt in range(2):
        with ThreadPoolExecutor(workers) as ex:
            got = dict(ex.map(one, todo))
        frames.update({t: f for t, f in got.items() if not f.empty})
        todo = [t for t in todo if t not in frames]
        print(f"reversal: pass {attempt + 1}: {len(frames)} priced, {len(todo)} empty")
        if not todo or attempt == 1:
            break
        time.sleep(retry_pause)
    first = pd.Timestamp(config.REVERSAL_FIRST_DAY) - pd.Timedelta(days=400)  # room for the 200-day average
    opens = pd.DataFrame({t: f["open"] for t, f in frames.items()}).sort_index()
    closes = pd.DataFrame({t: f["close"] for t, f in frames.items()}).sort_index()
    return opens[opens.index >= first], closes[closes.index >= first]


def member_mask(membership: pd.Series, days: pd.DatetimeIndex, tickers) -> pd.DataFrame:
    """Boolean day x ticker frame: True when the ticker was a member on that day (last list on or before it)."""
    cols = list(tickers)
    rows = pd.DataFrame([[t in s for t in cols] for s in membership], index=membership.index, columns=cols)
    return rows.reindex(rows.index.union(days)).ffill().reindex(days).fillna(False).astype(bool)


# ---------- backtest ----------

def open_returns(opens: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """r[d] = open(d+1) / open(d) - 1: what a position held from open d to open d+1 earns.
    Implausible values (bad data, recycled tickers) are set to NaN and counted."""
    r = opens.shift(-1) / opens - 1
    bad = (r > config.REVERSAL_MAX_DAILY_RET) | (r <= -1)
    return r.mask(bad), int(bad.sum().sum())


def cohort_weights(closes: pd.DataFrame, rets: pd.DataFrame, members: pd.DataFrame,
                   lookback: int, trend: bool, bottom: float) -> tuple[pd.DataFrame, pd.Series]:
    """Weights of the cohort formed at the close of each day (row), and the eligible count per day.
    Eligible: a member today with a k-day return and a price on the next trading day."""
    past = closes / closes.shift(lookback) - 1
    ok = members & past.notna() & closes.shift(-1).notna()
    if trend:
        ok &= closes > closes.rolling(200, min_periods=200).mean()
    # recycled-ticker guard: a k-day move beyond the bad-data cap is not a dip, it is a broken series
    ok &= past.abs() <= config.REVERSAL_MAX_DAILY_RET
    sig = past.where(ok)
    n_ok = sig.notna().sum(axis=1)
    rank = sig.rank(axis=1, method="first")
    n_pick = np.maximum(1, np.round(n_ok * bottom)).astype(int)
    pick = rank.le(n_pick, axis=0) & n_ok.ge(MIN_ELIGIBLE).values[:, None]
    w = pick.astype(float).div(pick.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return w, n_ok


def run_strategy(closes: pd.DataFrame, rets: pd.DataFrame, members: pd.DataFrame, lookback: int, hold: int,
                 trend: bool, costs, first: str, bottom: float = 0.1) -> pd.DataFrame:
    """Daily rows (labelled by the day whose open-to-open return is earned) with gross, net per cost,
    equal-weight member benchmark, turnover, holdings and eligible count."""
    w, n_ok = cohort_weights(closes, rets, members, lookback, trend, bottom)
    # a cohort formed at close t holds from open t+1 to open t+1+hold: it earns r[t+1] .. r[t+hold]
    book = w.rolling(hold, min_periods=1).sum().shift(1) / hold
    held = book.where(rets.notna(), 0.0).fillna(0.0)
    wsum = held.sum(axis=1)
    gross = (held * rets.fillna(0.0)).sum(axis=1) / wsum.replace(0, np.nan)  # missing prices dropped, book reweighted
    turnover = book.fillna(0.0).diff().abs().sum(axis=1)
    bench_members = members.shift(1).fillna(False).astype(bool)  # members known when the day's positions were set
    bench = rets.where(bench_members).mean(axis=1)
    df = pd.DataFrame({"gross": gross, "bench_ew": bench, "turnover": turnover,
                       "holdings": (held > 0).sum(axis=1), "eligible": n_ok.shift(1),
                       "members": members.sum(axis=1).shift(1)})
    df = df[(df.index >= pd.Timestamp(first)) & df["gross"].notna() & df["bench_ew"].notna()]
    for c in costs:
        df[f"net_{c:g}"] = df["gross"] - df["turnover"] * c / 2
    df.index.name = "day"
    return df


def to_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Compound daily return columns into calendar months; turnover is summed."""
    cols = [c for c in df.columns if c == "gross" or c == "bench_ew" or c.startswith("net_")]
    g = df[cols].groupby(df.index.to_period("M"))
    out = g.apply(lambda x: (1 + x).prod() - 1)
    out["turnover"] = df["turnover"].groupby(df.index.to_period("M")).sum()
    out["month"] = out.index.astype(str)
    return out.reset_index(drop=True)


def pick_variant(results: dict, split: str, cost: float) -> tuple:
    """In-sample choice: highest monthly net Sharpe at the given cost on days before the split."""
    best, best_s = None, -np.inf
    for key, df in results.items():
        m = to_monthly(df[df.index < pd.Timestamp(split)])
        s = mo.stats(m[f"net_{cost:g}"])["sharpe"]
        if pd.notna(s) and s > best_s:
            best, best_s = key, s
    return best


# ---------- report ----------

def _name(key) -> str:
    k, h, f = key
    return f"{k}-day dip, hold {h}d" + (", above 200d avg" if f else "")


def verdict(oos_m: pd.DataFrame, costs) -> str:
    """Edge = out-of-sample net excess over the EW universe that is positive with t >= 2 at the realistic cost."""
    real = f"net_{costs[0]:g}"
    x = oos_m[real] - oos_m["bench_ew"]
    t = mo.stats(x)["t"]
    house = "; ".join(f"at {c:.0%} round trip {(oos_m[f'net_{c:g}'] - oos_m['bench_ew']).mean() * 12:+.0%} a year" for c in costs[1:])
    if x.mean() > 0 and t >= 2:
        return f"EDGE: out of sample the dip buyers beat the equal-weight universe by {x.mean() * 12:+.1%} a year (t {t:.2f}) at {costs[0]:.1%} costs ({house})."
    return (f"NO EDGE: out of sample the excess over the equal-weight universe is {x.mean() * 12:+.1%} a year (t {t:.2f}) "
            f"at {costs[0]:.1%} costs, not reliably above zero ({house}).")


def report(results: dict, chosen: tuple, costs, split: str, bad: int, n_tickers: int, n_priced: int) -> str:
    df = results[chosen]
    cut = pd.Timestamp(split)
    ins, oos = to_monthly(df[df.index < cut]), to_monthly(df[df.index >= cut])
    oos_gross_x = oos["gross"] - oos["bench_ew"]
    cov = (df["eligible"] / df["members"]).describe()
    lines = ["# Short-term mean reversion on S&P 500 members", "",
             f"**Verdict:** {verdict(oos, costs)}", "",
             "Rule: after each close, rank point-in-time S&P 500 members by their return over the last k trading days, "
             "buy the worst 10% equal-weight at the next open, sell at the open h trading days later; a new cohort every day, "
             "h cohorts live. Optional filter: only stocks above their 200-day average. Yahoo prices adjusted for splits and "
             "dividends. Benchmark: equal weight over all priced members (isolates the stock selection from the market). "
             "Costs: daily turnover x half the round trip. Statistics on monthly compounded returns.", "",
             f"Chosen in sample (best net Sharpe at {costs[0]:.1%}, days before {split}): **{_name(chosen)}**.", "",
             "## In-sample variant comparison (days before the split)", "",
             "| variant | gross CAGR | gross excess vs EW (ann.) | net CAGR at realistic cost | net Sharpe | daily turnover |",
             "|---|---|---|---|---|---|"]
    for key, d in results.items():
        i = d[d.index < cut]
        m = to_monthly(i)
        g, n = mo.stats(m["gross"]), mo.stats(m[f"net_{costs[0]:g}"])
        gx = (m["gross"] - m["bench_ew"]).mean() * 12
        lines.append(f"| {_name(key)} | {g['ann']:.1%} | {gx:+.1%} | {n['ann']:.1%} | {n['sharpe']:.2f} | {i['turnover'].mean():.0%} |")
    for name, part, raw in (("In sample", ins, df[df.index < cut]), ("Out of sample", oos, df[df.index >= cut])):
        lines += ["", f"## {name}: {raw.index[0]:%Y-%m-%d} to {raw.index[-1]:%Y-%m-%d} ({len(part)} months)", ""]
        lines += mo._fmt_table(mo.summary(part, costs))
    yearly = oos.assign(year=oos["month"].str[:4]).groupby("year")
    lines += ["", "## Out of sample by year (excess over the EW universe)", "",
              f"| year | gross | net at {costs[0]:.1%} |", "|---|---|---|"]
    for y, g in yearly:
        gx = (1 + g["gross"]).prod() - (1 + g["bench_ew"]).prod()
        nx = (1 + g[f"net_{costs[0]:g}"]).prod() - (1 + g["bench_ew"]).prod()
        lines.append(f"| {y} | {gx:+.1%} | {nx:+.1%} |")
    be = oos_gross_x.mean() / (oos["turnover"].mean() / 2) if oos["turnover"].mean() else np.nan
    lines += ["", "## Data and biases", "",
              f"- Out of sample the gross excess (before any costs) is {oos_gross_x.mean() * 12:+.1%} a year; the round-trip cost that "
              f"would wipe it out is about {be:.2%}" + (" (negative: the rule loses money even for free)." if be < 0 else "."),
              f"- {n_tickers} tickers were ever members; {n_priced} have Yahoo history. Eligible share of members per day: "
              f"median {cov['50%']:.0%}, min {cov['min']:.0%}. Missing names are mostly delisted or acquired companies (survivorship bias: "
              "the dips that ended in delisting are under-represented, which flatters dip buying).",
              f"- {bad} stock-day open-to-open returns above +{config.REVERSAL_MAX_DAILY_RET:.0%} (or at -100%) were dropped as bad data.",
              "- Held names with no next price are dropped and the book reweighted, so delisting losses are missed.",
              f"- Average daily turnover of the chosen variant: {df['turnover'].mean():.0%} (sum of absolute weight changes).",
              f"- The {costs[0]:.1%} round trip is realistic for S&P 500 names with a commission-free broker; "
              f"{', '.join(f'{c:.0%}' for c in costs[1:])} are the project's small-cap house assumptions, shown as a stress test.",
              "", f"Daily series: `{DAILY_CSV}`."]
    return "\n".join(lines) + "\n"


def main() -> None:
    costs, split, first = config.REVERSAL_COSTS, config.REVERSAL_SPLIT, config.REVERSAL_FIRST_DAY
    membership = mo.load_membership(requests.get(config.SP500_MEMBERSHIP_URL, timeout=60).text)
    tickers = set().union(*membership.tolist())
    print(f"reversal: {len(tickers)} tickers ever in the S&P 500; fetching daily prices")
    opens, closes = fetch_panels(tickers)
    print(f"reversal: {closes.shape[1]} tickers priced, {closes.index.min():%Y-%m-%d} to {closes.index.max():%Y-%m-%d}")
    rets, bad = open_returns(opens)
    members = member_mask(membership, closes.index, closes.columns)
    results = {}
    for v in VARIANTS:
        results[v] = run_strategy(closes, rets, members, v[0], v[1], v[2], costs, first)
        print(f"reversal: {_name(v)} done, {len(results[v])} days")
    chosen = pick_variant(results, split, costs[0])
    REPORT.parent.mkdir(exist_ok=True)
    results[chosen].round(6).to_csv(DAILY_CSV)
    md = report(results, chosen, costs, split, bad, len(tickers), closes.shape[1])
    REPORT.write_text(md)
    print(md)
