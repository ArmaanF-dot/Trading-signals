import numpy as np
import pandas as pd

from edge import frontier as fr


def _rets(n=60, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2015-01", periods=n, freq="M")
    cols = list(fr.PAIRS) + sorted({f for f, _ in fr.PAIRS.values()})
    return pd.DataFrame(rng.normal(0, 0.05, (n, len(cols))), index=idx, columns=cols)


def test_signal_uses_only_past_returns():
    r = _rets()
    a = fr.signals(r, "gap", 1)
    r2 = r.copy()
    r2.iloc[-1] = 0.5  # change the last month: earlier signals must not move
    b = fr.signals(r2, "gap", 1)
    assert a.iloc[:-1].equals(b.iloc[:-1])


def test_planted_lag_is_found_and_costs_reduce_return():
    r = _rets(120, 1)
    for etf, (fut, _) in fr.PAIRS.items():  # ETF follows last month's commodity move
        r[etf] = 0.8 * r[fut].shift(1).fillna(0) + r[etf] * 0.2
    df = fr.run_variant(r, "raw", 1, [0.003, 0.02], "2016-06")
    assert df["gross"].mean() > 0 and df["ic"].mean() > 0.1
    assert (df["net_0.02"] < df["gross"]).all()


def test_verdict_no_edge_on_noise():
    r = _rets(120, 2)
    df = fr.run_variant(r, "gap", 3, [0.003, 0.02, 0.03], "2016-06")
    assert fr.verdict(df, [0.003, 0.02, 0.03]).startswith(("NO EDGE", "EDGE"))
