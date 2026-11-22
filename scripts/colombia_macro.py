"""Can Colombian insolvency data time Colombian equities a UK retail account can trade?

Firm-level insolvency filings (Supersociedades, Ley 1116) almost never hit a listed,
UK-tradeable company, so the only usable trade is aggregate: rising corporate
insolvencies -> underweight Colombia. This tests that on the three NYSE ADRs a UK
retail account can buy or spread bet (CIB, EC, AVAL), hedged with EEM, out of sample.

Signals (all lagged so they were public before the trade):
  biz_adm  : monthly count of Ley 1116 admissions by true admission date (co_events.adm),
             known one month later.
  biz_new  : firms appearing for the first time in each published Supersociedades base,
             per month covered, known the month after the cut-off.
  personal : personal (non-trader) insolvency proceedings per month (co_insolvencia.csv),
             known two months later.
Each signal is the year-on-year growth of its trailing 3-month total.

Rules: short the ADR basket against EEM when growth > theta (short-only), or also go
long when growth < -theta (long-short). Hold one month, rebalance monthly.
Costs: each unit change in the pair position costs half the round trip.
Variant chosen on in-sample net Sharpe at 2.5%; then reported out of sample.

Usage: python colombia_macro.py data/colombia  (reads insolvency_monthly_counts.csv)
"""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "data/colombia")
SPLIT = pd.Period("2023-01", "M")  # first out-of-sample month
COSTS = [0.0, 0.005, 0.02, 0.025, 0.03]
PICK_COST = 0.025
ADRS = ["CIB", "EC", "AVAL"]
UA = {"User-Agent": "Mozilla/5.0 (research script)"}


def yahoo(sym: str, interval: str = "1mo", p1: int = 1262304000, p2: int | None = None) -> pd.Series:
    p2 = p2 or int(time.time())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?period1={p1}&period2={p2}&interval={interval}&events=div,split")
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                j = json.load(r)["chart"]["result"][0]
            break
        except Exception as ex:  # noqa: BLE001
            print("yahoo retry", sym, ex)
            time.sleep(3 * (i + 1))
    else:
        return pd.Series(dtype=float)
    ts = pd.to_datetime(j["timestamp"], unit="s")
    adj = j["indicators"].get("adjclose", [{}])
    px = adj[0].get("adjclose") if adj else None
    px = px or j["indicators"]["quote"][0]["close"]
    s = pd.Series(px, index=ts, dtype=float).dropna()
    if interval == "1mo":
        s.index = s.index.to_period("M")
        s = s.groupby(level=0).last()
    return s


def signals() -> pd.DataFrame:
    """Build lagged growth signals from the published monthly counts (no firm-level data)."""
    c = pd.read_csv(OUT / "insolvency_monthly_counts.csv", index_col=0)
    c.index = pd.PeriodIndex(c.index, freq="M")

    def growth(s: pd.Series, lag: int) -> pd.Series:
        s = s.dropna()
        idx = pd.period_range(s.index.min(), s.index.max(), freq="M")
        s = s.reindex(idx, fill_value=0).astype(float)
        t3 = s.rolling(3).sum()
        g = t3 / t3.shift(12) - 1
        g.index = g.index + lag
        return g.replace([np.inf, -np.inf], np.nan)

    return pd.DataFrame({
        "biz_adm": growth(c["biz_adm_count"], 1),
        "biz_new": growth(c["biz_new_per_month"], 1),
        "personal": growth(c["personal_count"], 2),
    })


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 6:
        return {"n": len(r)}
    mu, sd = r.mean(), r.std()
    eq = (1 + r).cumprod()
    return {
        "n": len(r),
        "ann_ret": float((eq.iloc[-1]) ** (12 / len(r)) - 1),
        "sharpe": float(mu / sd * math.sqrt(12)) if sd > 0 else float("nan"),
        "t": float(mu / sd * math.sqrt(len(r))) if sd > 0 else float("nan"),
        "max_dd": float((eq / eq.cummax() - 1).min()),
        "months_in": int((r != 0).sum()),
    }


def run_rule(sig: pd.Series, pair: pd.Series, theta: float, mode: str, cost: float) -> pd.Series:
    d = pd.DataFrame({"s": sig, "r": pair}).dropna()
    pos = np.where(d.s > theta, -1.0, 0.0)
    if mode == "long-short":
        pos = np.where(d.s < -theta, 1.0, pos)
    pos = pd.Series(pos, index=d.index)
    turn = pos.diff().abs().fillna(pos.abs())
    return pos * d.r - turn * cost / 2


