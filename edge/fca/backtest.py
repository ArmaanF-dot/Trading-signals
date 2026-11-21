"""Event study of FCA aggregate net short changes (reconstructed from the archived named positions).

For every ISIN we rebuild the aggregate short from each holder's disclosures, find the days the
aggregate moved by >= FCA_RISE_PP, treat the move as public after FCA_PUBLICATION_LAG_BDAYS business
days, enter at the next close and measure forward returns versus a UK index ETF. Costs include
stamp duty and a liquidity-tiered spread (assumed). Reports both what a long-only holder earns
(net) and the cost-free excess return, because the likely use is as an avoid/short-side signal.
"""
import numpy as np
import pandas as pd

import config
from edge import http, prices
from edge.form4 import backtest as bt
from edge.form4 import opportunistic as op
from edge.fca import isin_map

COLS = ["holder", "issuer", "isin", "pct", "date", "end", "sheet"]


def _find(cols, *needles):
    for c in cols:
        if any(n in c for n in needles):
            return c
    return None


def parse_sheet(raw: pd.DataFrame, sheet: str) -> pd.DataFrame:
    raw = raw.fillna("")
    hdr = next((i for i in range(min(len(raw), 30)) if any(str(v).strip().lower() == "isin" for v in raw.iloc[i])), None)
    if hdr is None:
        return pd.DataFrame(columns=COLS)
    cols = [str(v).strip().lower() for v in raw.iloc[hdr]]
    body = raw.iloc[hdr + 1:].copy()
    body.columns = cols
    m = {"holder": _find(cols, "holder"), "issuer": _find(cols, "issuer", "name of company"), "isin": _find(cols, "isin"),
         "pct": _find(cols, "net short position", "(%)"), "end": _find(cols, "historical", "end"), "date": None}
    m["date"] = next((c for c in cols if "position date" in c and c != m["end"]), None)
    if None in (m["holder"], m["isin"], m["pct"], m["date"]):
        raise ValueError(f"unrecognised columns in sheet {sheet}: {cols}")
    out = pd.DataFrame({"holder": body[m["holder"]].astype(str).str.strip(), "issuer": body[m["issuer"]].astype(str).str.strip() if m["issuer"] else "",
                        "isin": body[m["isin"]].astype(str).str.strip().str.upper(),
                        "pct": pd.to_numeric(body[m["pct"]], errors="coerce"),
                        "date": pd.to_datetime(body[m["date"]], dayfirst=True, errors="coerce"),
                        "end": pd.to_datetime(body[m["end"]], dayfirst=True, errors="coerce") if m["end"] else pd.NaT,
                        "sheet": sheet})
    return out[(out["isin"] != "") & out["pct"].notna() & out["date"].notna()].reset_index(drop=True)


def load_archive(source) -> pd.DataFrame:
    sheets = pd.read_excel(source, sheet_name=None, header=None, dtype=str)
    frames = []
    for name, raw in sheets.items():
        if "disclosure" in name.lower():
            df = parse_sheet(raw, name)
            bt.log(f"sheet {name!r}: {len(df)} rows, dates {df['date'].min()} to {df['date'].max()}, end column present: {df['end'].notna().any()}")
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLS)


def intervals(pos: pd.DataFrame) -> pd.DataFrame:
    """valid_from / valid_to per disclosure: its 'end' date if given, else the holder's next disclosure
    on that ISIN, else (current sheet) open-ended. A last historic row with no end date is dropped."""
    p = pos.sort_values(["holder", "isin", "date"]).copy()
    nxt = p.groupby(["holder", "isin"])["date"].shift(-1)
    p["valid_to"] = p["end"].fillna(nxt)
    open_ended = p["valid_to"].isna() & p["sheet"].str.lower().str.contains("current")
    p.loc[open_ended, "valid_to"] = pd.Timestamp.max.normalize()
    return p[p["valid_to"].notna() & (p["valid_to"] > p["date"])].rename(columns={"date": "valid_from"})


def aggregate_events(iv: pd.DataFrame, rise_pp: float = config.FCA_RISE_PP) -> pd.DataFrame:
    """Days on which an ISIN's aggregate net short moved by at least rise_pp."""
    rows = []
    for isin, g in iv.groupby("isin"):
        steps = pd.concat([pd.DataFrame({"d": g["valid_from"], "x": g["pct"]}), pd.DataFrame({"d": g["valid_to"], "x": -g["pct"]})])
        steps = steps[steps["d"] < pd.Timestamp.max.normalize()].groupby("d")["x"].sum().sort_index()
        agg = steps.cumsum().round(6)
        delta = agg.diff().fillna(agg)
        issuer = g["issuer"].iloc[-1]
        for d, dl in delta.items():
            if abs(dl) >= rise_pp - 1e-9:
                rows.append({"isin": isin, "issuer": issuer, "date": d, "delta": round(float(dl), 3),
                             "agg_after": round(float(agg[d]), 3), "kind": "rise" if dl > 0 else "fall"})
    return pd.DataFrame(rows, columns=["isin", "issuer", "date", "delta", "agg_after", "kind"])


def uk_cost(adv_gbp) -> float:
    if adv_gbp is None or not np.isfinite(adv_gbp):
        return config.UK_LIQUIDITY_COST_TIERS[-1][1]
    for floor, cost in config.UK_LIQUIDITY_COST_TIERS:
        if adv_gbp >= floor:
            return cost
    return config.UK_LIQUIDITY_COST_TIERS[-1][1]


