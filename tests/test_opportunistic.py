import numpy as np
import pandas as pd

import config
from edge.form4 import opportunistic as op
from test_backtest import make_zip  # reuse the synthetic SEC zip


def buy(issuer, owner, date, filed=None, value=50000.0, ticker="ACME", title="CEO"):
    d = pd.Timestamp(date)
    return dict(accession=f"{issuer}-{owner}-{date}", form_type="4", issuer_cik=issuer, issuer="Acme", ticker=ticker,
                owner_cik=owner, owner="X", role="Officer", is_director=False, is_officer=True, officer_title=title,
                is_ten_pct=False, date=d, shares=100.0, price=value / 100, value=value,
                filed=pd.Timestamp(filed) if filed else d + pd.Timedelta(days=2))


def months_for(issuer, owner, years, month):
    return pd.DataFrame([{"issuer_cik": issuer, "owner_cik": owner, "year": y, "month": month} for y in years])


def test_trade_months_includes_sales_and_buys():
    m = op.trade_months(make_zip())
    assert set(m.columns) == {"issuer_cik", "owner_cik", "year", "month"} and len(m) >= 2


def test_classify_routine_vs_opportunistic():
    buys = pd.DataFrame([buy("1", "a", "2024-03-10"), buy("1", "b", "2024-03-10"), buy("1", "c", "2024-03-10")])
    hist = pd.concat([months_for("1", "a", [2021, 2022, 2023], 3),   # a: March every one of the last 3 years -> routine
                      months_for("1", "b", [2021, 2023], 3),          # b: gap in 2022 -> opportunistic
                      months_for("1", "c", [2021, 2022, 2023], 4)])   # c: other month -> opportunistic
    k = op.classify(buys, hist)
    assert list(k) == ["routine", "opportunistic", "opportunistic"]


def test_build_events_quiet_period_and_kind():
    buys = pd.DataFrame([buy("1", "a", "2024-03-01"), buy("1", "a", "2024-03-10"), buy("1", "a", "2024-05-10"),
                         buy("2", "b", "2024-03-01", value=5000.0)])
    kinds = pd.Series(["opportunistic"] * 4, index=buys.index)
    ev = op.build_events(buys, kinds, 2024)
    # issuer 1: first (Mar 3 filing) and May 12 filing; the Mar 12 filing is inside the 30-day quiet period;
    # issuer 2 is below the minimum value
    assert sorted(ev["filed"].dt.strftime("%Y-%m-%d")) == ["2024-03-03", "2024-05-12"]
    assert (ev["officer"]).all() and set(ev["kind"]) == {"opportunistic"}


def test_event_kind_is_opportunistic_if_any_buyer_is():
    buys = pd.DataFrame([buy("1", "a", "2024-03-01"), buy("1", "b", "2024-03-01")])
    ev = op.build_events(buys, pd.Series(["routine", "opportunistic"], index=buys.index), 2024)
    assert len(ev) == 1 and ev.iloc[0]["kind"] == "opportunistic" and ev.iloc[0]["n_buyers"] == 2


def test_cost_tiers():
    assert op.round_trip_cost(50e6) == 0.004 and op.round_trip_cost(8e6) == 0.010
    assert op.round_trip_cost(1e6) == 0.025 and op.round_trip_cost(None) == 0.025 and op.round_trip_cost(np.nan) == 0.025


def bars(n=400, vol=1e6):
    idx = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame({"close": [10.0 + i * 0.01 for i in range(n)], "volume": vol}, index=idx)


def test_features_use_only_past_and_entry_is_after_filing():
    b = bars()
    filed = b.index[300].strftime("%Y-%m-%d")
    f = op.features_and_returns(b, filed)
    assert f["entry_date"] == b.index[301].strftime("%Y-%m-%d")
    assert abs(f["adv"] - b["close"].iloc[281:301].mean() * 1e6) < 1  # trailing 20 bars up to the filing date
    assert abs(f["drawdown"]) < 1e-12  # steadily rising: at its 52-week high on the filing date
    assert abs(f["gross_20d"] - (b["close"].iloc[321] / b["close"].iloc[301] - 1)) < 1e-12
    # changing prices after the filing date must not change features
    b2 = b.copy(); b2.iloc[310:, 0] = 1.0
    assert op.features_and_returns(b2, filed)["adv"] == f["adv"] and op.features_and_returns(b2, filed)["drawdown"] == f["drawdown"]
    assert op.features_and_returns(b.iloc[:310], filed)["gross_60d"] is None


def _events(n=60, kind="opportunistic"):
    rng = np.random.default_rng(0)
    rows = []
    for i in range(n):
        rows.append(dict(kind=kind, filed=pd.Timestamp("2024-03-01") + pd.Timedelta(days=i % 20), ticker=f"T{i}",
                         total_value=float(rng.integers(30_000, 900_000)), n_buyers=int(rng.integers(1, 4)),
                         officer=bool(rng.integers(0, 2)), drawdown=-float(rng.random()), adv=float(rng.choice([1e6, 8e6, 40e6])),
                         have_prices=True, **{f"net_{h}d": float(rng.normal(0, .05)) for h in config.STUDY_HORIZONS},
                         **{f"excess_{h}d": float(rng.normal(0, .05)) for h in config.STUDY_HORIZONS}))
    return pd.DataFrame(rows)


def test_quintiles_and_small_months():
    ev = op.add_quintiles(_events())
    assert set(ev["quintile"].dropna()) == {1.0, 2.0, 3.0, 4.0, 5.0}
    small = op.add_quintiles(_events(n=5))
    assert small["quintile"].isna().all()  # fewer than MIN_EVENTS_PER_MONTH


def test_evaluate_and_report_end_to_end():
    ev0 = pd.DataFrame([dict(issuer_cik="1", filed=pd.Timestamp("2024-02-01"), ticker="AAA", issuer="A", kind="opportunistic",
                             n_buyers=2, total_value=100000.0, last_price=10.0, officer=True)])
    b = bars()
    ev = op.evaluate(ev0, fetch_bars=lambda s: b)
    r = ev.iloc[0]
    assert r["have_prices"] and r["cost"] == 0.01  # about $14m average dollar volume: middle tier
    assert abs(r["net_20d"] - (r["gross_20d"] - r["cost"])) < 1e-12 and r["excess_20d"] is not None
    txt = op.report(pd.concat([ev, op.evaluate(ev0.assign(ticker="BBB", kind="routine"), fetch_bars=lambda s: b)], ignore_index=True))
    assert "Opportunistic vs routine" in txt and "Survivorship" in txt
    assert "No priced events" in op.report(ev.assign(have_prices=False))
