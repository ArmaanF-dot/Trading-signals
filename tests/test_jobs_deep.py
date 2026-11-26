import numpy as np
import pandas as pd

from edge.jobs import deep

U1, U2 = "0b0e8a52-1111-4c2a-9a1e-123456789abc", "0b0e8a52-2222-4c2a-9a1e-123456789abc"


def test_classify_titles():
    assert deep.classify("Senior Software Engineer, Payments") == "eng"
    assert deep.classify("Enterprise Account Executive") == "sales"
    assert deep.classify("Solutions Engineer") == "sales"  # pre-sales is go-to-market
    assert deep.classify("Paralegal") == "other"
    assert deep.classify("") == ""


def test_parse_postings_reads_titles_from_feeds_and_html():
    assert deep.parse_postings("greenhouse", "acme", '{"jobs":[{"id":1,"title":"Data Scientist"},{"id":2,"title":"Recruiter"}]}') == \
        {"1": "Data Scientist", "2": "Recruiter"}
    assert deep.parse_postings("lever", "acme", f'[{{"id":"{U1}","text":"Account Executive"}}]') == {U1: "Account Executive"}
    html = '<div class="opening"><a href="/acme/jobs/111">Backend Engineer</a></div><a href="/acme/jobs/222">Sales Lead</a>'
    assert deep.parse_postings("greenhouse", "acme", html) == {"111": "Backend Engineer", "222": "Sales Lead"}
    lever = (f'<div class="posting" data-qa-posting-id="{U1}"><h5 data-qa="posting-name">iOS Developer</h5></div>'
             f'<div class="posting" data-qa-posting-id="{U2}"><h5 data-qa="posting-name">Office Manager</h5></div>')
    assert deep.parse_postings("lever", "acme", lever) == {U1: "iOS Developer", U2: "Office Manager"}
    assert deep.parse_postings("greenhouse", "acme", "<html>gone</html>") is None


def _hist():
    rows = [deep.snapshot_row("A", "2023-01-10", {"1": "Software Engineer", "2": "Account Executive", "3": "Lawyer", "4": "Engineer"}),
            deep.snapshot_row("A", "2023-04-20", {"3": "Lawyer", "4": "Engineer", "5": "Sales Rep", "6": "Sales Manager",
                                                  "7": "Platform Engineer", "8": "Recruiter"})]
    return pd.DataFrame(rows)


def test_features_split_adds_removals_and_functions():
    f = deep.features_at(_hist(), "2023-05-02", recent_max=45, lookback=80, lookback_max=150)
    assert np.isclose(f["d_total"], np.log1p(6) - np.log1p(4))
    assert np.isclose(f["add_rate"], 4 / 4) and np.isclose(f["remove_rate"], 2 / 4)  # 5-8 new; 1, 2 gone
    assert np.isclose(f["net_flow"], 0.5)
    assert np.isclose(f["d_eng"], np.log1p(2) - np.log1p(2))
    assert np.isclose(f["d_sales"], np.log1p(2) - np.log1p(1))
    assert np.isnan(deep.features_at(_hist(), "2023-04-20")["d_total"])  # the 20 April capture is not before the report


def test_quarterly_revenue_derives_q4_and_acceleration():
    rows = []
    def q(start, end, val, prio=0):
        rows.append(("revenue", prio, pd.Timestamp(start), pd.Timestamp(end), val, pd.Timestamp(end) + pd.Timedelta(days=30), ""))
    for y, base in ((2022, 100.0), (2023, 120.0)):
        q(f"{y}-01-01", f"{y}-03-31", base)
        q(f"{y}-04-01", f"{y}-06-30", base)
        q(f"{y}-07-01", f"{y}-09-30", base)
        q(f"{y}-01-01", f"{y}-12-31", base * 4 + (10 if y == 2023 else 0))  # Q4 2023 = 130
    facts = pd.DataFrame(rows, columns=["concept", "prio", "start", "end", "val", "filed", "accn"])
    rev = deep.quarterly_revenue(facts)
    assert np.isclose(rev[pd.Timestamp("2023-12-31")], 130) and np.isclose(rev[pd.Timestamp("2022-12-31")], 100)
    # reported early Feb 2024: Q4 growth 30% vs Q3 growth 20% -> +10 points
    assert np.isclose(deep.rev_accel_at(rev, "2024-02-05"), 0.10)
    assert np.isnan(deep.rev_accel_at(rev, "2022-05-01"))  # no year-earlier quarter


def test_power_helpers():
    assert deep.events_needed(0.05) == 3136
    assert np.isclose(deep.mde(400), 0.14)
