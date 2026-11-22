import numpy as np
import pandas as pd

from edge import ml_rank as ml


def _daily(n=12, days=600, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-01", periods=days)
    cols = [f"T{i}" for i in range(n)]
    close = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0.0003, 0.02, (days, n)), axis=0), index=idx, columns=cols)
    volume = pd.DataFrame(rng.uniform(1e5, 1e6, (days, n)), index=idx, columns=cols)
    return close, volume


def test_features_stop_the_day_before_the_trade_close():
    close, volume = _daily()
    f1 = ml.daily_features(close, volume)
    me = ml.month_end_dates(close.index)
    m = me.index[20]
    c2 = close.copy()
    c2.loc[me[m]] *= 3.0  # a huge move on the trade close itself must not reach month m's features
    f2 = ml.daily_features(c2, volume)
    for k in ml.FEATURES:
        pd.testing.assert_series_equal(f1[k].loc[m], f2[k].loc[m], check_names=False)
    assert not f1["mom_12_1"].loc[m].isna().any() and (f1["hi52"].loc[m] <= 1 + 1e-12).all()


def test_jump_keeps_sign_of_biggest_move():
    r3 = np.array([[0.01, np.nan], [-0.20, np.nan], [0.05, np.nan]])
    out = ml._jump(r3, 2, 63)
    assert out[0] == -0.20 and np.isnan(out[1])


def _data(months=180, n=120, seed=0):
    """Synthetic ranked table where next-month return is U-shaped in mom_12_1 (non-linear) plus noise."""
    rng = np.random.default_rng(seed)
    per = pd.period_range("2000-01", periods=months, freq="M")
    rows, rets = [], pd.DataFrame(index=per.append(pd.PeriodIndex([per[-1] + 1])), columns=[f"S{i}" for i in range(n)], dtype=float)
    for m in per:
        f = pd.DataFrame(rng.uniform(size=(n, len(ml.FEATURES))), columns=ml.FEATURES)
        fwd = 0.08 * np.abs(f["mom_12_1"] - 0.5) - 0.02 + rng.normal(0, 0.04, n)
        f["month"], f["ticker"], f["fwd"] = m, [f"S{i}" for i in range(n)], fwd
        f["label"] = f["fwd"].rank(pct=True) - 0.5
        f["members"] = n
        rows.append(f)
        rets.loc[m + 1] = fwd.to_numpy()
    members = {m: frozenset(rets.columns) for m in per}
    return pd.concat(rows, ignore_index=True), rets, members


def test_walk_forward_never_sees_future_labels():
    data, _, _ = _data(months=96)
    p1, _ = ml.walk_forward(data, "ridge", "2003-01")
    cut = pd.Period("2005-06", "M")
    bad = data.copy()
    late = bad["month"] > cut
    bad.loc[late, "label"] = -bad.loc[late, "label"]  # rewrite the future
    p2, _ = ml.walk_forward(bad, "ridge", "2003-01")
    early = data["month"] <= cut
    assert p1[early].notna().any()
    pd.testing.assert_series_equal(p1[early], p2[early])
    assert p1[data["month"] < pd.Period("2003-01", "M")].isna().all()


def test_gbm_finds_nonlinear_signal_ridge_does_not():
    data, _, _ = _data()
    g, _ = ml.walk_forward(data, "gbm", "2005-01")
    r, _ = ml.walk_forward(data, "ridge", "2005-01")
    assert ml.monthly_ic(data, g)["ic"].mean() > 0.1
    assert abs(ml.monthly_ic(data, r)["ic"].mean()) < 0.05


def test_end_to_end_report_on_synthetic_edge():
    data, rets, members = _data()
    costs = [0.002, 0.02, 0.03]
    results, ics, coefs, chosen = ml.run_all(data, rets, members, costs, "2005-01", "2010-01")
    assert chosen[0] == "gbm"
    info = {"n_tickers": 120, "n_priced": 120, "rows": len(data), "per_month": 120, "coverage": 1.0, "bad": 0, "first_pred": "2005-01"}
    md = ml.report(results, ics, chosen, costs, "2010-01", ml.feature_ics(data, "2010-01"), coefs, info)
    assert "**Verdict:** EDGE" in md and "Held-out test" in md and "mom_12_1" in md
    flat = results[chosen].copy()
    for c in ["gross"] + [f"net_{c:g}" for c in costs]:
        flat[c] = flat["bench_ew"] - 0.001
    assert ml.verdict(flat, costs, "x").startswith("NO EDGE")


def test_picks_take_top_slice():
    data, _, _ = _data(months=3, n=50)
    score = data["mom_12_1"]
    picks, sizes = ml.picks_from_scores(data, score, 0.1)
    m = data["month"].iloc[0]
    top = data[data["month"] == m].nlargest(5, "mom_12_1")["ticker"]
    assert set(picks[m].index) == set(top) and sizes[m] == (50, 50)
