"""Backtest of quality (profitability) and value (cheapness) tilts on S&P 500 members, from SEC XBRL.

Each month-end we rank the stocks that were S&P 500 members *on that date* by one of four signals,
built only from figures that had been filed with the SEC by that date (the `filed` stamp on every
XBRL fact, so restatements count only from when they were published):

- quality "gpa": gross profit / total assets for the latest fiscal year (Novy-Marx 2013).
- value "bm": book equity (latest balance sheet) / market cap. Negative book equity is excluded.
- value "ep": net income for the latest fiscal year / market cap.
- "qv": quality plus value, the average of the gpa and bm percentile ranks.

Market cap = shares outstanding from the latest filing cover page (all share classes summed),
restated to today's split basis with Yahoo's split history, times Yahoo's split-adjusted close.

We buy the top slice equal-weight and hold with overlapping cohorts (the momentum study's engine).
Benchmark: equal weight over every member that had the signal that month, so the comparison
isolates the ranking. Costs: turnover x half the round trip.

Out of sample: the 16 variants (4 signals x top 10%/20% x hold 3/12 months) are compared on
formations before config.QV_SPLIT only; the in-sample winner is then reported on later months.
XBRL financials start in 2009, so the test begins in 2010.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import config
from edge import http, momentum as mo, prices

REPORT = Path("reports/quality_value_backtest.md")
MONTHLY_CSV = Path("reports/quality_value_monthly.csv")
SIGNALS = ["gpa", "bm", "ep", "qv"]
SIGNAL_NAMES = {"gpa": "quality: gross profit / assets", "bm": "value: book / market",
                "ep": "value: earnings / price", "qv": "quality + value (gpa and bm ranks)"}
VARIANTS = [(s, top, hold) for s in SIGNALS for top in (0.1, 0.2) for hold in (3, 12)]

# concept -> [(taxonomy, tag)] in order of preference
CONCEPTS = {
    "assets": [("us-gaap", "Assets")],
    "equity": [("us-gaap", "StockholdersEquity"),
               ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")],
    "gross_profit": [("us-gaap", "GrossProfit")],
    "revenue": [("us-gaap", "Revenues"), ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
                ("us-gaap", "SalesRevenueNet"), ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax")],
    "cost_of_revenue": [("us-gaap", "CostOfRevenue"), ("us-gaap", "CostOfGoodsAndServicesSold"),
                        ("us-gaap", "CostOfGoodsSold")],
    "net_income": [("us-gaap", "NetIncomeLoss")],
    "shares": [("dei", "EntityCommonStockSharesOutstanding")],
}
FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "10-KT", "10-KT/A"}
FACT_COLS = ["concept", "prio", "start", "end", "val", "filed", "accn"]
DAY = np.timedelta64(1, "D")


# ---------- SEC facts ----------

def sec_json(url: str) -> dict:
    headers = {"User-Agent": config.sec_user_agent(), "Accept-Encoding": "gzip, deflate"}
    return http.get(url, headers=headers, min_interval=config.SEC_MIN_INTERVAL).json()


def norm_ticker(t: str) -> str:
    return str(t).strip().upper().replace(".", "-")


def ticker_to_cik(tickers_json: dict) -> dict:
    """{ticker: 10-digit CIK} from SEC's company_tickers_exchange.json (current tickers only)."""
    df = pd.DataFrame(tickers_json["data"], columns=tickers_json["fields"])
    return {norm_ticker(t): f"{int(c):010d}" for c, t in zip(df["cik"], df["ticker"])}


