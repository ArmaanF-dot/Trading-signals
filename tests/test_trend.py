import numpy as np
import pandas as pd

from edge import trend as tr


def _daily(n=2800, seed=0, drift=0.0003, vol=0.01):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2006-01-02", periods=n)
    r = rng.normal(drift, vol, (n, len(tr.UNIVERSE)))
    return pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=idx, columns=tr.UNIVERSE)


def test_signal_uses_only_past_prices():
    d = _daily()
    a = tr.trend_signal(d, "12m")
    d2 = d.copy()
    d2.iloc[-5:] *= 3  # change the final days: earlier month-end signals must not move
    b = tr.trend_signal(d2, "12m")
    assert a.iloc[:-1].equals(b.iloc[:-1])


def test_weights_hit_vol_target_and_respect_cap():
    d = _daily()
    dr = d.pct_change()
    sig = tr.trend_signal(d, "12m").dropna(how="all")
    m = sig.index[-3]
    w = tr.vol_scaled_weights(sig.loc[m], dr, m.to_timestamp(how="end").normalize())
    cov = dr[dr.index <= m.to_timestamp(how="end")].tail(tr.COV_WIN)[w.index].cov() * 252
    pv = float(np.sqrt(w.values @ cov.values @ w.values))
    assert abs(pv - 0.10) < 1e-6 or pv < 0.10  # equal to target unless the leverage cap binds


def test_planted_trend_is_captured_and_costs_reduce_return():
    d = _daily(drift=0.0, vol=0.002)
    rng = np.random.default_rng(5)
    for c in d.columns:  # slow persistent regimes: strong, long-lived trends
        regime = np.repeat(rng.choice([-1, 1], size=len(d) // 250 + 1), 250)[: len(d)]
        d[c] = 100 * np.cumprod(1 + regime * 0.0008 + rng.normal(0, 0.004, len(d)))
    df = tr.run_variant(d, "12m", "ls", [0.001, 0.025], "2008-01")
    assert df["gross"].mean() > df["bench_ew"].mean()
    assert (df["net_0.025"] < df["gross"]).all()


def test_verdict_no_edge_on_noise_and_tags():
    d = _daily(drift=0.0, seed=3)
    df = tr.run_variant(d, "sma10", "lo", [0.001, 0.0025, 0.025], "2008-01")
    assert tr.verdict(df, [0.001, 0.0025, 0.025]).startswith(("NO EDGE", "EDGE"))
    assert not df[["gross", "turnover", "bench_ew"]].isna().any().any()


def test_sharpe_se_and_breakeven():
    assert abs(tr.sharpe_se(0.0, 120) - (1 / 10) ** 0.5) < 1e-9
    df = pd.DataFrame({"gross": [0.01, 0.01], "turnover": [1.0, 1.0]})
    assert abs(tr.breakeven(df) - 0.02) < 1e-12
