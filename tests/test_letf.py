import numpy as np
import pandas as pd

from edge import letf


def _rets(n=500, seed=1, vol=0.02):
    rng = np.random.default_rng(seed)
    und = rng.normal(0, vol, n)
    idx = pd.bdate_range("2015-01-02", periods=n)
    return pd.DataFrame({"BULL": 3 * und, "BEAR": -3 * und, "UND": und}, index=idx)


def test_simulate_resets_to_target_and_drifts():
    r = _rets()
    pos, trade = letf.simulate(r, {"BULL": -0.5, "BEAR": -0.5}, 5)
    assert abs(pos.iloc[0]["BULL"] + 0.5) < 1e-12
    assert trade.iloc[0].sum() > 0 and trade.iloc[1].sum() == 0  # trades only on reset days
    assert trade.iloc[5].sum() > 0


def test_pair_hedge_has_near_zero_market_beta():
    r = _rets()
    pos, _ = letf.simulate(r, {"BULL": -0.5, "BEAR": -0.5}, 1)
    pnl = (pos * r[["BULL", "BEAR"]]).sum(axis=1)
    assert pnl.abs().max() < 1e-12  # exact mirror funds, daily reset: market P&L cancels every day


def test_borrow_and_spread_reduce_net_below_gross_without_rebate():
    r = _rets()
    pos, trade = letf.simulate(r, letf.legs("bullh", "BULL", "BEAR", "UND"), 5)
    rf = pd.Series(0.0, index=r.index)
    out = letf.excess_returns(r, pos, trade, rf, "BULL", "BEAR", letf.SCENARIOS["retail_broker"])
    assert out["net"].sum() < out["gross"].sum()


def test_regress_recovers_slope():
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(size=2000))
    y = 0.3 * x + rng.normal(size=2000)
    s = letf.regress(x, y)
    assert abs(s["beta"] - 0.3) < 0.05 and s["t"] > 5


def test_ibkr_small_account_earns_less_than_large_and_cfd_runs():
    r = _rets()
    pos, trade = letf.simulate(r, letf.legs("pair", "BULL", "BEAR", "UND"), 5)
    rf = pd.Series(0.04, index=r.index)
    small = letf.excess_returns(r, pos, trade, rf, "BULL", "BEAR", letf.SCENARIOS["ibkr_pro_3k"])["net"].sum()
    big = letf.excess_returns(r, pos, trade, rf, "BULL", "BEAR", letf.SCENARIOS["ibkr_pro_100k"])["net"].sum()
    cfd = letf.excess_returns(r, pos, trade, rf, "BULL", "BEAR", letf.SCENARIOS["ibkr_cfd_3k"])["net"]
    assert small < big and np.isfinite(cfd).all()