def tidy_facts(companyfacts: dict) -> pd.DataFrame:
    """The concepts we need from one company's XBRL companyfacts JSON, one row per reported value."""
    rows = []
    facts = companyfacts.get("facts", {})
    for concept, tags in CONCEPTS.items():
        for prio, (tax, tag) in enumerate(tags):
            units = facts.get(tax, {}).get(tag, {}).get("units", {})
            for f in units.get("shares" if concept == "shares" else "USD", []):
                if f.get("form") not in FORMS or f.get("val") is None:
                    continue
                rows.append((concept, prio, f.get("start"), f["end"], float(f["val"]), f["filed"], f.get("accn", "")))
    df = pd.DataFrame(rows, columns=FACT_COLS)
    for c in ("start", "end", "filed"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def derive_gross_profit(df: pd.DataFrame) -> pd.DataFrame:
    """Add revenue - cost of revenue as a lower-priority gross profit where both come from the same filing and period."""
    rev = df[df["concept"] == "revenue"].sort_values("prio").drop_duplicates(["accn", "start", "end"])
    cost = df[df["concept"] == "cost_of_revenue"].sort_values("prio").drop_duplicates(["accn", "start", "end"])
    m = rev.merge(cost, on=["accn", "start", "end"], suffixes=("", "_c"))
    if m.empty:
        return df
    gp = pd.DataFrame({"concept": "gross_profit", "prio": 10, "start": m["start"], "end": m["end"],
                       "val": m["val"] - m["val_c"], "filed": m[["filed", "filed_c"]].max(axis=1), "accn": m["accn"]})
    return pd.concat([df, gp], ignore_index=True)


class Facts:
    """Point-in-time lookups on one company's facts."""

    def __init__(self, df: pd.DataFrame):
        df = derive_gross_profit(df)
        self.by = {}
        for concept, g in df.groupby("concept"):
            dur = (g["end"] - g["start"]).dt.days
            if concept in ("gross_profit", "net_income"):
                g = g[dur.between(350, 380)]  # fiscal years only
            elif concept != "shares":
                g = g[g["start"].isna()]  # balance-sheet instants
            self.by[concept] = {"end": g["end"].values, "filed": g["filed"].values,
                                "prio": g["prio"].values, "val": g["val"].values, "accn": g["accn"].values}

    def latest(self, concept: str, d: np.datetime64, max_age_days: int, end=None):
        """Value for the latest period end filed before d, or at period `end` if given.
        Among values for that period: preferred tag first, then the most recent filing. (val, end) or (nan, None)."""
        a = self.by.get(concept)
        if a is None:
            return np.nan, None
        ok = a["filed"] < d
        if end is not None:
            ok &= a["end"] == end
        if not ok.any():
            return np.nan, None
        e = a["end"][ok].max()
        if (d - e) / DAY > max_age_days:
            return np.nan, None
        idx = np.flatnonzero(ok & (a["end"] == e))
        best = sorted(idx, key=lambda i: (a["prio"][i], -a["filed"][i].astype("int64")))[0]
        return float(a["val"][best]), e

    def shares(self, d: np.datetime64, max_age_days: int = 200):
        """Shares outstanding from the latest cover page filed before d, share classes summed. (shares, cover date)."""
        a = self.by.get("shares")
        if a is None:
            return np.nan, None
        ok = a["filed"] < d
        if not ok.any():
            return np.nan, None
        f = a["filed"][ok].max()
        if (d - f) / DAY > max_age_days:
            return np.nan, None
        pick = ok & (a["filed"] == f)
        acc = a["accn"][pick][0]
        pick &= a["accn"] == acc
        e = a["end"][pick].max()
        pick &= a["end"] == e
        return float(a["val"][pick].sum()), e


# ---------- prices ----------

def parse_chart(js: dict) -> tuple[pd.Series, pd.Series, list]:
    """Yahoo monthly chart JSON -> (adjusted close by month, split-adjusted close by month, [(date, ratio)])."""
    res = js["chart"]["result"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
    quote = res["indicators"]["quote"][0]
    close = pd.Series(quote["close"], index=idx, dtype=float)
    adj = pd.Series(res["indicators"].get("adjclose", [{}])[0].get("adjclose") or quote["close"], index=idx, dtype=float)
    splits = [(pd.to_datetime(s["date"], unit="s"), s["numerator"] / s["denominator"])
              for s in res.get("events", {}).get("splits", {}).values() if s.get("denominator")]

    def monthly(s):
        s = s.dropna()
        s.index = s.index.to_period("M")
        return s[~s.index.duplicated(keep="last")]
    return monthly(adj), monthly(close), sorted(splits)


def split_factor(splits: list, after: pd.Timestamp) -> float:
    """Shares counted before `after` times this = shares on today's split basis."""
    f = 1.0
    for d, r in splits:
        if d > after:
            f *= r
    return f


def fetch_prices(tickers, workers: int = 3, retry_pause: float = 30.0, get_json=None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    url = config.YAHOO_MONTHLY_MAX_URL + "&events=split"

    def default_get(sym):
        for attempt in range(3):
            try:
                r = requests.get(url.format(symbol=sym), headers={"User-Agent": config.YAHOO_USER_AGENT}, timeout=20)
                if r.status_code in (429, 500, 502, 503):
                    time.sleep(2 ** attempt)
                    continue
                return r.json() if r.status_code == 200 else None
            except (requests.RequestException, ValueError):
                return None
        return None
    get_json = get_json or default_get

    def one(t):
        js = get_json(prices.yahoo_symbol(t, "us"))
        try:
            return t, parse_chart(js) if js else None
        except (KeyError, IndexError, TypeError, ValueError):
            return t, None

    todo, got = sorted(set(tickers)), {}
    for attempt in range(2):
        with ThreadPoolExecutor(workers) as ex:
            for t, v in ex.map(one, todo):
                if v is not None and not v[0].empty:
                    got[t] = v
        todo = [t for t in todo if t not in got]
        print(f"quality-value: price pass {attempt + 1}: {len(got)} priced, {len(todo)} empty")
        if not todo or attempt == 1:
            break
        time.sleep(retry_pause)
    adj = pd.DataFrame({t: v[0] for t, v in got.items()}).sort_index()
    close = pd.DataFrame({t: v[1] for t, v in got.items()}).sort_index()
    return adj, close, {t: v[2] for t, v in got.items()}


# ---------- signals ----------

def signals_at(facts: Facts, d: np.datetime64, close: float, splits: list) -> dict:
    """gpa, bm, ep (and mcap) for one company as known at d; NaN where data are missing or stale."""
    out = {"gpa": np.nan, "bm": np.nan, "ep": np.nan, "mcap": np.nan}
    gp, e = facts.latest("gross_profit", d, config.QV_MAX_ANNUAL_AGE_DAYS)
    if e is not None:
        assets, _ = facts.latest("assets", d, config.QV_MAX_ANNUAL_AGE_DAYS, end=e)
        if assets > 0:
            out["gpa"] = gp / assets
    sh, cover = facts.shares(d)
    if not (sh > 0 and close > 0):
        return out
    mcap = sh * split_factor(splits, pd.Timestamp(cover)) * close
    if not config.QV_MIN_MCAP <= mcap <= config.QV_MAX_MCAP:
        return out
    out["mcap"] = mcap
    eq, _ = facts.latest("equity", d, config.QV_MAX_INSTANT_AGE_DAYS)
    if eq > 0:
        out["bm"] = eq / mcap
    ni, _ = facts.latest("net_income", d, config.QV_MAX_ANNUAL_AGE_DAYS)
    if pd.notna(ni):
        out["ep"] = ni / mcap
    return out


def signal_panel(facts: dict, close: pd.DataFrame, splits: dict, members: dict, months) -> dict:
    """{month: DataFrame indexed by ticker with gpa, bm, ep, qv, mcap} for members with a price and a CIK."""
    out = {}
    for m in months:
        d = np.datetime64(m.to_timestamp(how="end").normalize())
        rows = {}
        for t in members.get(m, ()):
            if t not in facts or t not in close.columns:
                continue
            p = close.at[m, t] if m in close.index else np.nan
            if pd.isna(p):
                continue
            rows[t] = signals_at(facts[t], d, float(p), splits.get(t, []))
        df = pd.DataFrame.from_dict(rows, orient="index", columns=["gpa", "bm", "ep", "mcap"])
        both = df[["gpa", "bm"]].dropna()
        df["qv"] = (both["gpa"].rank(pct=True) + both["bm"].rank(pct=True)) / 2
        out[m] = df
    return out


def picks_for(panel: dict, rets: pd.DataFrame, sig: str, top: float, min_n: int) -> tuple[dict, dict, dict]:
    """{month: equal weights of the top slice}, {month: (ranked, members)}, {month: ranked tickers}."""
    picks, sizes, uni = {}, {}, {}
    for m, df in panel.items():
        if m + 1 not in rets.index:
            continue
        ok = df[sig].dropna()
        sizes[m], uni[m] = (len(ok), len(df)), list(ok.index)
        if len(ok) < min_n:
            continue
        n = max(1, int(round(len(ok) * top)))
        best = ok.sort_values(ascending=False).index[:n]
        picks[m] = pd.Series(1.0 / n, index=best)
    return picks, sizes, uni


# ---------- report ----------

def verdict(oos: pd.DataFrame, costs) -> str:
    real = f"net_{costs[0]:g}"
    x = oos[real] - oos["bench_ew"]
    t = mo.stats(x)["t"]
    house = "; ".join(f"at {c:.0%} round trip {(oos[f'net_{c:g}'] - oos['bench_ew']).mean() * 12:+.1%} a year" for c in costs[1:])
    if x.mean() > 0 and t >= 2:
        return f"EDGE: out of sample the tilt beat the equal-weight universe by {x.mean() * 12:+.1%} a year (t {t:.2f}) at {costs[0]:.1%} costs ({house})."
    return (f"NO EDGE: out of sample the excess over the equal-weight universe is {x.mean() * 12:+.1%} a year (t {t:.2f}) "
            f"at {costs[0]:.1%} costs, not reliably above zero ({house}).")


def _label(v) -> str:
    return f"{v[0]}, top {v[1]:.0%}, hold {v[2]}"


def report(results: dict, chosen: tuple, costs, split: str, info: dict) -> str:
    real = f"net_{costs[0]:g}"
    df = results[chosen]
    ins, oos = df[df["formed"] < split], df[df["formed"] >= split]
    lines = ["# Quality and value tilts on S&P 500 members", "",
             f"**Verdict:** {verdict(oos, costs)}", "",
             "Rule: each month-end rank point-in-time S&P 500 members on a fundamental signal built only from SEC XBRL figures "
             "already filed by that date, buy the top slice equal-weight, hold with overlapping cohorts. Signals: "
             + "; ".join(f"`{k}` {v}" for k, v in SIGNAL_NAMES.items()) + ". Monthly Yahoo adjusted closes. Benchmark: equal "
             "weight over every member with that signal that month (isolates the ranking from the market). Costs: turnover x half the round trip.", "",
             f"Chosen in sample (best net Sharpe at {costs[0]:.1%}, formations before {split}): **{_label(chosen)}** ({SIGNAL_NAMES[chosen[0]]}).", "",
             "## In-sample variant comparison (formations before the split)", "",
             "| variant | gross CAGR | net CAGR | net Sharpe | excess vs EW (ann.) | t-stat | monthly turnover |",
             "|---|---|---|---|---|---|---|"]
    for key, d in results.items():
        i = d[d["formed"] < split]
        g, n, x = mo.stats(i["gross"]), mo.stats(i[real]), i[real] - i["bench_ew"]
        lines.append(f"| {_label(key)} | {g['ann']:.1%} | {n['ann']:.1%} | {n['sharpe']:.2f} | {x.mean() * 12:+.1%} | "
                     f"{mo.stats(x)['t']:.2f} | {i['turnover'].mean():.0%} |")
    for name, part in (("In sample", ins), ("Out of sample", oos)):
        lines += ["", f"## {name}, chosen variant: {part['month'].iloc[0]} to {part['month'].iloc[-1]} ({len(part)} months)", ""]
        lines += mo._fmt_table(mo.summary(part, costs))
    lines += ["", "## Every variant out of sample (for context only; the verdict uses the in-sample choice)", "",
              "| variant | net CAGR | excess vs EW (ann.) | t-stat |", "|---|---|---|---|"]
    for key, d in results.items():
        o = d[d["formed"] >= split]
        x = o[real] - o["bench_ew"]
        lines.append(f"| {_label(key)} | {mo.stats(o[real])['ann']:.1%} | {x.mean() * 12:+.1%} | {mo.stats(x)['t']:.2f} |")
    cov = (df["eligible"] / df["members"]).describe()
    lines += ["", "## Data and biases", "",
              f"- {info['n_tickers']} tickers were ever members after {config.QV_FIRST_FORMATION}; {info['n_cik']} map to a current SEC CIK and "
              f"{info['n_priced']} of those have Yahoo history. Companies that were delisted, acquired or renamed have no current CIK, so they "
              "are missing (survivorship bias, as in the momentum study).",
              f"- Members per month with prices and a CIK: median {info['median_members']:.0f}. Share of those with the chosen signal: "
              f"median {cov['50%']:.0%}, min {cov['min']:.0%} (banks and insurers have no gross profit, so `gpa` and `qv` skip most financials).",
              "- Point in time: each XBRL value is used only from its SEC `filed` date; fiscal-year figures older than "
              f"{config.QV_MAX_ANNUAL_AGE_DAYS} days and balance sheets older than {config.QV_MAX_INSTANT_AGE_DAYS} days are treated as missing.",
              "- Tickers are matched to companies by today's SEC ticker list, so a recycled ticker could pair one company's prices with another's "
              "filings when both filed in the same years. This is rare in the S&P 500 but not checked.",
              f"- {info['bad']} stock-month returns above +{config.MOMENTUM_MAX_MONTHLY_RET:.0%} (or at -100%) were dropped as bad data. "
              "Held names with no next-month price are dropped and the book reweighted, so delisting losses are missed.",
              f"- Average monthly turnover of the chosen variant: {df['turnover'].mean():.0%}.",
              f"- The {costs[0]:.1%} round trip is realistic for S&P 500 names; {', '.join(f'{c:.0%}' for c in costs[1:])} are the project's "
              "small-cap house assumptions and are shown as a stress test.",
              f"- Sanity check, market caps at {info['check_month']}: {info['check']}.",
              "", f"Monthly series of the chosen variant: `{MONTHLY_CSV}`."]
    return "\n".join(lines) + "\n"


def main() -> None:
    costs, split, first = config.MOMENTUM_COSTS, str(pd.Period(config.QV_SPLIT, "M")), pd.Period(config.QV_FIRST_FORMATION, "M")
    membership = mo.load_membership(requests.get(config.SP500_MEMBERSHIP_URL, timeout=60).text)
    start = membership.index[membership.index <= first.to_timestamp()].max()
    membership = membership[membership.index >= start]
    tickers = {norm_ticker(t) for s in membership.tolist() for t in s}
    membership = membership.map(lambda s: frozenset(norm_ticker(t) for t in s))
    cik = ticker_to_cik(sec_json(config.SEC_TICKERS_EXCHANGE_URL))
    mapped = sorted(t for t in tickers if t in cik)
    print(f"quality-value: {len(tickers)} members since {first}, {len(mapped)} with a current CIK; fetching prices")
    adj, close, splits = fetch_prices(mapped)
    facts = {}
    for i, t in enumerate(sorted(adj.columns)):
        try:
            facts[t] = Facts(tidy_facts(sec_json(config.SEC_COMPANYFACTS_URL.format(cik=cik[t]))))
        except Exception as exc:  # 404 for companies without XBRL, network errors: skip the company
            print(f"quality-value: no facts for {t}: {exc}")
        if i % 100 == 0:
            print(f"quality-value: facts {i}/{adj.shape[1]}")
    rets, bad = mo.clean_returns(adj)
    months = [m for m in adj.index if m >= first]
    members = mo.members_at_month_ends(membership, pd.PeriodIndex(months))
    panel = signal_panel(facts, close, splits, members, months)
    results = {}
    for v in VARIANTS:
        picks, sizes, uni = picks_for(panel, rets, v[0], v[1], config.QV_MIN_RANKED)
        results[v] = mo.run_from_picks(picks, sizes, rets, uni, v[2], costs)
    chosen = mo.pick_variant(results, split, costs[0])
    cm = pd.Period("2015-12", "M")
    check = ", ".join(f"{t} ${panel[cm].at[t, 'mcap'] / 1e9:,.0f}bn" for t in ("AAPL", "MSFT", "NVDA", "JPM", "XOM")
                      if cm in panel and t in panel[cm].index and pd.notna(panel[cm].at[t, "mcap"]))
    info = {"n_tickers": len(tickers), "n_cik": len(mapped), "n_priced": adj.shape[1], "bad": bad, "check_month": str(cm),
            "check": check or "not available", "median_members": float(np.median([len(p) for p in panel.values()]))}
    REPORT.parent.mkdir(exist_ok=True)
    results[chosen].to_csv(MONTHLY_CSV, index=False)
    md = report(results, chosen, costs, split, info)
    REPORT.write_text(md)
    print(md)