def ic(sig: pd.Series, fwd: pd.Series) -> dict:
    d = pd.DataFrame({"s": sig, "f": fwd}).dropna()
    if len(d) < 8:
        return {"n": len(d)}
    rho = d.s.rank().corr(d.f.rank())
    return {"n": len(d), "spearman": float(rho), "t": float(rho * math.sqrt((len(d) - 2) / max(1e-9, 1 - rho**2)))}


def canacol() -> dict:
    """Did the Supersociedades record lead or lag the market for the one tradeable name?"""
    s = yahoo("CNE.TO", "1d", 1735689600, 1772323200)  # 2025-01-01 .. 2026-03-01
    if s.empty:
        return {"error": "no prices"}
    s.index = s.index.normalize()

    def at(d: str) -> float | None:
        x = s[:d]
        return round(float(x.iloc[-1]), 3) if len(x) else None

    worst_day = s.pct_change().idxmin()
    return {
        "close_2025_01_02": at("2025-01-02"),
        "close_2025_06_30": at("2025-06-30"),
        "close_2025_10_31": at("2025-10-31"),
        "close_day_before_admission_2025_11_26": at("2025-11-26"),
        "close_admission_2025_11_27": at("2025-11-27"),
        "close_when_first_in_published_base_2026_01_10": at("2026-01-10"),
        "close_last": at("2026-03-01"),
        "worst_day": str(worst_day.date()),
        "worst_day_return": round(float(s.pct_change().min()), 3),
        "fall_2025_01_to_day_before_admission": round(at("2025-11-26") / at("2025-01-02") - 1, 3),
    }


def main() -> None:
    sig = signals()
    px = pd.DataFrame({k: yahoo(k) for k in ADRS + ["EEM", "SPY", "COP=X"]})
    px = px[px.index >= pd.Period("2015-01", "M")]
    ret = px.pct_change(fill_method=None)
    basket = ret[ADRS].mean(axis=1, skipna=True)
    pair = basket - ret["EEM"]  # long Colombia ADR basket, short EEM
    fwd3 = pair.rolling(3).sum().shift(-2)
    cop = ret["COP=X"]  # + = peso weakens

    variants = []
    for src in sig.columns:
        for theta in (0.0, 0.1, 0.2, 0.3):
            for mode in ("short-only", "long-short"):
                r_is = run_rule(sig[src], pair, theta, mode, PICK_COST)
                r_is = r_is[r_is.index < SPLIT]
                st = stats(r_is)
                variants.append({"source": src, "theta": theta, "mode": mode, **{f"is_{k}": v for k, v in st.items()}})
    var = pd.DataFrame(variants)
    best = var.sort_values("is_sharpe", ascending=False).iloc[0]

    res = {"chosen": {k: best[k] for k in ("source", "theta", "mode")}, "periods": {}}
    for name, lo, hi in (("in_sample", None, SPLIT), ("out_of_sample", SPLIT, None)):
        block = {}
        for c in COSTS:
            r = run_rule(sig[best.source], pair, best.theta, best["mode"], c)
            r = r[(r.index >= lo) if lo is not None else r.index == r.index]
            r = r[(r.index < hi) if hi is not None else r.index == r.index]
            block[f"net_{c}"] = stats(r)
            if c == PICK_COST:
                r.index = r.index.astype(str)
                r.to_csv(Path("reports") / f"colombia_macro_{name}_monthly.csv", header=["ret"])
        pr = pair[(pair.index >= lo) if lo is not None else pair.index == pair.index]
        pr = pr[(pr.index < hi) if hi is not None else pr.index == pr.index]
        block["passive_long_basket_vs_eem"] = stats(pr.loc[sig[best.source].dropna().index.intersection(pr.index)])
        res["periods"][name] = block

    ics = {}
    for src in sig.columns:
        for name, mask in (("in_sample", sig.index < SPLIT), ("out_of_sample", sig.index >= SPLIT)):
            s = sig[src][mask]
            ics[f"{src}|{name}|pair_next1m"] = ic(s, pair)
            ics[f"{src}|{name}|pair_next3m"] = ic(s, fwd3)
            ics[f"{src}|{name}|usdcop_next1m"] = ic(s, cop)
    res["ic"] = ics
    res["variants_in_sample"] = var.round(4).to_dict("records")
    res["coverage"] = {
        "signal_first": {c: str(sig[c].first_valid_index()) for c in sig},
        "signal_last": {c: str(sig[c].last_valid_index()) for c in sig},
        "prices_first": {c: str(px[c].first_valid_index()) for c in px},
        "prices_last": str(px.index.max()),
    }
    res["canacol"] = canacol()
    (Path("reports") / "colombia_macro.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: res[k] for k in ("chosen", "periods", "canacol", "coverage")}, indent=1, default=str))
    for k, v in ics.items():
        print(k, v)


if __name__ == "__main__":
    main()
