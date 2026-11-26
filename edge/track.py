"""Forward track record: what the live signals actually did after they fired (the only validation
that is free of survivorship bias). Returns are gross; the benchmark return covers the same dates.

Each source also gets a risk-adjusted record (Sharpe, volatility, max drawdown and a leverage-sizing line, see
edge/risk.py), written to signals/track_record.json for Baco as well as to the markdown."""
import json

import pandas as pd

import config
from edge import risk, store
from edge.form4.opportunistic import _wmean

# label, file, assumed round-trip cost, column with the date the signal became public, traded side
SOURCES = [("Form 4 clusters", config.FORM4_CLUSTERS_CSV, 0.025, "public_date", "long"),
           ("FCA short changes", config.FCA_EVENTS_CSV, 0.017, "date", "short"),
           ("UK combo", config.COMBO_CSV, 0.017, "signal_date", "long")]
TRACK_JSON = config.SIGNALS_DIR / "track_record.json"


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def table(label: str, df: pd.DataFrame, cost: float) -> list[str]:
    if df.empty or "ret_20d" not in df:
        return [f"### {label}", "", "No signals logged yet.", ""]
    r20, b20 = _num(df["ret_20d"]), _num(df.get("bench_ret_20d", pd.Series(dtype=float)))
    done = df.assign(r=r20, b=b20.reindex(df.index))[r20.notna()]
    out = [f"### {label}", "", f"Signals logged: {len(df)}. With a 20-day return: {len(done)}."]
    if len(done) < config.MIN_TRACK_N:
        return out + [f"Too few to read anything into (need {config.MIN_TRACK_N}).", ""]
    net = done["r"] - cost
    ex = (done["r"] - done["b"]).dropna() - cost
    out += ["", "| measure | value |", "|---|---|", f"| mean 20d return (net of assumed {cost:.1%} cost, winsorised) | {_wmean(net):.1%} |",
            f"| median net | {net.median():.1%} |", f"| share positive after cost | {(net > 0).mean():.0%} |"]
    if len(ex):
        out.append(f"| mean net excess vs benchmark | {_wmean(ex):.1%} |")
    return out + [""]


def traded(df: pd.DataFrame, side: str) -> pd.DataFrame:
    """Rows as they would be traded: FCA events keep only rises, shorted (the avoid flag taken as a trade)."""
    if side == "short" and "delta_pp" in df:
        df = df[_num(df["delta_pp"]) > 0]
    return df


def record(label: str, df: pd.DataFrame, cost: float, date_col: str, side: str) -> dict:
    """Risk-adjusted record of one live source: monthly cohorts of 20-day trades, net of the assumed cost."""
    label = "FCA short rises, shorted" if side == "short" else label
    base = {"signal": label, "side": side, "cost": cost, "logged": int(len(df)), "priced": 0, "ready": False}
    if df.empty or "ret_20d" not in df:
        return {**base, "sizing": {"leverage": 0.0, "text": "None: no signals logged yet."}}
    df = traded(df, side)
    date = df[date_col] if date_col in df else df.get("signal_date", pd.Series(index=df.index, dtype=object))
    sign = -1.0 if side == "short" else 1.0
    r, b = _num(df["ret_20d"]), _num(df.get("bench_ret_20d", pd.Series(index=df.index, dtype=float)))
    priced = int(r.notna().sum())
    if priced < config.MIN_TRACK_N:
        return {**base, "logged": int(len(df)), "priced": priced, "sizing": {
            "leverage": 0.0, "text": f"None: {priced} priced signals, too few to judge (need {config.MIN_TRACK_N})."}}
    row = risk.assess(label, "", risk.cohort_series(date, sign * r - cost), risk.cohort_series(date, sign * (r - b) - cost))
    row["period"] = f"{row['edge'].get('n', 0)} months"
    return {**base, **row, "logged": int(len(df)), "priced": priced, "ready": True}


def risk_lines(recs: list[dict]) -> list[str]:
    L = ["## Risk-adjusted record", "",
         "Monthly cohorts of 20-day trades after the assumed cost; FCA rises taken as shorts. Edge is the excess over the "
         "benchmark (IWM for US, the UK index ETF for UK). " + risk.GUIDANCE, ""]
    ready = [r for r in recs if r["ready"]]
    if ready:
        L += risk.table(ready, "signal") + [""]
    L += [f"- **{r['signal']}**: {r['sizing']['text']}" for r in recs]
    return L + [""]


def build(recs: list[dict] | None = None) -> str:
    L = ["# Forward track record", "", "Live signals only, measured from the first close after they became public. "
         "Costs are the same assumptions as the backtests. Not financial advice.", ""]
    for label, path, cost, *_ in SOURCES:
        L += table(label, store.read_csv(path), cost)
    return "\n".join(L + risk_lines(recs if recs is not None else records()))


def records() -> list[dict]:
    return [record(label, store.read_csv(path), cost, col, side) for label, path, cost, col, side in SOURCES]


def run() -> str:
    recs = records()
    text = build(recs)
    config.TRACK_RECORD_MD.write_text(text + "\n")
    TRACK_JSON.write_text(json.dumps({"guidance": risk.GUIDANCE, "min_signals": config.MIN_TRACK_N,
                                      "signals": [risk.clean(r) for r in recs]}, indent=1) + "\n")
    return text
