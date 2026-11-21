"""Opportunistic vs routine insider buys, plus a cross-sectional ranking of buy events.

Routine/opportunistic follows Cohen, Malloy and Pomorski ("Decoding Inside Information"):
an insider is *routine* for a trade if they traded (open-market buy or sale) in the same
calendar month in each of the previous three years; otherwise *opportunistic*. Deviation:
insiders with no history are counted as opportunistic (the paper excludes them).

No lookahead: events are dated by the Form 4 *filing* date and entered at the first close
after it. Features use prices before entry only. The ranking uses fixed, equal weights
(no fitting), so there is nothing to overfit beyond the choice of features.
"""
import numpy as np
import pandas as pd

import config
from edge import prices
from edge.form4 import backtest as bt

OFFICER_PAT = r"chief|ceo|cfo|president|chair|\bcoo\b|\bcio\b"


def trade_months(zf) -> pd.DataFrame:
    """Unique (issuer, owner, year, month) of every open-market buy or sale in a dataset."""
    sub = bt._tsv(zf, "SUBMISSION.tsv")
    own = bt._tsv(zf, "REPORTINGOWNER.tsv")
    tx = bt._tsv(zf, "NONDERIV_TRANS.tsv")
    tx = tx[tx["TRANS_CODE"].isin(["P", "S"])].copy()
    tx["date"] = bt._date(tx["TRANS_DATE"])
    tx = tx.dropna(subset=["date"])[["ACCESSION_NUMBER", "date"]]
    sub = sub[sub["DOCUMENT_TYPE"].isin(["4", "4/A"])][["ACCESSION_NUMBER", "ISSUERCIK"]]
    df = tx.merge(sub, on="ACCESSION_NUMBER").merge(own[["ACCESSION_NUMBER", "RPTOWNERCIK"]], on="ACCESSION_NUMBER")
    return pd.DataFrame({
        "issuer_cik": df["ISSUERCIK"].str.zfill(10), "owner_cik": df["RPTOWNERCIK"].str.zfill(10),
        "year": df["date"].dt.year, "month": df["date"].dt.month,
    }).drop_duplicates()


def load_history(start_year: int, end_year: int, dl=bt.download_quarter):
    """(buys, months) for all quarters; each zip is downloaded once."""
    buys, months = [], []
    for y in range(start_year, end_year + 1):
        for q in (1, 2, 3, 4):
            zf = dl(y, q)
            if zf is None:
                continue
            buys.append(bt.rows_from_zip(zf))
            months.append(trade_months(zf))
            bt.log(f"loaded {y}q{q}: {len(buys[-1])} buys")
    if not buys:
        return pd.DataFrame(columns=bt.TXN_COLS), pd.DataFrame(columns=["issuer_cik", "owner_cik", "year", "month"])
    return pd.concat(buys, ignore_index=True), pd.concat(months, ignore_index=True).drop_duplicates()


def classify(buys: pd.DataFrame, months: pd.DataFrame) -> pd.Series:
    """'routine' or 'opportunistic' per buy row."""
    seen = set(zip(months["issuer_cik"], months["owner_cik"], months["year"], months["month"]))
    d = pd.to_datetime(buys["date"])
    out = []
    for c, o, y, m in zip(buys["issuer_cik"], buys["owner_cik"], d.dt.year, d.dt.month):
        routine = all((c, o, y - k, m) in seen for k in (1, 2, 3))
        out.append("routine" if routine else "opportunistic")
    return pd.Series(out, index=buys.index)


def build_events(buys: pd.DataFrame, kinds: pd.Series, first_year: int) -> pd.DataFrame:
    """One event per issuer and kind per quiet period, dated by the first filing day.

    Features aggregate the buys filed that day. 'kind' is opportunistic if any buyer that day was."""
    b = buys.assign(kind=kinds, filed=pd.to_datetime(buys["filed"]))
    b = b[b["filed"].dt.year >= first_year]
    day = b.groupby(["issuer_cik", "filed"]).agg(
        ticker=("ticker", "last"), issuer=("issuer", "last"),
        kind=("kind", lambda k: "opportunistic" if (k == "opportunistic").any() else "routine"),
        n_buyers=("owner_cik", "nunique"), total_value=("value", "sum"), last_price=("price", "last"),
        officer=("officer_title", lambda t: bool(t.fillna("").str.contains(OFFICER_PAT, case=False, regex=True).any())),
    ).reset_index()
    day = day[(day["total_value"] >= config.MIN_EVENT_VALUE) & (day["ticker"] != "")]
    rows = []
    for (cik, kind), g in day.groupby(["issuer_cik", "kind"]):
        last = None
        for r in g.sort_values("filed").itertuples():
            if last is None or (r.filed - last).days >= config.EVENT_QUIET_DAYS:
                rows.append(r._asdict())
                last = r.filed
    return pd.DataFrame(rows).drop(columns=["Index"], errors="ignore")


