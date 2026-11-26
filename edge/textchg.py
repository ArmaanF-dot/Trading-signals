"""10-K and 10-Q wording changes as an earnings and drift signal, from free SEC EDGAR text.

Idea (Cohen, Malloy and Nguyen, "Lazy Prices", 2020): companies that rewrite their periodic reports
a lot, or whose tone turns more negative, tend to do worse afterwards; investors do not read the
filings. For each 10-K or 10-Q we compare the text with the same company's filing of the same form
about a year earlier (the same quarter, so seasonality cancels).

Features (all known the day the filing appears on EDGAR):
- sim: cosine similarity of word-count vectors (1.0 = identical wording; low = a lot of rewriting);
- d_tone: change in tone, where tone = (positive - negative words) / words from a small finance
  word list in this file (a short list written for this study, not the Loughran-McDonald list, which
  is not freely redistributable); d_unc: the same for uncertainty words;
- d_len: log change in length.
There is no language-model key on GitHub Actions, so "scoring" here is similarity plus word lists,
not a model reading the text. A model score would need a paid key and re-running 20,000 filings.

Outcomes: excess return over SPY from entry (PEAD_ENTRY_LAG closes after the first close following
the filing) over 20 and 60 days, and the earnings-day reaction (EAR) of the company's next earnings
8-K (taken from reports/pead_events.csv.gz). Costs, liquidity filters and no-lookahead rules follow
edge/pead.py. Survivorship: today's SEC ticker list. The rule (long the least-changed filings)
was fixed before the run, from the Lazy Prices paper.
"""
import datetime as dt
import html
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

import config
from edge import pead, prices
from edge.form4 import backtest as bt
from edge.form4 import opportunistic as op

HORIZONS = (20, 60)
FIRST_FILING = "2017-01-01"  # prior-year comparison therefore needs filings from 2016, fetched too
FETCH_FROM = "2016-01-01"
UNIVERSE_SIZE = 700  # most liquid companies by median 20-day dollar volume
TIME_BUDGET_S = 4 * 3600  # stop reading filings after this and report what exists
FORMS = ("10-K", "10-Q")

NEG = set("""adverse adversely against allegation allegations breach claims closure closures concern concerns
curtail curtailed decline declined declines declining decrease decreased default deficiency deficiencies delay
delayed delays deteriorate deteriorated deterioration difficult difficulties difficulty diminish disruption
disruptions dispute disputes downturn fail failed failure failures harm harmed impair impaired impairment
inability ineffective inefficient insolvency investigation lawsuit lawsuits layoffs loss losses negative
negatively penalties problem problems recall restructuring restate restated restatement severe shortfall
shortage shortages slowdown suffer terminate terminated termination threat unable unfavorable unfavourable
volatile volatility weak weakness weaker worsen worsened writedown writeoff""".split())
POS = set("""achieve achieved attain benefit benefits best better effective efficient enhance enhanced excellent
favorable favourable gain gains good greater growth improve improved improvement improvements improving
increase increased innovative leading opportunity opportunities outperform profitable profitability record
resilient robust solid strength strengthen strengthened strong stronger succeed success successful
successfully surpass""".split())
UNC = set("""approximately assume believe could depend depends doubt estimate estimates fluctuate fluctuations
indefinite may might possible possibly predict probable probably risk risks risky roughly uncertain
uncertainties uncertainty unclear unknown unpredictable unproved variability volatile""".split())

_WORD = re.compile(r"[a-z]{3,}")
_TABLE = re.compile(r"<table.*?</table>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")
_HIDDEN = re.compile(r"<ix:header>.*?</ix:header>", re.I | re.S)


def tokens(raw_html: str) -> Counter:
    """Word counts of the narrative text of a filing (tables and XBRL headers removed)."""
    s = _HIDDEN.sub(" ", raw_html)
    s = _TABLE.sub(" ", s)
    s = html.unescape(_TAGS.sub(" ", s)).lower()
    return Counter(_WORD.findall(s))


def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return float("nan")
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    dot = sum(c * big.get(w, 0) for w, c in small.items())
    na = sum(c * c for c in a.values()) ** 0.5
    nb = sum(c * c for c in b.values()) ** 0.5
    return dot / (na * nb) if na and nb else float("nan")


def tone(c: Counter) -> tuple[float, float]:
    n = sum(c.values())
    if n < 2000:
        return float("nan"), float("nan")
    pos = sum(v for w, v in c.items() if w in POS)
    neg = sum(v for w, v in c.items() if w in NEG)
    unc = sum(v for w, v in c.items() if w in UNC)
    return (pos - neg) / n, unc / n


