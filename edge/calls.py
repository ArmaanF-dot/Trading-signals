"""Earnings-call language as a return signal: word choice, hedging and disfluency in the transcript.

Data: the free Hugging Face set zcyeee/sp500-earnings-call-turns (33,362 S&P 500 calls, 2005-2025, split
into speaker turns with role and prepared-remarks / Q&A section). It is text only. There is no free
audio at scale (see reports/calls_study.md), so pauses and pitch cannot be measured; the closest
text proxies are filler words, self-interruptions ("--") and hedges, which are measured here.

Features per call, each a share of words in one part of the call:
- management Q&A answers: tone (positive - negative), uncertainty, hedging, certainty, disfluency;
- prepared remarks: tone, uncertainty;
- analyst questions: tone.
Each is then taken as a change against the same company's previous PRIOR_CALLS calls (average), so
company style cancels. The pre-set score (fixed before any return was looked at) is the equal-weight
average of quarterly percentile ranks of: Q&A tone change (+), Q&A uncertainty change (-), Q&A hedge
change (-), Q&A disfluency change (-), Q&A-minus-prepared tone gap change (+), analyst question tone
change (+). High score = management sounds more upbeat and surer than usual.

Outcomes, costs, liquidity filter and entry rule follow edge/pead.py with the call date standing in
for the filing date (entry two closes after the first close following the call day). Out of sample
is CALLS_OOS_START onward. Word lists are short lists written for this study (the Loughran-McDonald
list is not freely redistributable), reusing the lists in edge/textchg.py. Survivorship: today's
S&P 500 membership (the dataset is of S&P 500 companies), which flatters long returns.
"""
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import config
from edge import pead, prices
from edge import textchg
from edge.form4 import backtest as bt
from edge.form4 import opportunistic as op

HF_SHARD_URL = "https://huggingface.co/datasets/zcyeee/sp500-earnings-call-turns/resolve/main/data/train-{i:05d}-of-00004.parquet"
SHARDS = 4
START = "2016-10-01"  # Yahoo's 10-year price history begins about here; one year of calls earlier feed the baseline
FIRST_EVENT = "2017-01-01"
OOS_START = "2022-01-01"
HORIZONS = (5, 20, 60)
PRIOR_CALLS = 4
MIN_PRIOR = 2
MIN_WORDS = 300  # a part of a call with fewer words gives no reliable share
BAD_CHECKS = {"not_this_company", "ticker_reused"}
BAD_FLAGS = {"no_qa_detected", "no_speaker_labels", "tiny_content"}

HEDGE = set("""approximately around roughly somewhat perhaps maybe possibly probably potentially arguably
hopefully relatively fairly generally largely mostly partly partially likely unlikely appears seems seem
suggest suggests""".split())
HEDGE_PHRASES = ("sort of", "kind of", "i think", "i guess", "i would say", "i suppose", "a little bit", "to some extent",
                 "more or less", "we believe", "we hope", "we expect to be able")
CERTAIN = set("""definitely certainly clearly absolutely confident confidence undoubtedly obviously
committed always never ensure guarantee""".split())
FILLER_WORDS = {"um", "uh", "er", "erm", "hmm", "ah"}
FILLER_PHRASES = ("you know", "i mean", "you see", "let me think", "how do i say")
_WORD = re.compile(r"[a-z']+")


def part_features(text: str) -> dict:
    """Shares (per word) of each word class in one block of text, plus the word count."""
    low = text.lower()
    toks = _WORD.findall(low)
    n = len(toks)
    out = {"words": n}
    if n < MIN_WORDS:
        return {**out, "tone": np.nan, "unc": np.nan, "hedge": np.nan, "certain": np.nan, "disfl": np.nan}
    pos = sum(t in textchg.POS for t in toks)
    neg = sum(t in textchg.NEG for t in toks)
    unc = sum(t in textchg.UNC for t in toks)
    hedge = sum(t in HEDGE for t in toks) + sum(low.count(p) for p in HEDGE_PHRASES)
    certain = sum(t in CERTAIN for t in toks)
    # disfluency: filler words and phrases, and self-interruptions marked by a double dash or ellipsis
    disfl = sum(t in FILLER_WORDS for t in toks) + sum(low.count(p) for p in FILLER_PHRASES) + low.count("--") + low.count("...")
    return {"words": n, "tone": (pos - neg) / n, "unc": unc / n, "hedge": hedge / n, "certain": certain / n, "disfl": disfl / n}


