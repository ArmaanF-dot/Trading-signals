import numpy as np
import pandas as pd

from edge import combine, textchg
from edge.products import collect as pc


def test_tokens_drop_tables_and_compare():
    html = "<p>Strong growth and record profitability.</p><table><tr><td>secretword</td></tr></table>"
    c = textchg.tokens(html)
    assert "growth" in c and "secretword" not in c
    assert textchg.cosine(c, c) > 0.999
    assert textchg.cosine(c, textchg.tokens("<p>losses impairment failure</p>")) == 0


def test_tone_needs_enough_words():
    assert np.isnan(textchg.tone(textchg.tokens("good growth"))[0])
    big = textchg.tokens("<p>" + "good loss " * 1500 + "</p>")
    assert abs(textchg.tone(big)[0]) < 1e-9


def test_periodic_filings_and_prior_year():
    sub = {"filings": {"recent": {"form": ["10-Q", "10-Q", "8-K", "10-K"], "filingDate": ["2024-05-01", "2023-05-02", "2024-05-01", "2024-02-01"],
                                  "accessionNumber": ["a", "b", "c", "d"], "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm"]}, "files": []}}
    fl = textchg.periodic_filings(sub)
    assert list(fl["acc"]) == ["b", "d", "a"]
    assert textchg.prior_year(fl, 2) == 0 and textchg.prior_year(fl, 1) is None


def test_company_features_uses_prior_year_text_only():
    fl = pd.DataFrame({"form": ["10-Q", "10-Q"], "filed": pd.to_datetime(["2023-05-02", "2024-05-01"]), "acc": ["b", "a"], "doc": ["b.htm", "a.htm"]})
    pages = {"b.htm": "<p>" + "alpha beta " * 50 + "</p>", "a.htm": "<p>" + "alpha beta " * 50 + "</p>"}
    rows = textchg.company_features("0000000001", "XYZ", fl, lambda u: pages[u.rsplit("/", 1)[1]], since="2024-01-01")
    assert len(rows) == 1 and rows[0]["sim"] > 0.999 and rows[0]["filed"] == pd.Timestamp("2024-05-01")


def test_next_ear_looks_forward_only():
    feats = pd.DataFrame({"cik": ["0000000001"], "filed": [pd.Timestamp("2024-05-01")]})
    pev = pd.DataFrame({"cik": [1, 1, 1], "filed": ["2024-04-30", "2024-05-02", "2024-08-01"], "ear": [0.9, 0.5, 0.07]})
    assert textchg.next_ear(feats, pev).iloc[0] == 0.07


def test_attach_text_is_backward_only_and_combined_score():
    jobs = pd.DataFrame({"ticker": ["A", "A", "B"], "filed": pd.to_datetime(["2024-05-10", "2024-01-05", "2024-05-10"]),
                         "d_total": [0.1, 0.2, 0.3]})
    text = pd.DataFrame({"ticker": ["A", "A"], "filed": pd.to_datetime(["2024-05-09", "2024-05-11"]), "text_score": [0.2, 0.9]})
    out = combine.attach_text(jobs, text)
    assert out.loc[0, "text_score"] == 0.2          # not the filing that came after the report
    assert np.isnan(out.loc[1, "text_score"]) and np.isnan(out.loc[2, "text_score"])
    sc = combine.add_scores(out.assign(liquid=True))
    assert sc["combined"].notna().sum() == 1


def test_product_parse_summarise_features():
    prods = [{"id": 1, "variants": [{"price": "80", "compare_at_price": "100", "available": True}]},
             {"id": 2, "variants": [{"price": "50", "compare_at_price": None, "available": False}]}]
    cur = pc.parse(prods)
    s = pc.summarise(cur, {"1": [80, 100, 1], "3": [10, 0, 1]})
    assert s["products"] == 2 and s["on_sale"] == 1 and abs(s["avg_discount"] - 0.2) < 1e-9
    assert s["in_stock"] == 0.5 and s["added"] == 1 and s["removed"] == 1
    days = pd.date_range("2025-01-01", periods=100)
    d = pd.DataFrame({"date": days.strftime("%Y-%m-%d"), "ticker": "X", "status": "ok", "products": 10,
                      "on_sale": np.r_[np.full(50, 1), np.full(50, 4)], "avg_discount": 0.1, "in_stock": 0.9})
    f = pc.features_at(d, "X", "2025-04-10")
    assert f["d_sale_share"] > 0.2
    assert np.isnan(pc.features_at(d.head(20), "X", "2025-04-10")["d_sale_share"])
