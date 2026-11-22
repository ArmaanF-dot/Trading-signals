import numpy as np
import pandas as pd

from edge import pead


def bars_from(closes, start="2023-01-02", volume=1_000_000):
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"close": np.asarray(closes, dtype=float), "volume": float(volume)}, index=idx)


def test_universe_keeps_main_listing_on_nyse_or_nasdaq():
    js = {"fields": ["cik", "name", "ticker", "exchange"],
          "data": [[320193, "Apple", "AAPL", "Nasdaq"], [1067983, "Berkshire", "BRK-B", "NYSE"],
                   [1067983, "Berkshire", "BRK-A", "NYSE"], [1, "Otc Co", "OTCX", "OTC"], [2, "Warrant", "ABCDW.WS", "NYSE"]]}
    u = pead.universe(js)
    assert list(u["ticker"]) == ["AAPL", "BRK-B"] and u.iloc[0]["cik"] == "0000320193"


def test_filings_follows_older_files_and_earnings_dates_dedupes():
    sub = {"filings": {"recent": {"form": ["8-K", "8-K", "10-Q", "8-K"], "filingDate": ["2024-05-02", "2024-05-10", "2024-05-03", "2024-03-01"],
                                  "items": ["2.02,9.01", "2.02", "", "5.02"]},
                       "files": [{"name": "old.json", "filingFrom": "2015-01-01", "filingTo": "2023-12-31"},
                                 {"name": "ancient.json", "filingFrom": "2005-01-01", "filingTo": "2010-12-31"}]}}
    asked = []

    def more(name):
        asked.append(name)
        return {"form": ["8-K"], "filingDate": ["2023-11-02"], "items": ["2.02,7.01"]}

    fl = pead.filings(sub, more, since="2017-01-01")
    assert asked == ["old.json"]  # the file that ends before the start date is not fetched
    d = pead.earnings_dates(fl, since="2017-01-01", gap_days=45)
    # 2024-05-10 is within 45 days of 2024-05-02 (a follow-up), item 5.02 and the 10-Q are not earnings
    assert d == [pd.Timestamp("2023-11-02"), pd.Timestamp("2024-05-02")]


def test_measures_ear_entry_and_forward_returns_without_lookahead():
    n = 120
    stock = [100.0] * 30 + [110.0] * 2 + [110.0 * 1.001 ** k for k in range(1, n - 31)]
    b = bars_from(stock)
    bench = bars_from([200.0] * n)["close"]
    filed = b.index[30]  # filing day: its close is already 110, so the reaction is day 29 -> day 31
    m = pead.measures(b, bench, filed, horizons=(5, 20), lag=1)
    assert abs(m["ear"] - 0.10) < 1e-9
    assert m["entry_date"] == b.index[32].strftime("%Y-%m-%d")  # day +2: one close after the reaction is known
    assert abs(m["gross_5d"] - (1.001 ** 5 - 1)) < 1e-9 and m["bench_5d"] == 0.0
    assert m["adv"] == 100.0 * 1_000_000 and m["price"] == 100.0  # measured before the filing day


def test_measures_rejects_events_outside_price_history():
    b = bars_from([100.0] * 60)
    bench = bars_from([200.0] * 60)["close"]
    assert np.isnan(pead.measures(b, bench, b.index[5])["ear"])  # fewer than 20 bars before
    assert np.isnan(pead.measures(b, bench, b.index[-1] + pd.Timedelta(days=30))["ear"])  # no close after


def synthetic_events(n_days=200, per_day=5, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2020-01-01", periods=n_days)
    rows = []
    for d in days:
        for _ in range(per_day):
            ear = rng.normal(0, 0.05)
            rows.append({"filed": d, "entry_date": (d + pd.Timedelta(days=3)).strftime("%Y-%m-%d"), "ear": ear,
                         "liquid": True, "cost": 0.004, "excess_20d": 0.5 * ear + rng.normal(0, 0.01)})
    return pd.DataFrame(rows)


def test_quintiles_use_only_earlier_announcements():
    ev = synthetic_events()
    q = pead.add_quintiles(ev, days=91, min_n=100)
    first = ev["filed"].min()
    assert q.loc[q["filed"] < first + pd.Timedelta(days=28), "quintile"].isna().all()  # under 100 prior events
    later = q[q["quintile"].notna()]
    assert set(later["quintile"].unique()) == {1, 2, 3, 4, 5}
    # changing a future event's EAR must not change an earlier event's quintile
    ev2 = ev.copy()
    ev2.loc[ev2.index[-1], "ear"] = 99.0
    q2 = pead.add_quintiles(ev2, days=91, min_n=100)
    pd.testing.assert_series_equal(q["quintile"].iloc[:-1], q2["quintile"].iloc[:-1])


def test_planted_drift_gives_positive_spread_and_edge_verdict():
    q = pead.add_quintiles(synthetic_events(n_days=600), days=91, min_n=100)
    s = pead.period_stats(q[q["quintile"].notna()], 20)
    assert s["ls"] > 0.03 and s["ls_t"] > 5 and s["q5_net"] > 0
    assert pead.verdict(s).startswith("Edge")
    flat = dict(s, q5_net=-0.01, q5_net_t=-1.0, q5_gross=-0.005, ls=-0.001)
    assert pead.verdict(flat).startswith("No edge")


def test_report_renders(tmp_path):
    ev = synthetic_events(n_days=600)
    ev["filed"] = ev["filed"] + pd.DateOffset(years=1)  # straddle the out-of-sample start
    ev["entry_date"] = (ev["filed"] + pd.Timedelta(days=3)).dt.strftime("%Y-%m-%d")
    for h in (40, 60):
        ev[f"excess_{h}d"] = ev["excess_20d"]
    q = pead.add_quintiles(ev)
    text = pead.report(q, 123)
    assert "Out of sample" in text and "## Verdict" in text and "Q5 long" in text
