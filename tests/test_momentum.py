import numpy as np
import pandas as pd

from edge import momentum as mo

MEMBERSHIP = "date,tickers\n2000-01-03,\"AAA,BBB,CCC\"\n2001-06-01,\"AAA,BBB,DDD\"\n"


def test_load_membership_point_in_time():
    mem = mo.load_membership(MEMBERSHIP)
    months = pd.period_range("1999-12", "2001-07", freq="M")
    m = mo.members_at_month_ends(mem, months)
    assert pd.Period("1999-12", "M") not in m  # nothing published yet
    assert m[pd.Period("2001-05", "M")] == {"AAA", "BBB", "CCC"}
    assert m[pd.Period("2001-06", "M")] == {"AAA", "BBB", "DDD"}  # CCC left, DDD joined


def test_monthly_closes_from_yahoo_bars():
    idx = pd.to_datetime(["2024-01-01", "2024-02-01", "2024-02-15"])  # Yahoo adds a partial bar for the current month
    bars = pd.DataFrame({"close": [10.0, 11.0, 12.0], "volume": 1.0}, index=idx)
    s = mo.monthly_closes(bars)
    assert list(s.index.astype(str)) == ["2024-01", "2024-02"] and s.iloc[-1] == 12.0


def test_signal_skips_latest_month_and_bad_data():
    idx = pd.period_range("2020-01", periods=14, freq="M")
    p = pd.DataFrame({"A": [100.0] * 12 + [200.0, 200.0], "B": 100 * 1.01 ** np.arange(14)}, index=idx)
    rets, bad = mo.clean_returns(p)
    mom = mo.signal(rets)
    # at 2021-01 (row 12) the signal covers 2020-01..2020-12: A flat, so the +100% in the latest month is skipped
    assert abs(mom.loc[idx[12], "A"]) < 1e-12
    assert abs(mom.loc[idx[12], "B"] - (1.01 ** 11 - 1)) < 1e-9
    assert np.isnan(mom.loc[idx[10], "B"])  # needs 11 returns
    p.loc[idx[5], "A"] = 1000.0  # recycled-ticker style jump: +900%
    rets, bad = mo.clean_returns(p)
    assert bad == 1 and np.isnan(mo.signal(rets).loc[idx[12], "A"])


def _universe(n=60, months=40, seed=0):
    """n stocks with persistent drifts: the high-drift names should be the momentum winners."""
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2010-01", periods=months, freq="M")
    drift = np.linspace(-0.02, 0.03, n)
    r = drift + rng.normal(0, 0.005, (months, n))
    tick = [f"S{i:02d}" for i in range(n)]
    panel = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=idx, columns=tick)
    members = {m: frozenset(tick) for m in idx}
    return panel, members, drift


def test_strategy_picks_winners_and_charges_costs():
    panel, members, drift = _universe()
    rets, _ = mo.clean_returns(panel)
    df = mo.run_strategy(panel, rets, members, 0.1, 1, [0.002, 0.02], "2011-01")
    assert len(df) > 10
    assert (df["holdings"] == 6).all()  # top 10% of 60
    assert (df["gross"] > df["bench_ew"]).mean() > 0.9  # persistent drift => winners beat the universe
    assert abs(df["turnover"].iloc[0] - 1.0) < 1e-12  # first month buys the whole book
    first = df.iloc[0]
    assert abs(first["net_0.02"] - (first["gross"] - 0.01)) < 1e-9  # turnover 1.0 x half of 2%
    assert (df["net_0.002"] >= df["net_0.02"]).all()


def test_overlapping_hold_halves_turnover_when_ranking_changes():
    panel, members, _ = _universe()
    rets, _ = mo.clean_returns(panel)
    h1 = mo.run_strategy(panel, rets, members, 0.2, 1, [0.002], "2011-01")
    h2 = mo.run_strategy(panel, rets, members, 0.2, 2, [0.002], "2011-01")
    assert h2["turnover"].iloc[2:].mean() <= h1["turnover"].iloc[2:].mean() + 1e-12


def test_delisted_holding_is_dropped_and_book_reweighted():
    panel, members, _ = _universe()
    panel.loc[pd.Period("2011-06", "M"):, "S59"] = np.nan  # best name disappears
    rets, _ = mo.clean_returns(panel)
    df = mo.run_strategy(panel, rets, members, 0.1, 1, [0.002], "2011-01").set_index("month")
    assert df.loc["2011-06", "holdings"] == 5


def test_report_and_verdict_from_fake_results():
    panel, members, _ = _universe(months=60)
    rets, _ = mo.clean_returns(panel)
    costs = [0.002, 0.02, 0.03]
    res = {v: mo.run_strategy(panel, rets, members, v[0], v[1], costs, "2011-01") for v in mo.VARIANTS}
    chosen = mo.pick_variant(res, "2013-01", costs[0])
    assert chosen in res
    md = mo.report(res, chosen, costs, "2013-01", bad=0, n_tickers=60, n_priced=60)
    assert md.startswith("# 12-1 momentum") and "**Verdict:** EDGE" in md and "Out of sample" in md
    flat = res[chosen].copy()
    flat["gross"] = flat["bench_ew"]
    for c in costs:
        flat[f"net_{c:g}"] = flat["bench_ew"] - 0.001
    assert mo.verdict(flat, costs).startswith("NO EDGE")
