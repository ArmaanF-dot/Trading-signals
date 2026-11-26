"""Combining signals: job postings + 10-K/10-Q text changes (+ product pages, forward only).

For each earnings report in the job-postings events (reports/jobs_deep_events.csv) we attach the
latest text score from reports/text_events.csv.gz that was public before the report. Pre-set rule
(fixed before looking at any result, signs from the literature, not fitted):

    combined = mean of two within-quarter percentile ranks:
        job postings: change in total postings (more hiring = better)
        text: combined text score (unchanged, positive-toned filings = better)

A report needs both to be scored. Each signal alone is shown on the same events so any gain from
combining is visible. Outcomes: earnings-day reaction (EAR) and 20/60/120-day drift. In sample
2017-21, out of sample 2022 onward. Product-page data has no history, so it is reported as a count
of what can be tested so far.
"""
import numpy as np
import pandas as pd

import config
from edge import pead, textchg
from edge.form4 import opportunistic as op
from edge.products import collect as pcollect

OUTS = {"ear": "EAR", "excess_20d": "Drift 20d", "excess_60d": "Drift 60d", "excess_120d": "Drift 120d"}
SIGS = {"jobs": "Job postings only", "text": "Text only", "combined": "Combined"}
MAX_TEXT_AGE_DAYS = 120


def attach_text(jobs: pd.DataFrame, text: pd.DataFrame) -> pd.DataFrame:
    """Latest text score per job event, from a filing at least a day before the report and at most
    MAX_TEXT_AGE_DAYS earlier, same company. Text scores are ranks within their own quarter."""
    t = text[["ticker", "filed", "text_score"]].dropna().sort_values("filed").rename(columns={"filed": "text_filed"})
    j = jobs.reset_index(drop=True).assign(_pos=lambda d: d.index, _key=lambda d: d["filed"] - pd.Timedelta(days=1)).sort_values("_key")
    out = pd.merge_asof(j, t, left_on="_key", right_on="text_filed", by="ticker", direction="backward",
                        tolerance=pd.Timedelta(days=MAX_TEXT_AGE_DAYS))
    return out.sort_values("_pos").drop(columns=["_key", "_pos"]).reset_index(drop=True)


def add_scores(ev: pd.DataFrame) -> pd.DataFrame:
    ev = ev.copy()
    ev["quarter"] = ev["filed"].dt.to_period("Q")
    ev["jobs"] = ev.groupby("quarter")["d_total"].rank(pct=True)
    ev["text"] = ev.groupby("quarter")["text_score"].rank(pct=True)
    ev["combined"] = (ev["jobs"] + ev["text"]) / 2
    return ev


def ic_cells(g: pd.DataFrame, sig: str) -> list[str]:
    cells = []
    for o in OUTS:
        ic = _ic(g, sig, o)
        cells.append("n/a" if len(ic) < 3 else f"{ic.mean():+.3f} (t {textchg._t(ic):.1f})")
    return cells


def _ic(g: pd.DataFrame, sig: str, o: str, min_n: int = 8) -> pd.Series:
    d = g[g[sig].notna() & g[o].notna()]
    out = {q: gq[sig].rank().corr(gq[o].rank()) for q, gq in d.groupby("quarter") if len(gq) >= min_n}
    return pd.Series(out, dtype=float)


def top_bottom(g: pd.DataFrame, sig: str, h: int, stress: float) -> str:
    """Top third minus bottom third excess return at horizon h, before costs, and top third net of the stress cost."""
    d = g[g[sig].notna() & g[f"excess_{h}d"].notna() & g["liquid"]].copy()
    if len(d) < 30:
        return "n/a"
    d["tier"] = np.ceil(d.groupby("quarter")[sig].rank(pct=True, method="first") * 3).clip(1, 3)
    top, bot = d[d["tier"] == 3], d[d["tier"] == 1]
    return f"{top[f'excess_{h}d'].mean() - bot[f'excess_{h}d'].mean():+.2%} gross; top net {op._wmean(top[f'excess_{h}d'] - stress):+.2%} (n {len(top)})"


