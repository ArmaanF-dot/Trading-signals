import numpy as np
import pandas as pd

import config
from edge.fca import backtest as fb
from edge.fca import isin_map


def raw_sheet(rows, with_end=False):
    head = ["Position Holder", "Name of Share Issuer", "ISIN", "Net Short Position (%)", "Position Date"] + (["Date the position became historical"] if with_end else [])
    return pd.DataFrame([["Title row"], [], head] + rows).astype(object)


def test_parse_sheet_finds_header_and_columns():
    df = fb.parse_sheet(raw_sheet([["Fund A", "Foo plc", "GB1", "0.6", "01/03/2024"], ["Fund B", "Foo plc", "", "0.7", "01/03/2024"]]), "Current Disclosures")
    assert len(df) == 1 and df.iloc[0]["pct"] == 0.6 and df.iloc[0]["date"] == pd.Timestamp("2024-03-01")
    ended = fb.parse_sheet(raw_sheet([["Fund A", "Foo plc", "GB1", "0.6", "01/03/2024", "10/04/2024"]], True), "Historic Disclosures")
    assert ended.iloc[0]["end"] == pd.Timestamp("2024-04-10") and ended.iloc[0]["date"] == pd.Timestamp("2024-03-01")


def pos(rows):
    return pd.DataFrame(rows, columns=["holder", "issuer", "isin", "pct", "date", "end", "sheet"]).astype({"date": "datetime64[ns]", "end": "datetime64[ns]"})


def test_aggregate_events_from_holder_intervals():
    p = pos([
        ("A", "Foo", "GB1", 0.6, "2024-03-01", "2024-03-20", "Historic"),   # A shorts 0.6 then closes
        ("B", "Foo", "GB1", 1.0, "2024-03-05", pd.NaT, "Historic"),         # B 1.0, then B's next row below
        ("B", "Foo", "GB1", 0.3, "2024-04-01", pd.NaT, "Current"),          # B reduces to 0.3 (open-ended)
    ])
    ev = fb.aggregate_events(fb.intervals(p)).set_index("date")
    assert ev.loc["2024-03-01", "kind"] == "rise" and ev.loc["2024-03-01", "agg_after"] == 0.6
    assert ev.loc["2024-03-05", "delta"] == 1.0 and ev.loc["2024-03-05", "agg_after"] == 1.6
    assert ev.loc["2024-03-20", "kind"] == "fall" and ev.loc["2024-03-20", "agg_after"] == 1.0
    assert ev.loc["2024-04-01", "delta"] == -0.7  # B 1.0 -> 0.3
    small = pos([("A", "Foo", "GB1", 0.6, "2024-03-01", "2024-03-02", "Historic"), ("A", "Foo", "GB1", 0.8, "2024-03-02", pd.NaT, "Current")])
    assert fb.aggregate_events(fb.intervals(small), rise_pp=0.5).shape[0] == 1  # the 0.2 step is below threshold


def test_last_historic_row_without_end_is_dropped():
    p = pos([("A", "Foo", "GB1", 0.6, "2024-03-01", pd.NaT, "Historic Disclosures")])
    assert fb.intervals(p).empty


def test_uk_cost_tiers():
    assert fb.uk_cost(20e6) == 0.009 and fb.uk_cost(3e6) == 0.017 and fb.uk_cost(1e5) == 0.035 and fb.uk_cost(np.nan) == 0.035


def test_isin_map_caches_and_skips_known(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ISIN_TICKER_CSV", tmp_path / "m.csv")
    calls = []
    out = isin_map.map_isins(["GB1", "GB2"], search=lambda i: calls.append(i) or ("FOO.L" if i == "GB1" else None))
    assert out == {"GB1": "FOO.L"} and sorted(calls) == ["GB1", "GB2"]
    calls.clear()
    assert isin_map.map_isins(["GB1", "GB2"], search=lambda i: calls.append(i)) == {"GB1": "FOO.L"} and calls == []  # miss cached too


def test_evaluate_and_report(monkeypatch):
    idx = pd.bdate_range("2024-01-02", periods=300)
    bars = pd.DataFrame({"close": np.linspace(1000, 1300, 300), "volume": 1e6}, index=idx)  # pence; ~GBP 10-13m a day
    ev = pd.DataFrame([{"isin": "GB1", "issuer": "Foo", "date": pd.Timestamp("2024-08-01"), "delta": 0.8, "agg_after": 3.2, "kind": "rise"},
                       {"isin": "GB1", "issuer": "Foo", "date": pd.Timestamp("2024-09-02"), "delta": -0.6, "agg_after": 2.6, "kind": "fall"}])
    out = fb.evaluate(ev, {"GB1": "FOO.L"}, fetch_bars=lambda s: bars)
    r = out.iloc[0]
    assert r["have_prices"] and r["cost"] == 0.009 and abs(r["net_20d"] - (r["gross_20d"] - 0.009)) < 1e-12
    assert r["public_date"] == pd.Timestamp("2024-08-05")
    txt = fb.report(out)
    assert "| rise |" in txt and "| fall |" in txt and "rise to >= 3%" in txt
    assert "No priced events" in fb.report(out.assign(have_prices=False))