def call_features(turns: list[dict]) -> dict:
    """Features of one call from its speaker turns (management only counts as 'management' speech)."""
    prep = " ".join(t["text"] for t in turns if t["role"] == "management" and t["section"] == "prepared")
    ans = " ".join(t["text"] for t in turns if t["role"] == "management" and t["section"] == "qa")
    qs = " ".join(t["text"] for t in turns if t["role"] == "analyst" and t["section"] == "qa")
    p, a, q = part_features(prep), part_features(ans), part_features(qs)
    out = {"prep_words": p["words"], "ans_words": a["words"], "q_words": q["words"],
           "prep_tone": p["tone"], "prep_unc": p["unc"],
           "ans_tone": a["tone"], "ans_unc": a["unc"], "ans_hedge": a["hedge"], "ans_certain": a["certain"], "ans_disfl": a["disfl"],
           "q_tone": q["tone"]}
    out["gap_tone"] = a["tone"] - p["tone"]
    return out


LEVELS = ["ans_tone", "ans_unc", "ans_hedge", "ans_certain", "ans_disfl", "gap_tone", "q_tone", "prep_tone", "prep_unc"]
SCORE_PARTS = {"d_ans_tone": 1, "d_ans_unc": -1, "d_ans_hedge": -1, "d_ans_disfl": -1, "d_gap_tone": 1, "d_q_tone": 1}


def add_changes(feats: pd.DataFrame, prior: int = PRIOR_CALLS, min_prior: int = MIN_PRIOR) -> pd.DataFrame:
    """Each level minus the mean of the company's previous `prior` calls (at least `min_prior` of them
    with a value). Calls are ordered by date; the current call is never in its own baseline."""
    f = feats.sort_values(["cik", "date"]).reset_index(drop=True)
    for c in LEVELS:
        base = f.groupby("cik")[c].transform(lambda s: s.shift(1).rolling(prior, min_periods=min_prior).mean())
        f[f"d_{c}"] = f[c] - base
    return f


def add_score(ev: pd.DataFrame) -> pd.DataFrame:
    """Pre-set score: equal-weight mean of quarterly percentile ranks (sign-adjusted); all parts needed."""
    ev = ev.copy()
    ev["quarter"] = ev["filed"].dt.to_period("Q")
    ranks = []
    for c, sgn in SCORE_PARTS.items():
        r = ev.groupby("quarter")[c].rank(pct=True)
        ranks.append(r if sgn > 0 else 1 - r)
    ev["call_score"] = pd.concat(ranks, axis=1).mean(axis=1, skipna=False)
    return ev


# --- data ---