def product_status() -> list[str]:
    f = pcollect.DAILY
    if not f.exists():
        return ["No product snapshots yet."]
    d = pd.read_csv(f)
    ok = d[d["status"] == "ok"]
    days = ok["date"].nunique()
    return [f"Product-page collector: {len(pcollect.load_sites())} sites, {days} daily snapshots so far "
            f"({ok['date'].min() if days else 'none'} to {ok['date'].max() if days else 'none'}). "
            "Features need about 90 days of history before an earnings date, so earnings reports testable today: 0."]


def report(ev: pd.DataFrame, n_jobs: int) -> str:
    stress = config.ROUND_TRIP_COST
    oos_start = pd.Timestamp(config.PEAD_OOS_START)
    both = ev[ev["combined"].notna()]
    L = ["# Combining job postings and filing-text signals", "",
         f"Job-postings earnings reports: {n_jobs}. With a text score from a filing in the previous {MAX_TEXT_AGE_DAYS} days as well: {len(both)} "
         f"(liquid: {int(both['liquid'].sum())}). Rank correlation (IC) within each quarter, averaged, t across quarters. "
         "Rule fixed in advance (see module note); no weights were fitted.", ""]
    for name, g in (("In sample (2017-21)", both[both["filed"] < oos_start]), ("Out of sample (2022 onward)", both[both["filed"] >= oos_start])):
        L += [f"## {name}: {len(g)} reports", "", "| signal | " + " | ".join(OUTS.values()) + " |", "|---|" + "---|" * len(OUTS)]
        for s, sn in SIGS.items():
            L.append(f"| {sn} | " + " | ".join(ic_cells(g, s)) + " |")
        L += ["", f"Liquid reports, top third minus bottom third by signal, excess over SPY (stress cost {stress:.1%} once per trade):", "",
              "| signal | 60d | 120d |", "|---|---|---|"]
        for s, sn in SIGS.items():
            L.append(f"| {sn} | {top_bottom(g, s, 60, stress)} | {top_bottom(g, s, 120, stress)} |")
        L.append("")
    L += ["## Product pages (forward only)", ""] + product_status()
    L += ["", "## Verdict", "", "VERDICT_PLACEHOLDER", "",
          "Caveats: the overlap is small and tech-heavy (only companies with a public job board); many ICs are shown, so a few will pass "
          "|t| >= 2 by chance; the text score is word lists, not a language model. Not financial advice."]
    return "\n".join(L)


def verdict(ev: pd.DataFrame) -> str:
    oos = ev[(ev["filed"] >= pd.Timestamp(config.PEAD_OOS_START)) & ev["combined"].notna()]
    if len(oos) < 100:
        return "Too few overlapping out-of-sample reports to judge; the combination cannot be tested properly yet."
    res = {}
    for s in SIGS:
        ics = [_ic(oos, s, o) for o in OUTS]
        res[s] = max(abs(textchg._t(i)) if len(i) > 2 else 0 for i in ics)
    if res["combined"] >= 2 and res["combined"] > max(res["jobs"], res["text"]):
        return "The combined score is the only one with a significant out-of-sample IC; treat as a lead for the forward test, not an edge, given the number of tests."
    return "No edge: the combined score is no better out of sample than either signal alone, and nothing clears t >= 2 on the main outcomes after allowing for the number of tests."


def main() -> None:
    jobs = pd.read_csv(config.REPORTS_DIR / "jobs_deep_events.csv", parse_dates=["filed"])
    jobs = jobs[jobs["d_total"].notna()]
    text = pd.read_csv(config.REPORTS_DIR / "text_events.csv.gz", parse_dates=["filed"])
    ev = add_scores(attach_text(jobs, text))
    out = report(ev, len(jobs)).replace("VERDICT_PLACEHOLDER", verdict(ev))
    (config.REPORTS_DIR / "combined_signals.md").write_text(out + "\n")
    print(out)