def compare(cur: Counter, prev: Counter) -> dict:
    t0, u0 = tone(prev)
    t1, u1 = tone(cur)
    n0, n1 = sum(prev.values()), sum(cur.values())
    return {"sim": cosine(cur, prev), "d_tone": t1 - t0, "d_unc": u1 - u0,
            "d_len": float(np.log(n1 / n0)) if n0 and n1 else float("nan"), "words": n1}


# --- EDGAR access ---

_lock = threading.Lock()
_next_slot = 0.0


def _throttled_get(url: str) -> requests.Response:
    """GET with a shared rate limit across threads (SEC allows 10 requests a second)."""
    global _next_slot
    delay = 1.0
    for attempt in range(config.HTTP_RETRIES):
        with _lock:
            now = time.monotonic()
            wait = max(0.0, _next_slot - now)
            _next_slot = max(now, _next_slot) + config.SEC_MIN_INTERVAL
        if wait:
            time.sleep(wait)
        try:
            r = requests.get(url, headers={"User-Agent": config.sec_user_agent(), "Accept-Encoding": "gzip, deflate"},
                             timeout=config.HTTP_TIMEOUT)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == config.HTTP_RETRIES - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def periodic_filings(sub: dict, more=None, since: str = FETCH_FROM) -> pd.DataFrame:
    """10-K and 10-Q filings (form, filed date, accession, primary document) from a submissions JSON."""
    blocks = [sub.get("filings", {}).get("recent", {})]
    if more is not None:
        blocks += [more(f["name"]) for f in sub.get("filings", {}).get("files", []) if f.get("filingTo", "9999") >= since]
    frames = []
    for b in blocks:
        if b and b.get("form"):
            frames.append(pd.DataFrame({"form": b["form"], "filed": b["filingDate"], "acc": b["accessionNumber"],
                                        "doc": b["primaryDocument"]}))
    if not frames:
        return pd.DataFrame(columns=["form", "filed", "acc", "doc"])
    out = pd.concat(frames, ignore_index=True)
    out["filed"] = pd.to_datetime(out["filed"], errors="coerce")
    out = out[out["form"].isin(FORMS) & (out["filed"] >= pd.Timestamp(since)) & out["doc"].str.lower().str.endswith((".htm", ".html"))]
    return out.dropna(subset=["filed"]).sort_values("filed").drop_duplicates("acc").reset_index(drop=True)


def filing_url(cik: str, acc: str, doc: str) -> str:
    return f"{config.SEC_BASE}/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}"


def prior_year(fl: pd.DataFrame, i: int) -> int | None:
    """Index of the same-form filing 340-400 days before filing i (a year earlier), if any."""
    r = fl.iloc[i]
    cand = fl[(fl["form"] == r["form"]) & ((r["filed"] - fl["filed"]).dt.days.between(340, 400))]
    return None if cand.empty else int(cand.index[-1])


def company_features(cik: str, ticker: str, fl: pd.DataFrame, fetch_text, since: str = FIRST_FILING) -> list[dict]:
    """Features for every filing since `since` that has a prior-year filing of the same form.
    `fetch_text(url)` returns the filing's HTML. Keeps the word counts of the last two years in memory only."""
    cache: dict[int, Counter] = {}
    rows = []

    def counts(i: int) -> Counter:
        if i not in cache:
            r = fl.iloc[i]
            cache[i] = tokens(fetch_text(filing_url(cik, r["acc"], r["doc"])))
        return cache[i]

    for i in range(len(fl)):
        r = fl.iloc[i]
        if r["filed"] < pd.Timestamp(since):
            continue
        j = prior_year(fl, i)
        if j is None:
            continue
        try:
            rows.append({"cik": cik, "ticker": ticker, "form": r["form"], "filed": r["filed"], **compare(counts(i), counts(j))})
        except Exception as exc:
            bt.log(f"{ticker} {r['form']} {r['filed'].date()}: {type(exc).__name__}: {exc}")
        for k in [k for k in cache if fl.iloc[k]["filed"] < r["filed"] - pd.Timedelta(days=430)]:
            del cache[k]
    return rows


# --- outcomes ---

def next_ear(feats: pd.DataFrame, pead_events: pd.DataFrame) -> pd.Series:
    """EAR of the company's first earnings 8-K filed more than 5 days after each filing (the next report)."""
    pe = pead_events[["cik", "filed", "ear"]].dropna().copy()
    pe["cik"] = pe["cik"].astype(str).str.zfill(10)
    pe["filed"] = pd.to_datetime(pe["filed"])
    by = {c: g.sort_values("filed") for c, g in pe.groupby("cik")}
    out = []
    for r in feats.itertuples(index=False):
        g = by.get(r.cik)
        nxt = None if g is None else g[g["filed"] > r.filed + pd.Timedelta(days=5)]
        out.append(float(nxt["ear"].iloc[0]) if nxt is not None and len(nxt) and (nxt["filed"].iloc[0] - r.filed).days < 130 else np.nan)
    return pd.Series(out, index=feats.index)


