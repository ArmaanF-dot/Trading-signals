import numpy as np
import pandas as pd

from edge import momentum as mo
from edge import reversal as rv


def test_parse_chart_scales_open_by_adjustment_factor():
    payload = {"chart": {"result": [{
        "timestamp": [1704205800, 1704292200, 1704378600],  # 2024-01-02..04
        "indicators": {"quote": [{"open": [10.0, None, 22.0], "close": [11.0, 12.0, 20.0]}],
                       "adjclose": [{"adjclose": [5.5, 6.0, 20.0]}]}}]}}
    df = rv.parse_chart(payload)
    assert list(df.index.strftime("%Y-%m-%d")) == ["2024-01-02", "2024-01-04"]  # missing open dropped
    assert abs(df["open"].iloc[0] - 5.0) < 1e-12 and df["close"].iloc[0] == 5.5  # 2:1 adjustment applied to the open
    assert df["open"].iloc[1] == 22.0


def test_member_mask_is_point_in_time():
    mem = mo.load_membership("date,tickers\n2020-01-02,\"AAA,BBB\"\n2020-01-06,\"AAA,CCC\"\n")
    days = pd.bdate_range("2020-01-01", "2020-01-08")
    m = rv.member_mask(mem, days, ["AAA", "BBB", "CCC"])
    assert not m.loc["2020-01-01"].any()  # nothing published yet
    assert m.loc["2020-01-03"].tolist() == [True, True, False]
    assert m.loc["2020-01-07"].tolist() == [True, False, True]


def test_open_returns_drop_bad_data():
    opens = pd.DataFrame({"A": [10.0, 11.0, 33.0, 33.0]}, index=pd.bdate_range("2024-01-01", periods=4))
    r, bad = rv.open_returns(opens)
    assert abs(r["A"].iloc[0] - 0.1) < 1e-12 and np.isnan(r["A"].iloc[1]) and bad == 1  # +200% treated as bad
    assert np.isnan(r["A"].iloc[-1])  # no next open yet


def _universe(n=80, days=400, phi=-0.4, seed=0):
    """Prices whose daily moves partly reverse (phi < 0): yesterday's losers should bounce."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2011-01-03", periods=days)
    e = rng.normal(0, 0.02, (days, n))
    r = np.zeros_like(e)
    for t in range(1, days):
        r[t] = phi * e[t - 1] + e[t]
    tick = [f"S{i:02d}" for i in range(n)]
    closes = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=idx, columns=tick)
    opens = closes.shift(1).bfill()  # open = previous close: no overnight gap
    members = pd.DataFrame(True, index=idx, columns=tick)
    return opens, closes, members


def test_dip_buyer_profits_from_reversal_and_charges_costs():
    opens, closes, members = _universe()
    rets, _ = rv.open_returns(opens)
    df = rv.run_strategy(closes, rets, members, 3, 5, False, [0.002, 0.02], "2011-01-03")
    assert len(df) > 300
    assert (df["gross"] - df["bench_ew"]).mean() > 0.001  # losers bounce
    assert df["holdings"].iloc[-1] > 8  # several cohorts of 8 names, with overlap
    d = df.iloc[50]
    assert abs(d["net_0.02"] - (d["gross"] - d["turnover"] * 0.01)) < 1e-12
    assert (df["net_0.002"] >= df["net_0.02"]).all()


def test_trending_universe_gives_no_edge():
    opens, closes, members = _universe(phi=0.0, seed=1)
    rets, _ = rv.open_returns(opens)
    df = rv.run_strategy(closes, rets, members, 5, 5, False, [0.002], "2011-01-03")
    m = rv.to_monthly(df)
    assert mo.stats(m["gross"] - m["bench_ew"])["t"] < 2  # random walk: nothing to find


def test_no_lookahead_signal_close_does_not_affect_same_day_return():
    opens, closes, members = _universe()
    rets, _ = rv.open_returns(opens)
    base = rv.run_strategy(closes, rets, members, 3, 5, False, [0.002], "2011-01-03")
    day = base.index[100]
    shocked = closes.copy()
    shocked.loc[day:] *= np.linspace(0.5, 1.5, closes.shape[1])  # change today's (and later) closes only
    alt = rv.run_strategy(shocked, rets, members, 3, 5, False, [0.002], "2011-01-03")
    assert abs(alt.loc[day, "gross"] - base.loc[day, "gross"]) < 1e-12  # today's book was set before today's close
    assert abs(alt.loc[base.index[101], "gross"] - base.loc[base.index[101], "gross"]) > 1e-9


def test_trend_filter_and_minimum_universe():
    opens, closes, members = _universe(n=40)
    rets, _ = rv.open_returns(opens)
    df = rv.run_strategy(closes, rets, members, 3, 5, False, [0.002], "2011-01-03")
    assert df.empty  # fewer than 50 eligible names: no trades, no rows
    opens, closes, members = _universe()
    w, n_ok = rv.cohort_weights(closes, rv.open_returns(opens)[0], members, 3, True, 0.1)
    assert n_ok.iloc[:199].eq(0).all() and n_ok.iloc[250] < 80  # 200-day average needs history, then filters


def test_report_and_verdict():
    opens, closes, members = _universe(days=700)
    rets, _ = rv.open_returns(opens)
    costs = [0.002, 0.02, 0.03]
    res = {v: rv.run_strategy(closes, rets, members, *v, costs, "2011-01-03") for v in rv.VARIANTS}
    chosen = rv.pick_variant(res, "2012-06-01", costs[0])
    assert chosen in res
    md = rv.report(res, chosen, costs, "2012-06-01", bad=0, n_tickers=80, n_priced=80)
    assert md.startswith("# Short-term mean reversion") and "**Verdict:** EDGE" in md and "Out of sample by year" in md
    flat = rv.to_monthly(res[chosen])
    flat["gross"] = flat["bench_ew"]
    for c in costs:
        flat[f"net_{c:g}"] = flat["bench_ew"] - 0.001
    assert rv.verdict(flat, costs).startswith("NO EDGE")


def test_fetch_panels_retries_empty_tickers():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    calls = []

    def fetch(sym):
        calls.append(sym)
        if sym == "BRK-B" and calls.count(sym) == 1:
            return pd.DataFrame(columns=["open", "close"], dtype=float)
        return pd.DataFrame({"open": [1.0, 2.0], "close": [1.5, 2.5]}, index=idx)

    opens, closes = rv.fetch_panels(["AAA", "BRK.B"], fetch=fetch, retry_pause=0)
    assert set(closes.columns) == {"AAA", "BRK.B"} and calls.count("BRK-B") == 2
    assert opens.loc["2024-01-03", "AAA"] == 2.0
