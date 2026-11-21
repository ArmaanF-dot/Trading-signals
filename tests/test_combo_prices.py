import pandas as pd

from edge import combo, prices


def fca(rows):
    return pd.DataFrame(rows, columns=["issuer", "isin", "net_short_pct", "position_date"])


def rns(rows):
    return pd.DataFrame(rows, columns=["date", "company", "isin", "ticker", "director", "role", "shares", "price", "value_gbp", "source_url"])


def test_combo_matches_on_isin_and_threshold():
    r = rns([("2026-11-15", "Foo", "GB1", "FOO", "Ann", "CEO", "1", "1", "50000", ""),
             ("2026-11-16", "Foo", "GB1", "FOO", "Bob", "CFO", "1", "1", "20000", ""),
             ("2026-11-16", "Low", "GB2", "LOW", "Cy", "CEO", "1", "1", "9000", ""),
             ("2026-11-16", "None", "GB3", "NON", "Di", "CEO", "1", "1", "9000", "")])
    f = fca([("Foo", "GB1", 0.7, ""), ("Low", "GB2", 0.2, "")])
    out = combo.find_combos(r, f, today="2026-11-20")
    assert list(out["isin"]) == ["GB1"]
    row = out.iloc[0]
    assert row["n_directors"] == 2 and row["total_net_short_pct"] == 0.7 and row["director_value_gbp"] == 70000


def test_combo_ignores_old_buys():
    r = rns([("2026-08-01", "Foo", "GB1", "FOO", "Ann", "CEO", "1", "1", "50000", "")])
    assert combo.find_combos(r, fca([("Foo", "GB1", 1.0, "")]), today="2026-11-20").empty


def test_returns_for():
    idx = pd.bdate_range("2026-11-02", periods=30)
    closes = pd.Series([100 + i for i in range(30)], index=idx, dtype=float)
    out = prices.returns_for(closes, "2026-10-30")  # public Friday, entry at Monday's close
    assert out["price_at_signal"] == 100 and out["ret_5d"] == 0.05 and out["ret_20d"] == 0.2
    young = prices.returns_for(closes.iloc[:10], "2026-10-30")
    assert young["ret_5d"] == 0.05 and young["ret_20d"] == ""
    assert prices.returns_for(pd.Series(dtype=float), "2026-10-30")["price_at_signal"] == ""


def test_fill_returns_skips_complete_rows_and_uses_cache():
    calls = []

    def fake(sym):
        calls.append(sym)
        return pd.Series([10.0] * 30, index=pd.bdate_range("2026-11-02", periods=30))

    df = pd.DataFrame({"ticker": ["VOD", "VOD", "XYZ"], "d": ["2026-10-30"] * 3,
                       "price_at_signal": ["", "", ""], "ret_5d": ["", "", ""], "ret_20d": ["", "0.1", ""]})
    out = prices.fill_returns(df, "ticker", "d", "uk", fetch=fake)
    assert calls == ["VOD.L", "XYZ.L"] and out.loc[1, "ret_20d"] == "0.1" and out.loc[0, "ret_20d"] == 0.0


def test_yahoo_symbol():
    assert prices.yahoo_symbol("VOD", "uk") == "VOD.L" and prices.yahoo_symbol("brk.b", "us") == "BRK-B"


def test_fetch_closes_parses_yahoo_payload(monkeypatch):
    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"chart": {"result": [{"timestamp": [1704205800, 1704292200],
                    "indicators": {"quote": [{"close": [10.0, 11.0]}], "adjclose": [{"adjclose": [9.5, None]}]}}]}}
    monkeypatch.setattr(prices.requests, "get", lambda *a, **k: R())
    s = prices.fetch_closes("ACME")
    assert list(s) == [9.5] and s.index[0] == pd.Timestamp("2024-01-02")
    monkeypatch.setattr(prices.requests, "get", lambda *a, **k: (_ for _ in ()).throw(prices.requests.ConnectionError()))
    assert prices.fetch_closes("ACME").empty


def test_returns_for_with_benchmark_and_entry_gap():
    idx = pd.bdate_range("2026-11-02", periods=30)
    closes = pd.Series([100.0 + i for i in range(30)], index=idx)
    bench = pd.Series([50.0 + 0.5 * i for i in range(30)], index=idx)
    out = prices.returns_for(closes, "2026-10-30", bench)
    assert out["ret_20d"] == 0.2 and out["bench_ret_20d"] == round((60.0 / 50.0) - 1, 4)
    assert prices.returns_for(closes, "2026-09-01")["price_at_signal"] == ""  # history starts long after the signal


def test_fill_returns_uses_fallback_date_and_adds_columns():
    idx = pd.bdate_range("2026-11-02", periods=30)
    s = pd.Series([100.0 + i for i in range(30)], index=idx)
    df = pd.DataFrame({"ticker": ["ACME"], "public_date": [""], "signal_date": ["2026-10-28"]})  # +2 days -> Oct 30
    out = prices.fill_returns(df, "ticker", "public_date", "us", fetch=lambda sym: s, bench_symbol="IWM",
                              fallback_col="signal_date", fallback_days=2)
    assert out.loc[0, "price_at_signal"] == 100.0 and "bench_ret_20d" in out.columns