def evaluate(feats: pd.DataFrame, bars: dict, bench: pd.Series) -> pd.DataFrame:
    """Forward excess returns from each filing, with the no-lookahead entry rule of edge/pead.py."""
    events = feats[["cik", "ticker", "filed"]]
    ev = pead.evaluate(events, bars, bench, horizons=HORIZONS)
    keep = [c for c in feats.columns if c not in ("cik", "ticker", "filed")]
    return pd.concat([ev.reset_index(drop=True), feats[keep].reset_index(drop=True)], axis=1)


def add_score(ev: pd.DataFrame) -> pd.DataFrame:
    """Pre-set text score: rank of similarity within the quarter (high = unchanged) plus rank of the
    tone change (high = more positive) minus rank of the uncertainty change. Equal weights."""
    ev = ev.copy()
    ev["quarter"] = ev["filed"].dt.to_period("Q")
    r = lambda c: ev.groupby("quarter")[c].rank(pct=True)
    ev["text_score"] = (r("sim") + r("d_tone") + (1 - r("d_unc"))) / 3
    return ev


# --- statistics ---

def rank_ic_by_quarter(ev: pd.DataFrame, feature: str, outcome: str) -> pd.Series:
    g = ev[ev[feature].notna() & ev[outcome].notna()]
    out = {}
    for q, gq in g.groupby("quarter"):
        if len(gq) >= 20:
            out[q] = gq[feature].rank().corr(gq[outcome].rank())
    return pd.Series(out, dtype=float)


def _t(s: pd.Series) -> float:
    s = s.dropna()
    return float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))) if len(s) > 2 and s.std(ddof=1) > 0 else float("nan")


def quintile_by_quarter(ev: pd.DataFrame, col: str, k: int = 5) -> pd.Series:
    """1..k within each quarter by `col` (events in the same quarter are ranked together)."""
    pct = ev.groupby("quarter")[col].rank(pct=True, method="first")
    return np.ceil(pct * k).clip(1, k)


def report(ev: pd.DataFrame, n_companies: int) -> str:
    oos_start = pd.Timestamp(config.PEAD_OOS_START)
    stress = config.ROUND_TRIP_COST
    feats = {"sim": "Similarity to last year's filing", "d_tone": "Tone change (positive minus negative)",
             "d_unc": "Uncertainty-word change", "d_len": "Length change", "text_score": "Combined text score (pre-set)"}
    outs = {"ear_next": "Next earnings-day reaction", "excess_20d": "Drift 20d", "excess_60d": "Drift 60d"}
    L = ["# 10-K and 10-Q text changes (Lazy Prices style)", "",
         f"Companies: {n_companies} (most liquid on NYSE/Nasdaq, today's SEC list). Filings compared with the same company's "
         f"filing a year earlier: {len(ev)}; with a price outcome: {int(ev['excess_60d'].notna().sum())}. "
         "Wording is scored by similarity and short word lists, not by a language model (see the module note).", ""]
    for name, g in (("In sample (2017-21)", ev[ev["filed"] < oos_start]), ("Out of sample (2022 onward)", ev[ev["filed"] >= oos_start])):
        L += [f"## {name}: {len(g)} filings", "", "Rank correlation (IC) within each quarter, averaged; t across quarters. "
              "Positive = higher feature goes with a better outcome.", "",
              "| feature | " + " | ".join(outs.values()) + " |", "|---|" + "---|" * len(outs)]
        for f, fn in feats.items():
            cells = []
            for o in outs:
                ic = rank_ic_by_quarter(g, f, o)
                cells.append("n/a" if len(ic) < 3 else f"{ic.mean():+.3f} (t {_t(ic):.1f})")
            L.append(f"| {fn} | " + " | ".join(cells) + " |")
        liq = g[g["liquid"] & g["text_score"].notna()].copy()
        liq["q"] = quintile_by_quarter(liq, "text_score")
        L += ["", "Liquid filings by combined text score quintile (Q5 = least change and best tone), excess over SPY, "
              f"net of {stress:.1%} (monthly-average t):", "", "| quintile | n | 20d | 60d |", "|---|---|---|---|"]
        for k in range(1, 6):
            gk = liq[liq["q"] == k]
            cells = []
            for h in HORIZONS:
                x = (gk[f"excess_{h}d"] - stress).dropna()
                if len(x) < 10:
                    cells.append("n/a")
                    continue
                t, _ = pead.monthly_t(gk[f"excess_{h}d"] - stress, pd.to_datetime(gk["entry_date"]).dt.to_period("M"))
                cells.append(f"{op._wmean(x):+.2%} (t {t:.1f})")
            L.append(f"| Q{k} | {len(gk)} | " + " | ".join(cells) + " |")
        top, bot = liq[liq["q"] == 5], liq[liq["q"] == 1]
        spread = [(top[f"excess_{h}d"].mean() - bot[f"excess_{h}d"].mean()) for h in HORIZONS]
        L += ["", f"Q5 minus Q1 before costs: 20d {spread[0]:+.2%}, 60d {spread[1]:+.2%}.", ""]
    L += ["## Verdict", "", "VERDICT_PLACEHOLDER", "",
          "Caveats: survivorship (today's ticker list); word lists are a crude stand-in for a language model; "
          "10-Qs often come out the same day as the earnings 8-K, so part of any move is the earnings news itself, "
          "which the entry lag only partly removes; overlapping returns make the t-statistics too generous. Not financial advice."]
    return "\n".join(L)


