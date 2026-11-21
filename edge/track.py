"""Forward track record: what the live signals actually did after they fired (the only validation
that is free of survivorship bias). Returns are gross; the benchmark return covers the same dates."""
import pandas as pd

import config
from edge import store
from edge.form4.opportunistic import _wmean

SOURCES = [("Form 4 clusters", config.FORM4_CLUSTERS_CSV, 0.025), ("FCA short changes", config.FCA_EVENTS_CSV, 0.017),
           ("UK combo", config.COMBO_CSV, 0.017)]


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


def build() -> str:
    L = ["# Forward track record", "", "Live signals only, measured from the first close after they became public. "
         "Costs are the same assumptions as the backtests. Not financial advice.", ""]
    for label, path, cost in SOURCES:
        L += table(label, store.read_csv(path), cost)
    return "\n".join(L)


def run() -> str:
    text = build()
    config.TRACK_RECORD_MD.write_text(text + "\n")
    return text
