import numpy as np
import pandas as pd

from edge.jobs import study

U1, U2 = "0b0e8a52-1111-4c2a-9a1e-123456789abc", "0b0e8a52-2222-4c2a-9a1e-123456789abc"


def test_count_postings_from_feeds_and_html():
    assert study.count_postings("greenhouse", "acme", '{"jobs":[{"id":1},{"id":2},{"id":2}],"meta":{"total":2}}') == 2
    assert study.count_postings("lever", "acme", f'[{{"id":"{U1}"}},{{"id":"{U2}"}}]') == 2
    html = '<a href="/acme/jobs/111">A</a><a href="https://boards.greenhouse.io/acme/jobs/111">A</a><a href="/acme/jobs/222">B</a>'
    assert study.count_postings("greenhouse", "acme", html) == 2
    lever = f'<div class="posting" data-qa-posting-id="{U1}"></div><a href="https://jobs.lever.co/acme/{U2}">x</a>'
    assert study.count_postings("lever", "acme", lever) == 2
    assert study.count_postings("ashby", "acme", f'<a href="/acme/{U1}">x</a>') == 1


def test_count_postings_treats_broken_or_empty_pages_as_missing():
    assert study.count_postings("greenhouse", "acme", "<html>Page not found</html>") is None
    assert study.count_postings("greenhouse", "acme", '{"jobs":[]}') is None
    assert study.count_postings("greenhouse", "acme", "{not json") is None
    assert study.count_postings("greenhouse", "acme", '{"error":"x"}') is None


def test_pick_monthly_keeps_one_capture_per_month_preferring_feeds():
    rows = [("20230105000000", "boards.greenhouse.io/acme"), ("20230120000000", "boards-api.greenhouse.io/v1/boards/acme/jobs"),
            ("20230210000000", "boards.greenhouse.io/acme")]
    out = study.pick_monthly(rows)
    assert out == [("20230120000000", "boards-api.greenhouse.io/v1/boards/acme/jobs"), ("20230210000000", "boards.greenhouse.io/acme")]


def test_signal_uses_only_snapshots_before_the_report():
    h = pd.DataFrame({"date": pd.to_datetime(["2023-01-10", "2023-03-01", "2023-04-20", "2023-05-03"]), "open": [100, 120, 200, 999]})
    s = study.signal_at(h, "2023-05-02", recent_max=45, lookback=80, lookback_max=150)
    assert s["jobs_now"] == 200  # the 3 May capture is after the report and must not be used
    assert s["jobs_then"] == 100  # latest capture at least 80 days before 20 April
    assert np.isclose(s["signal"], np.log1p(200) - np.log1p(100))
    stale = study.signal_at(h, "2023-08-30", recent_max=45)
    assert np.isnan(stale["signal"])


def test_terciles_use_only_earlier_events():
    d = pd.date_range("2022-01-01", periods=60, freq="7D")
    ev = pd.DataFrame({"filed": d, "signal": np.arange(60, dtype=float), "liquid": True})
    out = study.add_terciles(ev, days=365, min_n=30)
    assert out["tercile"].iloc[:30].isna().all()  # not enough history for breakpoints yet
    assert (out["tercile"].iloc[30:] == 3).all()  # a rising signal is always above past breakpoints
    ev.loc[45, "liquid"] = False
    assert np.isnan(study.add_terciles(ev, days=365, min_n=30).at[45, "tercile"])


def test_report_says_too_few_when_archive_is_thin():
    ev = pd.DataFrame({"filed": pd.to_datetime(["2023-01-01"]), "signal": [np.nan], "tercile": [np.nan]})
    cov = pd.DataFrame({"ticker": ["AAA"], "months": [3], "first": ["2023-01"], "last": ["2023-03"]})
    assert "Too few events" in study.report(ev, cov)
