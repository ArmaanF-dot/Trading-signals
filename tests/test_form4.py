import pandas as pd

from conftest import FIX
from edge.form4 import cluster, fetch, parse


def test_parse_keeps_only_open_market_purchases():
    rows = parse.parse_form4((FIX / "form4_buy.xml").read_text(), "0000111111-26-000001")
    assert len(rows) == 1
    r = rows[0]
    assert r["ticker"] == "ACME" and r["value"] == 55000.0
    assert r["role"] == "CEO, Director" and r["owner_cik"] == "0000222222"


def test_parse_feed_and_filter(monkeypatch):
    entries = fetch.parse_feed((FIX / "feed.atom").read_text())
    assert [e["form_type"] for e in entries] == ["4", "8-K", "4/A"]
    assert entries[0]["accession"] == "0000111111-26-000001"
    monkeypatch.setattr(fetch, "_get", lambda url: (FIX / "feed.atom").read_text())
    out = fetch.list_recent_filings(pages=2)
    assert {f["accession"] for f in out} == {"0000111111-26-000001", "0000888888-26-000003"}


def test_find_xml_url_skips_xsl():
    url = fetch.find_xml_url((FIX / "index.html").read_text())
    assert url.endswith("/wf-form4.xml") and "xsl" not in url


def _buys(rows):
    return pd.DataFrame(rows, columns=["issuer_cik", "ticker", "issuer", "owner_cik", "owner", "role",
                                       "accession", "date", "shares", "price", "value"])


def test_cluster_detected_and_emitted_once():
    b = _buys([
        ("1", "ACME", "Acme", "o1", "A", "CEO", "a1", "2026-11-02", 10000, 6, 60000),
        ("1", "ACME", "Acme", "o2", "B", "CFO", "a2", "2026-11-05", 10000, 6, 60000),
        ("1", "ACME", "Acme", "o2", "B", "CFO", "a3", "2026-11-07", 1000, 6, 6000),
    ])
    out = cluster.find_clusters(cluster.load_buys(b))
    assert len(out) == 1 and out.iloc[0]["n_insiders"] == 2 and out.iloc[0]["total_value"] == 126000


def test_no_cluster_cases():
    one = _buys([("1", "A", "A", "o1", "X", "CEO", "a1", "2026-11-02", 1, 1, 500000)])
    assert cluster.find_clusters(cluster.load_buys(one)).empty
    small = _buys([("1", "A", "A", "o1", "X", "CEO", "a1", "2026-11-02", 1, 1, 40000),
                   ("1", "A", "A", "o2", "Y", "CFO", "a2", "2026-11-03", 1, 1, 40000)])
    assert cluster.find_clusters(cluster.load_buys(small)).empty
    wide = _buys([("1", "A", "A", "o1", "X", "CEO", "a1", "2026-10-01", 1, 1, 90000),
                  ("1", "A", "A", "o2", "Y", "CFO", "a2", "2026-11-03", 1, 1, 90000)])
    assert cluster.find_clusters(cluster.load_buys(wide)).empty


def test_joint_filing_value_counted_once():
    # same trade reported for two owners on one accession
    b = _buys([("1", "A", "A", "o1", "X", "CEO", "a1", "2026-11-02", 5, 10, 60000),
               ("1", "A", "A", "o2", "Y", "CFO", "a1", "2026-11-02", 5, 10, 60000)])
    assert cluster.find_clusters(cluster.load_buys(b)).empty  # 60k, not 120k
