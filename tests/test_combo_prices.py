import pandas as pd

from edge import combo, prices


def fca(rows):
    return pd.DataFrame(rows, columns=["holder", "issuer", "isin", "net_short_pct", "position_date"])


def rns(rows):
    return pd.DataFrame(rows, columns=["date", "company", "isin", "ticker", "director", "role", "shares", "price", "value_gbp", "source_url"])


def test_combo_matches_on_isin_and_threshold():
    r = rns([("2026-11-15", "Foo", "GB1", "FOO", "Ann", "CEO", "1", "1", "50000", ""),
             ("2026-11-16", "Foo", "GB1", "FOO", "Bob", "CFO", "1", "1", "20000", ""),
             ("2026-11-16", "Low", "GB2", "LOW", "Cy", "CEO", "1", "1", "9000", ""),
             ("2026-11-16", "None", "GB3", "NON", "Di", "CEO", "1", "1", "9000", "")])
    f = fca([("A", "Foo", "GB1", 0.4, ""), ("B", "Foo", "GB1", 0.3, ""), ("A", "Low", "GB2", 0.2, "")])
    out = combo.find_combos(r, f, today="2026-11-20")
    assert list(out["isin"]) == ["GB1"]
    row = out.iloc[0]
    assert row["n_directors"] == 2 and row["total_net_short_pct"] == 0.7 and row["director_value_gbp"] == 70000


def test_combo_ignores_old_buys():
    r = rns([("2026-08-01", "Foo", "GB1", "FOO", "Ann", "CEO", "1", "1", "50000", "")])
    assert combo.find_combos(r, fca([("A", "Foo", "GB1", 1.0, "")]), today="2026-11-20").empty


def test_returns_for():
    idx = pd.bdate_range("2026-11-02", periods=30)
    closes = pd.Series([100 + i for i in range(30)], index=idx, dtype=float)
    out = prices.returns_for(closes, "2026-11-02")
    assert out["price_at_signal"] == 100 and out["ret_5d"] == 0.05 and out["ret_20d"] == 0.2
    young = prices.returns_for(closes.iloc[:10], "2026-11-02")
    assert young["ret_5d"] == 0.05 and young["ret_20d"] == ""
    assert prices.returns_for(pd.Series(dtype=float), "2026-11-02")["price_at_signal"] == ""


def test_fill_returns_skips_complete_rows_and_uses_cache():
    calls = []

    def fake(sym):
        calls.append(sym)
        return pd.Series([10.0] * 30, index=pd.bdate_range("2026-11-02", periods=30))

    df = pd.DataFrame({"ticker": ["VOD", "VOD", "XYZ"], "d": ["2026-11-02"] * 3,
                       "price_at_signal": ["", "", ""], "ret_5d": ["", "", ""], "ret_20d": ["", "0.1", ""]})
    out = prices.fill_returns(df, "ticker", "d", "uk", fetch=fake)
    assert calls == ["vod.uk", "xyz.uk"] and out.loc[1, "ret_20d"] == "0.1" and out.loc[0, "ret_20d"] == 0.0


def test_stooq_symbol():
    assert prices.stooq_symbol("VOD.L", "uk") == "vod.uk" and prices.stooq_symbol("ACME", "us") == "acme.us"