def round_trip_cost(adv: float | None) -> float:
    if adv is None or not np.isfinite(adv):
        return config.LIQUIDITY_COST_TIERS[-1][1]
    for floor, cost in config.LIQUIDITY_COST_TIERS:
        if adv >= floor:
            return cost
    return config.LIQUIDITY_COST_TIERS[-1][1]


def features_and_returns(bars: pd.DataFrame, filed: str, horizons=config.STUDY_HORIZONS) -> dict:
    """Entry at the first close strictly after `filed`. Features use only bars up to the filing date."""
    out = {"entry_date": "", "adv": np.nan, "drawdown": np.nan}
    for h in horizons:
        out[f"gross_{h}d"] = None
    if bars.empty:
        return out
    t = pd.Timestamp(filed)
    before, after = bars[bars.index <= t], bars[bars.index > t]
    if after.empty:
        return out
    out["entry_date"] = after.index[0].strftime("%Y-%m-%d")
    tail = before.tail(20)
    if len(tail) >= 10 and tail["volume"].notna().any():
        out["adv"] = float((tail["close"] * tail["volume"]).mean())
    yr = before["close"].tail(252)
    if len(yr) >= 60:
        out["drawdown"] = float(yr.iloc[-1] / yr.max() - 1)
    p0 = float(after["close"].iloc[0])
    for h in horizons:
        if len(after) > h:
            out[f"gross_{h}d"] = float(after["close"].iloc[h]) / p0 - 1
    return out


def evaluate(events: pd.DataFrame, fetch_bars=prices.fetch_bars, benchmark=config.BACKTEST_BENCHMARK,
             horizons=config.STUDY_HORIZONS) -> pd.DataFrame:
    """Attach features, gross/net returns and benchmark excess to each event."""
    if events.empty:
        return events
    syms = {prices.yahoo_symbol(t, "us") for t in events["ticker"]}
    bars = bt.prefetch(syms | {benchmark}, fetch_bars)
    bench = bars[benchmark]
    rows = []
    for e in events.itertuples():
        b = bars.get(prices.yahoo_symbol(e.ticker, "us"), pd.DataFrame(columns=["close", "volume"]))
        f = features_and_returns(b, e.filed.strftime("%Y-%m-%d"), horizons)
        row = {**e._asdict(), **f, "have_prices": not b.empty and bool(f["entry_date"])}
        cost = round_trip_cost(f["adv"])
        row["cost"] = cost
        bf = features_and_returns(bench, e.filed.strftime("%Y-%m-%d"), horizons) if row["have_prices"] else {}
        for h in horizons:
            g = f[f"gross_{h}d"]
            row[f"net_{h}d"] = g - cost if g is not None else None
            bg = bf.get(f"gross_{h}d")
            row[f"excess_{h}d"] = g - bg - cost if g is not None and bg is not None else None
        rows.append(row)
    return pd.DataFrame(rows).drop(columns=["Index"], errors="ignore")


def score(ev: pd.DataFrame) -> pd.Series:
    """Equal-weight sum of z-scores (computed within the month): bigger buy, more buyers,
    officer involved, deeper drawdown from the 52-week high."""
    feats = pd.DataFrame({
        "value": np.log(ev["total_value"].astype(float)), "buyers": ev["n_buyers"].astype(float),
        "officer": ev["officer"].astype(float), "dd": -ev["drawdown"].astype(float),
    })
    z = (feats - feats.mean()) / feats.std(ddof=0).replace(0, np.nan)
    return z.fillna(0).sum(axis=1)