def verdict(ev: pd.DataFrame) -> str:
    oos = ev[(ev["filed"] >= pd.Timestamp(config.PEAD_OOS_START)) & ev["liquid"] & ev["text_score"].notna()].copy()
    if len(oos) < 300:
        return "Too few out-of-sample filings to judge."
    oos["q"] = quintile_by_quarter(oos, "text_score")
    q5, q1 = oos[oos["q"] == 5], oos[oos["q"] == 1]
    net = (q5["excess_60d"] - config.ROUND_TRIP_COST).dropna()
    t, _ = pead.monthly_t(q5["excess_60d"] - config.ROUND_TRIP_COST, pd.to_datetime(q5["entry_date"]).dt.to_period("M"))
    gross_spread = q5["excess_60d"].mean() - q1["excess_60d"].mean()
    if len(net) and net.mean() > 0 and t >= 2:
        return "Edge: unchanged, positive-toned filings beat SPY out of sample after costs with t >= 2."
    if gross_spread > 0:
        return "There is a small gap between the most and least changed filings, but it is too small to trade after costs: no tradeable edge."
    return "No edge: out of sample, filings with more rewriting and a worse tone did not lag, and the least-changed ones did not beat SPY after costs."


def main() -> None:
    t0 = time.monotonic()
    uni = pead.universe(pead.sec_json(config.SEC_TICKERS_EXCHANGE_URL))
    pev = pd.read_csv(config.REPORTS_DIR / "pead_events.csv.gz", dtype={"cik": str})
    adv = pev.groupby("cik")["adv"].median()
    uni = uni.assign(adv=uni["cik"].map(adv)).dropna(subset=["adv"]).sort_values("adv", ascending=False).head(UNIVERSE_SIZE)
    bt.log(f"{len(uni)} companies; reading 10-K/10-Q text from EDGAR")

    def work(r) -> list[dict]:
        if time.monotonic() - t0 > TIME_BUDGET_S:
            return []
        try:
            sub = pead.sec_json(config.SEC_SUBMISSIONS_URL.format(cik=r.cik))
            fl = periodic_filings(sub, lambda name: pead.sec_json(config.SEC_SUBMISSIONS_FILE_URL.format(name=name)))
            return company_features(r.cik, r.ticker, fl, lambda u: _throttled_get(u).text)
        except Exception as exc:
            bt.log(f"{r.ticker}: {type(exc).__name__}: {exc}")
            return []

    rows = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, res in enumerate(ex.map(work, list(uni.itertuples(index=False))), 1):
            rows += res
            if i % 25 == 0:
                bt.log(f"{i}/{len(uni)} companies, {len(rows)} filings scored, {(time.monotonic() - t0) / 60:.0f} min")
    feats = pd.DataFrame(rows)
    syms = {prices.yahoo_symbol(t, "us") for t in feats["ticker"].unique()} | {config.PEAD_BENCHMARK}
    bars = bt.prefetch(syms, prices.fetch_bars)
    ev = evaluate(feats, bars, bars[config.PEAD_BENCHMARK]["close"])
    ev["ear_next"] = next_ear(ev, pev).values
    ev = add_score(ev)
    config.REPORTS_DIR.mkdir(exist_ok=True)
    ev.drop(columns=["quarter"]).to_csv(config.REPORTS_DIR / "text_events.csv.gz", index=False)
    text = report(ev, uni["ticker"].nunique()).replace("VERDICT_PLACEHOLDER", verdict(ev))
    (config.REPORTS_DIR / "text_study.md").write_text(text + "\n")
    print(text)