def load_calls(cache_dir: Path, shards=range(SHARDS)) -> pd.DataFrame:
    """Download the parquet shards (once) and compute features for every usable call since START."""
    import pyarrow.parquet as pq
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in shards:
        path = cache_dir / f"shard{i}.parquet"
        if not path.exists():
            bt.log(f"downloading shard {i}")
            with requests.get(HF_SHARD_URL.format(i=i), stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(path, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
        pf = pq.ParquetFile(path)
        for g in range(pf.num_row_groups):
            t = pf.read_row_group(g, columns=["symbol", "date", "cik", "company_check", "flags", "turns"]).to_pylist()
            for r in t:
                if r["date"] < START or r["company_check"] in BAD_CHECKS or BAD_FLAGS & set(r["flags"] or []):
                    continue
                rows.append({"cik": f"{int(r['cik']):010d}" if r["cik"] else r["symbol"], "ticker": r["symbol"], "date": pd.Timestamp(r["date"][:10]),
                             **call_features(r["turns"])})
        bt.log(f"shard {i} done: {len(rows)} calls so far")
    return pd.DataFrame(rows).drop_duplicates(["cik", "date"])


# --- evaluation ---

def evaluate(feats: pd.DataFrame, bars: dict, bench: pd.Series) -> pd.DataFrame:
    """Forward excess returns from each call date with edge/pead.py's no-lookahead entry rule."""
    events = feats[["cik", "ticker", "date"]].rename(columns={"date": "filed"})
    ev = pead.evaluate(events, bars, bench, horizons=HORIZONS)
    keep = [c for c in feats.columns if c not in ("cik", "ticker", "date")]
    return pd.concat([ev.reset_index(drop=True), feats[keep].reset_index(drop=True)], axis=1)


def partial_ic(ev: pd.DataFrame, feature: str, outcome: str, control: str = "ear") -> pd.Series:
    """Rank IC per quarter after removing what the call-day reaction (EAR) explains of the outcome."""
    g = ev[ev[[feature, outcome, control]].notna().all(axis=1)]
    out = {}
    for q, gq in g.groupby("quarter"):
        if len(gq) < 30:
            continue
        y, x, c = gq[outcome].rank(), gq[feature].rank(), gq[control].rank()
        beta = np.cov(y, c)[0, 1] / np.var(c, ddof=1)
        out[q] = x.corr(y - beta * c)
    return pd.Series(out, dtype=float)


def _ic(ev, feature, outcome):
    return textchg.rank_ic_by_quarter(ev, feature, outcome)


def _row(ev: pd.DataFrame, feat: str, h: int) -> str:
    col = f"excess_{h}d"
    ic = _ic(ev, feat, col)
    pic = partial_ic(ev, feat, col)
    return f"{ic.mean():+.3f} (t {textchg._t(ic):.1f}) | {pic.mean():+.3f} (t {textchg._t(pic):.1f})"


def report(ev: pd.DataFrame, n_companies: int) -> str:
    oos_start = pd.Timestamp(OOS_START)
    liquid = ev[ev["liquid"] & ev["call_score"].notna() & ev["entry_date"].astype(bool)].copy()
    liquid["q"] = textchg.quintile_by_quarter(liquid, "call_score")
    parts = {"In sample (2017-21)": liquid[liquid["filed"] < oos_start], "Out of sample (2022 onward)": liquid[liquid["filed"] >= oos_start]}
    L = ["# Earnings-call language and delivery as a signal (US large caps)", "",
         f"Source: free Hugging Face transcript set of S&P 500 calls, text only. Companies: {n_companies}; calls 2017 onward with a score "
         f"and a price history: {len(ev['call_score'].dropna())}; liquid (20-day ADV >= ${config.PEAD_MIN_ADV / 1e6:g}m, price >= ${config.PEAD_MIN_PRICE:g}) "
         f"and scored: {len(liquid)}.", "",
         "Features are changes against the company's own previous four calls. The pre-set score averages quarterly ranks of: "
         "Q&A tone (+), Q&A uncertainty (-), Q&A hedging (-), Q&A disfluency (-), Q&A-minus-prepared tone gap (+), analyst question tone (+). "
         "Outcomes are excess returns over SPY from entry two closes after the first close following the call date. "
         "IC = quarterly Spearman rank correlation of the feature with the outcome, t-statistic across quarters; "
         "the second column removes what the call-day reaction (EAR) explains.", ""]
    stats = {}
    for name, g in parts.items():
        L += [f"## {name}: {len(g)} calls", "", "| quintile of score | n | " + " | ".join(f"{h}d excess" for h in HORIZONS) + " |",
              "|---|---|" + "---|" * len(HORIZONS)]
        for k in range(1, 6):
            gk = g[g["q"] == k]
            cells = []
            for h in HORIZONS:
                x = gk[f"excess_{h}d"].dropna()
                t, _ = pead.monthly_t(gk[f"excess_{h}d"], pd.to_datetime(gk["entry_date"]).dt.to_period("M"))
                cells.append(f"{op._wmean(x):+.2%} (t {t:.1f})" if len(x) >= 10 else "n/a")
            L.append(f"| Q{k}{' (calmest, most upbeat)' if k == 5 else ' (most hedged, flat)' if k == 1 else ''} | {len(gk)} | " + " | ".join(cells) + " |")
        L.append("")
        ps = {}
        for h in HORIZONS:
            col = f"excess_{h}d"
            q5, q1 = g[(g["q"] == 5) & g[col].notna()], g[(g["q"] == 1) & g[col].notna()]
            m5 = pd.to_datetime(q5["entry_date"]).dt.to_period("M")
            top = q5.groupby(m5)[col].mean()
            bot = q1.groupby(pd.to_datetime(q1["entry_date"]).dt.to_period("M"))[col].mean()
            sp = (top - bot).dropna()
            ps[h] = {"n_q5": len(q5), "q5_gross": op._wmean(q5[col]) if len(q5) else float("nan"),
                     "q5_net": op._wmean(q5[col] - q5["cost"]) if len(q5) else float("nan"),
                     "q5_net_t": pead.monthly_t(q5[col] - q5["cost"], m5)[0],
                     "q5_stress": op._wmean(q5[col] - config.ROUND_TRIP_COST) if len(q5) else float("nan"),
                     "ls": float(sp.mean()) if len(sp) else float("nan"), "ls_t": textchg._t(sp)}
        stats[name] = ps
        L += ["| rule | " + " | ".join(f"{h}d" for h in HORIZONS) + " |", "|---|" + "---|" * len(HORIZONS),
              "| Q5 long, net of realistic cost | " + " | ".join(f"{ps[h]['q5_net']:+.2%} (t {ps[h]['q5_net_t']:.1f})" for h in HORIZONS) + " |",
              f"| Q5 long, net of {config.ROUND_TRIP_COST:.1%} | " + " | ".join(f"{ps[h]['q5_stress']:+.2%}" for h in HORIZONS) + " |",
              "| Q5 minus Q1, before costs (monthly) | " + " | ".join(f"{ps[h]['ls']:+.2%} (t {ps[h]['ls_t']:.1f})" for h in HORIZONS) + " |", ""]
    L += ["## Each feature on its own (exploratory; six features and three horizons, so expect one or two |t| above 2 by luck)", ""]
    for name, g in {"In sample": ev[(ev["liquid"]) & (ev["filed"] < oos_start)], "Out of sample": ev[(ev["liquid"]) & (ev["filed"] >= oos_start)]}.items():
        L += [f"**{name}**, IC with 20d / 60d excess return, raw | after removing EAR", "",
              "| feature | 20d raw | 20d after EAR | 60d raw | 60d after EAR |", "|---|---|---|---|---|"]
        for f in list(SCORE_PARTS) + ["call_score"]:
            r20, r60 = _row(g, f, 20), _row(g, f, 60)
            L.append(f"| {f} | {r20.split(' | ')[0]} | {r20.split(' | ')[1]} | {r60.split(' | ')[0]} | {r60.split(' | ')[1]} |")
        L.append("")
    oos = list(stats.values())[-1][60]
    L += ["## Verdict", "", f"Pre-set rule: buy the top score quintile, hold 60 days, judged out of sample. " + pead.verdict(oos), "",
          "Caveats: text only (no pauses or pitch); survivorship (today's S&P 500 members, so failures and deletions are missing); "
          "transcripts are polished by the vendor, so fillers are mostly stripped; call dates carry no reliable timezone so entry is "
          "deliberately late (two closes after the first close following the call day); overlapping trades make the t-statistics "
          "optimistic. Not financial advice."]
    return "\n".join(L)


def main() -> None:
    t0 = time.monotonic()
    feats = add_changes(load_calls(Path("/tmp/calls_cache")))
    feats = feats[feats["date"] >= pd.Timestamp(FIRST_EVENT)].reset_index(drop=True)
    bt.log(f"{len(feats)} calls from {feats['cik'].nunique()} companies; features in {(time.monotonic() - t0) / 60:.1f} min; fetching prices")
    syms = {prices.yahoo_symbol(t, "us") for t in feats["ticker"].unique()} | {config.PEAD_BENCHMARK}
    bars = bt.prefetch(syms, prices.fetch_bars)
    ev = evaluate(feats, bars, bars[config.PEAD_BENCHMARK]["close"])
    ev = add_score(ev)
    config.REPORTS_DIR.mkdir(exist_ok=True)
    ev.drop(columns=["quarter"]).to_csv(config.REPORTS_DIR / "calls_events.csv.gz", index=False)
    text = report(ev, feats["cik"].nunique())
    (config.REPORTS_DIR / "calls_study.md").write_text(text + "\n")
    print(text)