def add_quintiles(ev: pd.DataFrame) -> pd.DataFrame:
    """Score and quintile within each filing month; months with too few events get no quintile."""
    ev = ev.copy()
    ev["month"] = pd.to_datetime(ev["filed"]).dt.to_period("M")
    ev["score"] = np.nan
    ev["quintile"] = np.nan
    for _, idx in ev.groupby("month").groups.items():
        if len(idx) < config.MIN_EVENTS_PER_MONTH:
            continue
        sc = score(ev.loc[idx])
        ev.loc[idx, "score"] = sc
        ev.loc[idx, "quintile"] = np.ceil(sc.rank(pct=True) * 5).clip(1, 5)
    return ev


def _row(g: pd.DataFrame, horizons) -> list[str]:
    cells = [str(len(g))]
    for h in horizons:
        n, e = g[f"net_{h}d"].dropna(), g[f"excess_{h}d"].dropna()
        cells.append(f"{n.mean():.1%} / {(n > 0).mean():.0%} / {e.mean():.1%}" if len(n) else "n/a")
    return cells


def _table(title: str, groups: dict, horizons) -> list[str]:
    head = "| group | n | " + " | ".join(f"{h}d net / hit / excess" for h in horizons) + " |"
    out = [f"### {title}", "", head, "|---|---|" + "---|" * len(horizons)]
    for name, g in groups.items():
        out.append("| " + " | ".join([name] + _row(g, horizons)) + " |")
    return out + [""]


def report(ev: pd.DataFrame, horizons=config.STUDY_HORIZONS) -> str:
    have = ev[ev["have_prices"]] if len(ev) else ev
    L = ["# Opportunistic insiders and cross-sectional ranking", "",
         f"Events: {len(ev)}; with prices: {len(have)}. Entry at the first close after the filing date. "
         "Cost per trade depends on average dollar volume (assumed, not measured): "
         + ", ".join(f">= ${f / 1e6:g}m: {c:.1%}" if f else f"below: {c:.1%}" for f, c in config.LIQUIDITY_COST_TIERS)
         + " round trip. Cells are mean net return / share of trades positive after cost / mean net excess over IWM. "
         "Survivorship bias flatters everything (delisted names have no prices).", ""]
    if have.empty:
        return "\n".join(L + ["No priced events."])
    liquid = have[have["adv"] >= config.LIQUID_MIN_ADV]
    L += _table("Opportunistic vs routine (all priced)", {k: g for k, g in have.groupby("kind")}, horizons)
    L += _table(f"Opportunistic vs routine (liquid: ADV >= ${config.LIQUID_MIN_ADV / 1e6:g}m)",
                {k: g for k, g in liquid.groupby("kind")}, horizons)
    for kind in ("opportunistic", "routine"):
        for label, uni in (("all priced", have), ("liquid", liquid)):
            u = add_quintiles(uni[uni["kind"] == kind])
            u = u[u["quintile"].notna()]
            if u.empty:
                continue
            groups = {f"Q{int(q)}": g for q, g in u.groupby("quintile")}
            L += _table(f"{kind} buys, ranked quintiles ({label})", groups, horizons)
            spread = []
            for h in horizons:
                q5, q1 = u[u.quintile == 5][f"net_{h}d"].dropna(), u[u.quintile == 1][f"net_{h}d"].dropna()
                spread.append(f"{h}d: {q5.mean() - q1.mean():.1%}" if len(q5) and len(q1) else f"{h}d: n/a")
            L += [f"Q5 minus Q1 mean net return, {kind} ({label}): " + ", ".join(spread), ""]
    L += ["Caveats: events overlap in time and across names (not independent); fixed equal-weight "
          "score with four features, nothing fitted, but several tables were examined so a single "
          "good-looking cell can be luck; costs are assumptions; daily closes only. Not financial advice."]
    return "\n".join(L)


def main(first_year: int, last_year: int) -> None:
    buys, months = load_history(first_year - 3, last_year)
    bt.log(f"{len(buys)} buy rows, {len(months)} insider-months")
    kinds = classify(buys, months)
    events = build_events(buys, kinds, first_year)
    bt.log(f"{len(events)} events ({events['kind'].value_counts().to_dict() if len(events) else {}})")
    ev = evaluate(events)
    config.REPORTS_DIR.mkdir(exist_ok=True)
    ev.to_csv(config.REPORTS_DIR / "form4_opportunistic_events.csv", index=False)
    text = report(ev)
    (config.REPORTS_DIR / "form4_opportunistic.md").write_text(text + "\n")
    print(text)
