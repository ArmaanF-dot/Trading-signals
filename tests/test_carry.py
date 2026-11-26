import io
import zipfile

import numpy as np
import pandas as pd

import config
from edge import carry


def _zip(text: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("x.csv", text)
    return b.getvalue()


def test_kline_parser_handles_header_and_microseconds():
    ms = _zip("1577836800000,10,12,9,11,1,0,0,0,0,0,0\n1577923200000,11,13,10,12,1,0,0,0,0,0,0\n")
    us = _zip("open_time,open,high,low,close,volume,close_time,quote_volume,count,a,b,c\n1577836800000000,10,12,9,11,1,0,0,0,0,0,0\n")
    a = carry.kline_frame(carry.read_zip_csv(ms))
    b = carry.kline_frame(carry.read_zip_csv(us))
    assert list(a["close"]) == [11, 12] and a.index[0] == pd.Timestamp("2020-01-01")
    assert b.index[0] == pd.Timestamp("2020-01-01")


def test_funding_midnight_print_belongs_to_previous_day():
    z = _zip("calc_time,funding_interval_hours,last_funding_rate\n1577836800001,8,0.0001\n1577865600000,8,0.0002\n")
    s = carry.funding_frame(carry.read_zip_csv(z))
    assert s[pd.Timestamp("2019-12-31")] == 0.0001 and s[pd.Timestamp("2020-01-01")] == 0.0002


def _panel(n=400, funding=0.0001, drift=0.0, coins=("BTC", "ETH")):
    idx = pd.date_range("2022-01-01", periods=n)
    rows = []
    for c in coins:
        px = 100 * (1 + drift) ** np.arange(n)
        rows.append(pd.DataFrame({"date": idx, "coin": c, "spot": px, "perp": px, "perp_high": px, "funding": funding}))
    return pd.concat(rows)


def test_constant_funding_flat_basis_earns_funding_less_entry_cost():
    W = carry.wide(_panel())
    rf = pd.Series(0.0, index=W["carry"].index)
    df = carry.run_weights(W, carry.always_on(W, ["BTC"]), rf)
    expect_daily = 0.0001 / (1 + config.CARRY_MARGIN)
    assert abs(df["gross"].iloc[5] - expect_daily) < 1e-12
    entry = carry.leg_cost("BTC") / (1 + config.CARRY_MARGIN)
    assert abs(df["cost"].sum() - entry) < 1e-12  # one entry, no exit
    assert df["gross"].iloc[0] == 0  # nothing earned before the first decision can act


def test_hedge_cancels_price_moves():
    W = carry.wide(_panel(drift=0.01, funding=0.0))
    df = carry.run_weights(W, carry.always_on(W, ["BTC", "ETH"]), pd.Series(0.0, index=W["carry"].index))
    assert df["gross"].abs().max() < 1e-12


def test_filter_uses_only_past_funding():
    p = _panel(coins=("BTC",))
    W1 = carry.wide(p)
    p2 = p.copy()
    p2.loc[p2.index[-1], "funding"] = -0.5  # change the last day only
    W2 = carry.wide(p2)
    a, b = carry.filtered(W1, ["BTC"], 7, 0.0), carry.filtered(W2, ["BTC"], 7, 0.0)
    assert a.iloc[:-1].equals(b.iloc[:-1])
    r1 = carry.run_weights(W1, a, pd.Series(0.0, index=a.index))
    r2 = carry.run_weights(W2, b, pd.Series(0.0, index=a.index))
    assert r1["net"].iloc[:-1].equals(r2["net"].iloc[:-1])


def test_filter_exits_when_funding_turns_negative_and_pays_costs():
    p = _panel(coins=("BTC",), n=200)
    p.loc[p.index[100:], "funding"] = -0.0002
    W = carry.wide(p)
    df = carry.run_weights(W, carry.filtered(W, ["BTC"], 7, 0.0), pd.Series(0.0, index=W["carry"].index))
    assert df["deployed"].iloc[-1] == 0
    assert df["cost"].sum() > carry.leg_cost("BTC") / (1 + config.CARRY_MARGIN) * 1.9  # entry and exit
