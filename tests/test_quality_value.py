import numpy as np
import pandas as pd

from edge import momentum as mo
from edge import quality_value as qv


def _f(end, val, filed, start=None, form="10-K", accn="a1"):
    d = {"end": end, "val": val, "filed": filed, "form": form, "accn": accn}
    if start:
        d["start"] = start
    return d


COMPANYFACTS = {"facts": {
    "us-gaap": {
        "Assets": {"units": {"USD": [_f("2019-12-31", 1000, "2020-02-20"), _f("2020-12-31", 2000, "2021-02-20", accn="a2")]}},
        "StockholdersEquity": {"units": {"USD": [_f("2020-12-31", 500, "2021-02-20", accn="a2"),
                                                 _f("2021-03-31", 600, "2021-05-01", form="10-Q", accn="q1")]}},
        "GrossProfit": {"units": {"USD": [_f("2019-12-31", 300, "2020-02-20", start="2019-01-01"),
                                          # a quarter: never used as a fiscal year
                                          _f("2021-03-31", 999, "2021-05-01", start="2021-01-01", form="10-Q", accn="q1")]}},
        # 2020 has no GrossProfit tag, only revenue and cost of revenue in the same filing
        "Revenues": {"units": {"USD": [_f("2020-12-31", 1000, "2021-02-20", start="2020-01-01", accn="a2")]}},
        "CostOfRevenue": {"units": {"USD": [_f("2020-12-31", 600, "2021-02-20", start="2020-01-01", accn="a2")]}},
        "NetIncomeLoss": {"units": {"USD": [_f("2020-12-31", 100, "2021-02-20", start="2020-01-01", accn="a2"),
                                            # restated later: counts only from its own filing date
                                            _f("2020-12-31", 80, "2021-08-01", start="2020-01-01", form="10-K/A", accn="a3")]}},
    },
    "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        _f("2021-02-10", 10, "2021-02-20", accn="a2"), _f("2021-02-10", 5, "2021-02-20", accn="a2"),  # two share classes
        _f("2021-04-25", 16, "2021-05-01", form="10-Q", accn="q1")]}}},
}}


def facts():
    return qv.Facts(qv.tidy_facts(COMPANYFACTS))


def d(s):
    return np.datetime64(pd.Timestamp(s))


def test_point_in_time_gross_profit_and_assets():
    f = facts()
    gp, e = f.latest("gross_profit", d("2021-01-31"), 480)
    assert gp == 300 and pd.Timestamp(e) == pd.Timestamp("2019-12-31")  # 2020 10-K not filed yet
    gp, e = f.latest("gross_profit", d("2021-03-31"), 480)
    assert gp == 400  # derived 1000 - 600; the 10-Q quarter is ignored
    assert f.latest("assets", d("2021-03-31"), 480, end=e)[0] == 2000
    assert np.isnan(f.latest("gross_profit", d("2022-12-31"), 480)[0])  # stale


def test_restatement_used_only_after_filing():
    f = facts()
    assert f.latest("net_income", d("2021-06-30"), 480)[0] == 100
    assert f.latest("net_income", d("2021-09-30"), 480)[0] == 80


def test_shares_sum_classes_and_split_basis():
    f = facts()
    sh, cover = f.shares(d("2021-03-31"))
    assert sh == 15 and pd.Timestamp(cover) == pd.Timestamp("2021-02-10")
    assert f.shares(d("2021-05-31"))[0] == 16
    splits = [(pd.Timestamp("2021-03-15"), 2.0), (pd.Timestamp("2020-01-01"), 3.0)]
    assert qv.split_factor(splits, pd.Timestamp("2021-02-10")) == 2.0


def test_signals_at(monkeypatch):
    monkeypatch.setattr(qv.config, "QV_MIN_MCAP", 0)
    f = facts()
    s = qv.signals_at(f, d("2021-03-31"), 20.0, [])
    assert s["mcap"] == 300  # 15 shares x 20
    assert s["gpa"] == 400 / 2000 and s["bm"] == 500 / 300 and s["ep"] == 100 / 300
    s = qv.signals_at(f, d("2021-03-31"), 20.0, [(pd.Timestamp("2021-03-15"), 2.0)])
    assert s["mcap"] == 600  # pre-split share count doubled to today's basis


def test_parse_chart_with_splits():
    ts = [int(pd.Timestamp(x).timestamp()) for x in ("2020-07-01", "2020-08-01", "2020-09-01")]
    js = {"chart": {"result": [{"timestamp": ts,
                                "indicators": {"quote": [{"close": [100.0, 120.0, None]}], "adjclose": [{"adjclose": [95.0, 115.0, None]}]},
                                "events": {"splits": {"1": {"date": int(pd.Timestamp("2020-08-31").timestamp()), "numerator": 4, "denominator": 1}}}}]}}
    adj, close, splits = qv.parse_chart(js)
    assert list(adj.index.astype(str)) == ["2020-07", "2020-08"] and close.iloc[-1] == 120.0
    assert splits[0][1] == 4.0


def test_picks_and_backtest_rank_by_signal():
    """Synthetic: stocks with higher signal earn more, so the tilt beats the ranked universe."""
    rng = np.random.default_rng(1)
    idx = pd.period_range("2015-01", periods=30, freq="M")
    tick = [f"S{i:03d}" for i in range(150)]
    drift = np.linspace(-0.01, 0.02, 150)
    adj = pd.DataFrame(100 * np.cumprod(1 + drift + rng.normal(0, 0.003, (30, 150)), axis=0), index=idx, columns=tick)
    rets, _ = mo.clean_returns(adj)
    panel = {m: pd.DataFrame({"gpa": drift + rng.normal(0, 0.001, 150)}, index=tick) for m in idx}
    picks, sizes, uni = qv.picks_for(panel, rets, "gpa", 0.1, 100)
    assert len(picks[idx[0]]) == 15 and idx[-1] not in picks
    df = mo.run_picks(picks, sizes, rets, uni, 3, [0.002, 0.02])
    assert (df["gross"] > df["bench_ew"]).mean() > 0.9
    assert df["turnover"].iloc[1:].mean() < 0.5  # overlapping cohorts rebuild a third of the book a month
