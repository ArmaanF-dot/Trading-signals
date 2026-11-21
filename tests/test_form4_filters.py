import pandas as pd

import config
from edge.form4 import cluster, marketcap

COLS = ["issuer_cik", "ticker", "issuer", "owner_cik", "owner", "role", "accession", "date", "shares", "price",
        "value", "is_director", "is_officer", "is_ten_pct"]


def buys(rows):
    return cluster.load_buys(pd.DataFrame(rows, columns=COLS).astype(str))


def test_person_plus_own_fund_on_joint_filing_is_one_buyer():
    b = buys([("1", "BOLD", "Bold", "p", "TANG KEVIN", "10% owner", "a1", "2026-11-18", 100, 5, 500000, "False", "False", "True"),
              ("1", "BOLD", "Bold", "f", "TANG CAPITAL LLC", "10% owner", "a1", "2026-11-18", 100, 5, 500000, "False", "False", "True"),
              ("1", "BOLD", "Bold", "x", "OTHER", "Director", "a2", "2026-11-19", 100, 5, 500000, "True", "False", "False")])
    out = cluster.find_clusters(b)
    assert len(out) == 1 and out.iloc[0]["n_insiders"] == 2  # Tang+fund count once, plus OTHER


def test_joint_filing_alone_is_not_a_cluster():
    b = buys([("1", "BOLD", "Bold", "p", "TANG KEVIN", "10% owner", "a1", "2026-11-18", 100, 5, 500000, "False", "False", "False"),
              ("1", "BOLD", "Bold", "f", "TANG CAPITAL LLC", "10% owner", "a1", "2026-11-18", 100, 5, 500000, "True", "False", "False")])
    assert cluster.find_clusters(b).empty


def test_requires_officer_or_director():
    rows = [("1", "A", "A", "o1", "X", "10% owner", "a1", "2026-11-18", 1, 1, 80000, "False", "False", "True"),
            ("1", "A", "A", "o2", "Y", "10% owner", "a2", "2026-11-19", 1, 1, 80000, "False", "False", "True")]
    assert cluster.find_clusters(buys(rows)).empty
    assert len(cluster.find_clusters(buys(rows), require_insider=False)) == 1
    rows[1] = ("1", "A", "A", "o2", "Y", "CFO", "a2", "2026-11-19", 1, 1, 80000, "False", "True", "False")
    assert len(cluster.find_clusters(buys(rows))) == 1


def test_market_cap_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SHARES_CACHE_CSV", tmp_path / "shares.csv")
    cl = pd.DataFrame({"issuer_cik": ["1", "2", "3"], "last_price": [10.0, 10.0, 10.0], "market_cap": ["", "", ""]})
    shares = {"1": 50e6, "2": 500e6, "3": None}  # caps: $0.5bn, $5bn, unknown
    out = marketcap.apply_cap_filter(cl, fetch=lambda c: shares[c])
    assert list(out["issuer_cik"]) == ["1", "3"]  # big cap dropped, unknown kept
    assert out.loc[0, "market_cap"] == 500_000_000 and out.loc[1, "market_cap"] == ""
    calls = []
    marketcap.shares_for(["1", "2"], fetch=lambda c: calls.append(c))
    assert calls == []  # known values come from the cache


def test_fetch_shares_outstanding_parses_xbrl(monkeypatch):
    class R:
        text = '{"units": {"shares": [{"end": "2026-03-01", "val": 100}, {"end": "2026-09-30", "val": 120}]}}'
    monkeypatch.setenv("SEC_USER_AGENT", "Test Name test@example.com")
    monkeypatch.setattr(marketcap.http, "get", lambda *a, **k: R())
    assert marketcap.fetch_shares_outstanding("1") == 120.0
    monkeypatch.setattr(marketcap.http, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("404")))
    assert marketcap.fetch_shares_outstanding("1") is None


def test_public_date_uses_first_seen_or_trade_date_plus_two():
    rows = [("1", "A", "A", "o1", "X", "CEO", "a1", "2026-11-02", 1, 1, 80000, "False", "True", "False"),
            ("1", "A", "A", "o2", "Y", "CFO", "a2", "2026-11-04", 1, 1, 80000, "False", "True", "False")]
    df = pd.DataFrame(rows, columns=COLS).astype(str)
    old = cluster.find_clusters(cluster.load_buys(df))           # no "seen" column: trade date + 2 days
    assert old.iloc[0]["public_date"] == "2026-11-06"
    df["seen"] = ["2026-11-05", ""]                              # one seen, one legacy blank
    new = cluster.find_clusters(cluster.load_buys(df))
    assert new.iloc[0]["public_date"] == "2026-11-06"            # max(seen, legacy fallback)
    df["seen"] = ["2026-11-05", "2026-11-09"]
    assert cluster.find_clusters(cluster.load_buys(df)).iloc[0]["public_date"] == "2026-11-09"