def evaluate(events: pd.DataFrame, ticker_of: dict, fetch_bars=prices.fetch_bars, horizons=config.STUDY_HORIZONS) -> pd.DataFrame:
    ev = events.copy()
    ev["ticker"] = ev["isin"].map(ticker_of).fillna("")
    ev["public_date"] = ev["date"] + pd.offsets.BDay(config.FCA_PUBLICATION_LAG_BDAYS)
    syms = set(ev.loc[ev["ticker"] != "", "ticker"]) | set(config.UK_BENCHMARKS)
    bars = bt.prefetch(syms, fetch_bars)
    bench = next((bars[b] for b in config.UK_BENCHMARKS if not bars[b].empty), pd.DataFrame(columns=["close", "volume"]))
    rows = []
    for e in ev.itertuples():
        b = bars.get(e.ticker, pd.DataFrame(columns=["close", "volume"])) if e.ticker else pd.DataFrame(columns=["close", "volume"])
        f = op.features_and_returns(b, e.public_date.strftime("%Y-%m-%d"), horizons)
        ok = not b.empty and bool(f["entry_date"])
        adv_gbp = f["adv"] / 100.0 if np.isfinite(f["adv"]) else np.nan  # Yahoo quotes .L prices in pence
        cost = uk_cost(adv_gbp)
        bf = op.features_and_returns(bench, e.public_date.strftime("%Y-%m-%d"), horizons) if ok else {}
        row = {**e._asdict(), **f, "adv_gbp": adv_gbp, "cost": cost, "have_prices": ok}
        for h in horizons:
            g, bg = f[f"gross_{h}d"], bf.get(f"gross_{h}d")
            row[f"net_{h}d"] = g - cost if g is not None else None
            row[f"gexcess_{h}d"] = g - bg if g is not None and bg is not None else None
            row[f"excess_{h}d"] = g - bg - cost if g is not None and bg is not None else None
        rows.append(row)
    return pd.DataFrame(rows).drop(columns=["Index"], errors="ignore")


def _cell(g: pd.DataFrame, h: int) -> str:
    n, x, e = g[f"net_{h}d"].dropna(), g[f"excess_{h}d"].dropna(), g[f"gexcess_{h}d"].dropna()
    if not len(n):
        return "n/a"
    return f"{op._wmean(n):.1%} (med {n.median():.1%}) / {op._wmean(x):.1%} / {op._wmean(e):.1%}"


def report(ev: pd.DataFrame, horizons=config.STUDY_HORIZONS) -> str:
    have = ev[ev["have_prices"]] if len(ev) else ev
    L = ["# FCA aggregate short changes: event study", "",
         f"Events (aggregate net short moved by >= {config.FCA_RISE_PP}pp): {len(ev)}; with prices: {len(have)}. "
         f"Public {config.FCA_PUBLICATION_LAG_BDAYS} business days after the position date; entry at the next close. "
         "Cells: long-only net return (winsorised mean, median) / net excess vs the UK index ETF / cost-free excess "
         "(information content; for a rise, a negative value means shorts were right). Costs are assumed: "
         + ", ".join(f">= GBP {f / 1e6:g}m a day: {c:.1%}" if f else f"below: {c:.1%}" for f, c in config.UK_LIQUIDITY_COST_TIERS)
         + " round trip including stamp duty. Survivorship: delisted names have no prices.", ""]
    if have.empty:
        return "\n".join(L + ["No priced events."])
    liquid = have[have["adv_gbp"] >= config.UK_LIQUID_MIN_ADV]
    for label, uni in (("all priced", have), (f"liquid (>= GBP {config.UK_LIQUID_MIN_ADV / 1e6:g}m a day)", liquid)):
        L += [f"### {label}", "", "| event | n | " + " | ".join(f"{h}d" for h in horizons) + " |", "|---|---|" + "---|" * len(horizons)]
        for kind, g in uni.groupby("kind"):
            L.append(f"| {kind} | {len(g)} | " + " | ".join(_cell(g, h) for h in horizons) + " |")
        big = uni[(uni["kind"] == "rise") & (uni["agg_after"] >= 3)]
        if len(big):
            L.append(f"| rise to >= 3% aggregate | {len(big)} | " + " | ".join(_cell(big, h) for h in horizons) + " |")
        L.append("")
    L += ["Caveats: events cluster in time (market-wide moves); aggregate rebuilt from holder disclosures so "
          "closures that were never recorded would inflate it; ISIN-to-ticker mapping can miss delisted names; "
          "several cuts examined, so a lone good-looking cell may be luck. Not financial advice."]
    return "\n".join(L)


def main() -> None:
    raw = http.get(config.FCA_ARCHIVE_URL, headers={"User-Agent": "Mozilla/5.0 (compatible; trading-signals-research)"}).content
    import io
    pos = load_archive(io.BytesIO(raw))
    bt.log(f"{len(pos)} disclosures, {pos['isin'].nunique()} ISINs")
    iv = intervals(pos)
    events = aggregate_events(iv)
    events = events[events["date"] >= pd.Timestamp("2015-01-01")]
    bt.log(f"{len(events)} aggregate events: {events['kind'].value_counts().to_dict() if len(events) else {}}")
    tick = isin_map.map_isins(events["isin"].unique())
    bt.log(f"mapped {len(tick)}/{events['isin'].nunique()} ISINs to London tickers")
    ev = evaluate(events, tick)
    config.REPORTS_DIR.mkdir(exist_ok=True)
    ev.to_csv(config.REPORTS_DIR / "fca_short_events.csv", index=False)
    text = report(ev)
    (config.REPORTS_DIR / "fca_shorts_study.md").write_text(text + "\n")
    print(text)
