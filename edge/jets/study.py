"""Do corporate jet trips predict deals or returns? Event study on adsb.lol history.

Inputs: data/jets/history/*.csv (one file per day, from edge/jets/day.py) and the watchlist
(edge/jets/registry.py). Rules fixed before looking at outcomes:

- Omaha visit: a watchlist jet arrives at Eppley (KOMA) or Millard (KMLE), owner not based in
  Nebraska. At most one event per company per 30 days. This is the "meets Buffett" idea; a
  landing shows the plane went to Omaha, not who anyone met.
- Unusual trip: a watchlist jet arrives at an airport it has not visited in the previous 180
  days, other than its usual base. Needs 180 days of history on that jet first. At most one
  event per company per 7 days. This is the published "buyer visits target" idea.
Companies with more than MAX_FLEET jets on the watchlist are operating fleets (organ transport,
utilities), not executive travel, and are left out.

Outcomes:
- Returns: data for day D is published around 03:30 UTC on D+1, so entry is the close of D+1.
  Excess over SPY at 5, 20 and 60 trading days; net of liquidity-tiered costs and of a flat 2.5%.
  Monthly-clustered t-statistics. In sample to 2024-12-31, out of sample from 2025-01-01.
- Deals: share of events followed within 90 days by an M&A filing from the company (Form 425
  or 8-K Item 2.01), against the same company's base rate on every day of the window.
- Berkshire: Omaha visitors that became a new Berkshire Hathaway 13F position within two
  quarters, and Berkshire's new positions whose company jet had been to Omaha.
"""
import re
import xml.etree.ElementTree as ET
from datetime import timedelta

import numpy as np
import pandas as pd

import config
from edge import pead, prices
from edge.form4 import backtest as bt
from edge.form4 import opportunistic as op
from edge.jets import day as D
from edge.jets import registry

OMAHA = D.OMAHA
MAX_FLEET = 6
NOVEL_LOOKBACK = 180
OOS_START = pd.Timestamp("2025-01-01")
HORIZONS = (5, 20, 60)
DEAL_WINDOW = 90
BRK_CIK = "0001067983"
REPORT = config.REPORTS_DIR / "jets_study.md"
EVENTS_CSV = config.REPORTS_DIR / "jets_events.csv"


def load_history(hist_dir=D.HISTORY_DIR) -> pd.DataFrame:
    files = sorted(hist_dir.glob("*.csv"))
    frames = [pd.read_csv(f, dtype=str) for f in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=D.FIELDS + ["days_scanned"])
    h = pd.concat(frames, ignore_index=True)
    h["date"] = pd.to_datetime(h["date"])
    h["watch"] = h["watch"].astype(int)
    h["omaha"] = h["omaha"].astype(int)
    h.attrs["days_scanned"] = len(files)
    h.attrs["first_day"], h.attrs["last_day"] = files[0].stem, files[-1].stem
    return h


def watch_arrivals(h: pd.DataFrame, wl: pd.DataFrame) -> pd.DataFrame:
    a = h[h["watch"] == 1].merge(wl[["hex", "ticker", "company", "state", "city", "valid_to"]], on="hex", how="inner")
    vt = pd.to_datetime(a["valid_to"].replace("", np.nan))
    a = a[vt.isna() | (a["date"] <= vt)]
    fleet = wl.groupby("ticker")["hex"].nunique()
    return a[a["ticker"].map(fleet).fillna(0) <= MAX_FLEET].copy()


def _thin(ev: pd.DataFrame, days: int) -> pd.DataFrame:
    keep, last = [], {}
    for r in ev.sort_values("date").itertuples():
        if r.ticker in last and (r.date - last[r.ticker]).days < days:
            continue
        last[r.ticker] = r.date
        keep.append(r.Index)
    return ev.loc[keep]


def omaha_events(a: pd.DataFrame) -> pd.DataFrame:
    ev = a[a["airport"].isin(OMAHA) & (a["state"] != "NE")]
    return _thin(ev.assign(kind="omaha"), 30)


def novel_events(a: pd.DataFrame, lookback: int = NOVEL_LOOKBACK) -> pd.DataFrame:
    rows = []
    for hx, g in a.sort_values("arrived_utc").groupby("hex"):
        home = g["airport"].mode().iloc[0]
        first = g["date"].min()
        last_seen: dict[str, pd.Timestamp] = {}
        for r in g.itertuples():
            prev = last_seen.get(r.airport)
            if (r.date - first).days >= lookback and r.airport != home and (prev is None or (r.date - prev).days > lookback):
                rows.append(r.Index)
            last_seen[r.airport] = r.date
    return _thin(a.loc[rows].assign(kind="novel"), 7)


# --- outcomes ---

def deal_dates(fl: pd.DataFrame) -> list[pd.Timestamp]:
    items = fl["items"].fillna("").astype(str).map(lambda s: re.split(r"[,\s]+", s))
    is_deal = (fl["form"] == "425") | ((fl["form"] == "8-K") & items.map(lambda x: "2.01" in x))
    return sorted(set(fl.loc[is_deal, "filed"]))


def deal_hit(dates: list[pd.Timestamp], day: pd.Timestamp, window: int = DEAL_WINDOW) -> bool:
    return any(day < d <= day + timedelta(days=window) for d in dates)


def base_rate(dates: list[pd.Timestamp], start: pd.Timestamp, end: pd.Timestamp, window: int = DEAL_WINDOW) -> float:
    days = pd.date_range(start, end, freq="D")
    return float(np.mean([deal_hit(dates, d, window) for d in days])) if len(days) else float("nan")


def add_returns(ev: pd.DataFrame, bars: dict, bench: pd.Series) -> pd.DataFrame:
    empty = pd.DataFrame(columns=["close", "volume"], dtype=float)
    rows = []
    for r in ev.itertuples():
        m = pead.measures(bars.get(prices.yahoo_symbol(r.ticker, "us"), empty), bench, r.date, HORIZONS, lag=0)
        rows.append(m)
    m = pd.DataFrame(rows, index=ev.index)
    out = pd.concat([ev, m.drop(columns=["ear"])], axis=1)
    for h in HORIZONS:
        out[f"excess_{h}d"] = out[f"gross_{h}d"] - out[f"bench_{h}d"]
    out["cost"] = out["adv"].map(op.round_trip_cost)
    return out


def brk_new_positions(sec_json=pead.sec_json) -> pd.DataFrame:
    """Berkshire 13F-HR: issuers that appear in a quarter's table but not the previous one."""
    sub = sec_json(config.SEC_SUBMISSIONS_URL.format(cik=BRK_CIK))
    rec = sub["filings"]["recent"]
    f = pd.DataFrame({"form": rec["form"], "acc": rec["accessionNumber"], "filed": rec["filingDate"],
                      "period": rec.get("reportDate", [""] * len(rec["form"]))})
    f = f[f["form"] == "13F-HR"].sort_values("period")
    f = f[f["period"] >= "2022-09-30"].drop_duplicates("period", keep="last")
    prev, rows = None, []
    for r in f.itertuples():
        acc = r.acc.replace("-", "")
        idx = sec_json(f"https://www.sec.gov/Archives/edgar/data/1067983/{acc}/index.json")
        xmls = [i["name"] for i in idx["directory"]["item"] if i["name"].endswith(".xml") and "primary" not in i["name"]]
        if not xmls:
            continue
        txt = bt_get_text(f"https://www.sec.gov/Archives/edgar/data/1067983/{acc}/{xmls[0]}")
        names = issuers_from_13f(txt)
        if prev is not None:
            for n in sorted(names - prev):
                rows.append({"period": r.period, "filed": r.filed, "issuer": n})
        prev = names
    return pd.DataFrame(rows, columns=["period", "filed", "issuer"])


def bt_get_text(url: str) -> str:
    from edge import http
    return http.get(url, headers={"User-Agent": config.sec_user_agent()}, min_interval=config.SEC_MIN_INTERVAL).text


def issuers_from_13f(xml_text: str) -> set[str]:
    root = ET.fromstring(xml_text.encode())
    out = set()
    for el in root.iter():
        if el.tag.split("}")[-1] == "nameOfIssuer" and el.text:
            out.add(registry.norm(el.text))
    return out


# --- statistics ---

def cell(g: pd.DataFrame, col: str, cost=None) -> str:
    x = g[col] if cost is None else g[col] - cost
    x = x.dropna()
    if len(x) < 5:
        return f"n={len(x)}"
    t, _ = pead.monthly_t(x, pd.to_datetime(g.loc[x.index, "entry_date"]).dt.to_period("M"))
    return f"{op._wmean(x) if len(x) >= 20 else x.mean():+.2%} (t {t:.1f}, n {len(x)})"


def table(ev: pd.DataFrame) -> list[str]:
    lines = ["| Signal | Period | Events | " + " | ".join(f"Excess {h}d" for h in HORIZONS) + " | Net 60d (tiered) | Net 60d (2.5%) |",
             "|---|---|---|" + "---|" * len(HORIZONS) + "---|---|"]
    for kind, kg in ev.groupby("kind"):
        for label, g in (("in sample", kg[kg["date"] < OOS_START]), ("out of sample", kg[kg["date"] >= OOS_START]), ("all", kg)):
            cells = [cell(g, f"excess_{h}d") for h in HORIZONS]
            lines.append(f"| {kind} | {label} | {len(g)} | " + " | ".join(cells) +
                         f" | {cell(g, 'excess_60d', g['cost'])} | {cell(g, 'excess_60d', config.ROUND_TRIP_COST)} |")
    return lines


def verdict(ev: pd.DataFrame) -> str:
    oos = ev[(ev["date"] >= OOS_START) & ev["excess_20d"].notna()]
    ins = ev[(ev["date"] < OOS_START) & ev["excess_20d"].notna()]
    msgs = []
    for kind in ("novel", "omaha"):
        i, o = ins[ins["kind"] == kind], oos[oos["kind"] == kind]
        if len(o) < 30:
            msgs.append(f"{kind}: too few out-of-sample events ({len(o)}) to test")
            continue
        net = (o["excess_20d"] - o["cost"]).mean()
        net_short = (-o["excess_20d"] - o["cost"]).mean()
        t, _ = pead.monthly_t(o["excess_20d"], pd.to_datetime(o["entry_date"]).dt.to_period("M"))
        same_sign = np.sign(i["excess_20d"].mean()) == np.sign(o["excess_20d"].mean())
        ok = max(net, net_short) > 0 and abs(t) >= 2 and same_sign
        msgs.append(f"{kind}: {'possible edge' if ok else 'no edge'} (OOS 20d excess {o['excess_20d'].mean():+.2%}, t {t:.1f}, "
                    f"best side net of costs {max(net, net_short):+.2%}, in-sample sign {'held' if same_sign else 'flipped'})")
    return "; ".join(msgs)


def report(h: pd.DataFrame, wl: pd.DataFrame, a: pd.DataFrame, ev: pd.DataFrame, deals: pd.DataFrame,
           brk: pd.DataFrame, oma_all: pd.DataFrame) -> str:
    n_days = h.attrs.get("days_scanned", 0)
    seen = a["hex"].nunique()
    L = ["# Corporate jet tracking study", "",
         f"Data: adsb.lol daily archive (ODbL), {n_days} days scanned from {h.attrs.get('first_day', '?')} to "
         f"{h.attrs.get('last_day', '?')}. Watchlist: {len(wl)} turbofan jets registered in the FAA database to "
         f"{wl['ticker'].nunique()} SEC-listed companies; {seen} of them were seen arriving somewhere "
         f"({a['ticker'].nunique()} companies after dropping operating fleets of more than {MAX_FLEET} jets).", "",
         f"**Verdict: {verdict(ev)}.**", "",
         "## Returns after trips (excess over SPY, entry at the close after the data is published)", ""]
    L += table(ev)
    L += ["", "Costs: tiered by 20-day dollar volume as in the other studies; the last column charges a flat 2.5% round trip. "
          "Means are clipped at the 1st/99th percentile when there are at least 20 events.", "",
          "## Deals within 90 days (Form 425 or 8-K Item 2.01)", ""]
    if not deals.empty:
        L += ["| Signal | Events with filings data | Followed by a deal filing | Same companies' base rate |", "|---|---|---|---|"]
        for kind, g in deals.groupby("kind"):
            L.append(f"| {kind} | {len(g)} | {g['deal'].mean():.1%} | {g['base'].mean():.1%} |")
    L += ["", "## Omaha", ""]
    om = ev[ev["kind"] == "omaha"]
    if om.empty:
        L.append("No watchlist jet from outside Nebraska landed in Omaha in the scanned days.")
    else:
        L += ["| Date | Company | Jet | Airport | 20d excess |", "|---|---|---|---|---|"]
        for r in om.sort_values("date").itertuples():
            x = f"{r.excess_20d:+.1%}" if pd.notna(r.excess_20d) else ""
            L.append(f"| {r.date:%Y-%m-%d} | {r.company} ({r.ticker}) | {r.reg or r.hex} | {r.airport} | {x} |")
    if not oma_all.empty:
        bj = oma_all[oma_all["type"].fillna("").str.match(r"^(GLF|GL|CL|C5|C6|C7|E5|E55|FA|F2|F9|LJ|H25|PC24|BE40|C25|C56|C68|C700|G280|GALX|ASTR)")]
        L += ["", f"All aircraft arriving in Omaha over the scanned days: {oma_all['hex'].nunique()} distinct airframes, "
              f"{len(bj)} business-jet arrivals. Owner names, where adsb.lol's database has them, are mostly trustees, "
              "LLCs, fractional operators and charter firms, so most visits cannot be tied to a company."]
        top = bj["owner_op"].fillna("").replace("", "(unknown)").value_counts().head(12)
        L += ["", "| Owner/operator (as broadcast database lists it) | Business-jet arrivals |", "|---|---|"]
        L += [f"| {k} | {v} |" for k, v in top.items()]
    L += ["", "## Berkshire Hathaway new 13F positions", ""]
    if brk.empty:
        L.append("Could not read Berkshire's 13F filings in this run.")
    else:
        visitors = set(om["company"].map(registry.norm))
        L.append("| Quarter | New issuer | Its jet on the watchlist? | Visited Omaha before filing? |")
        L.append("|---|---|---|---|")
        wl_norm = {registry.norm(c): t for c, t in zip(wl["company"], wl["ticker"])}
        for r in brk.itertuples():
            on = next((t for n, t in wl_norm.items() if n and (n == r.issuer or n.startswith(r.issuer) or r.issuer.startswith(n))), None)
            visited = any(n == r.issuer or n.startswith(r.issuer) or r.issuer.startswith(n) for n in visitors)
            L.append(f"| {r.period} | {r.issuer} | {on or 'no'} | {'yes' if visited else 'no'} |")
    L += ["", "## What can and cannot be inferred", "",
          "- A landing shows where a plane went, not who was on it or who they met. Omaha also hosts Union Pacific, "
          "Kiewit, Mutual of Omaha, TD Ameritrade's old base and others, so an Omaha visit is not a Berkshire meeting.",
          "- Warren Buffett and Berkshire's managers fly NetJets (fractional, shared tail numbers), so their own travel "
          "cannot be followed; visitors could only be seen if they fly their own registered jet.",
          "- Most large-company jets are registered through bank trustees (Bank of Utah, Wilmington Trust, TVPX: about "
          "4,100 US jets) or anonymous LLCs, and many fly with the FAA's PIA privacy hex. The watchlist only holds jets "
          "registered openly in a listed company's name, so coverage is a small, biased slice.",
          "- The watchlist is today's FAA registry plus aircraft deregistered since 2023; jets bought by a company after "
          "a trip, or held under a name we cannot match, are missed.",
          "- Licences: adsb.lol history is ODbL 1.0 (open, attribution and share-alike for derived databases); the FAA "
          "registry and EDGAR are US public records. OpenSky's API was unreachable from this environment and its "
          "historical database needs an approved research account; ADS-B Exchange's free samples are one day a month. "
          "No paid data used. Tracking aircraft broadcasts is legal in the US and UK; trading on it is not insider "
          "dealing since it uses public information, but publishing a named individual's movements raises privacy issues, "
          "so the repo stores company jets only.", ""]
    return "\n".join(L)


def main() -> None:
    h = load_history()
    wl = pd.DataFrame(registry.load()).fillna("")
    bt.log(f"history: {h.attrs.get('days_scanned', 0)} days, {len(h)} arrival rows")
    a = watch_arrivals(h, wl)
    ev = pd.concat([omaha_events(a), novel_events(a)], ignore_index=True)
    bt.log(f"events: {ev['kind'].value_counts().to_dict() if len(ev) else {}}")
    syms = {prices.yahoo_symbol(t, "us") for t in ev["ticker"].unique()} | {"SPY"}
    bars = bt.prefetch(syms, prices.fetch_bars)
    ev = add_returns(ev, bars, bars["SPY"]["close"])
    # deal filings
    tick = pead.sec_json(registry.SEC_TICKERS_URL)
    cik = {v["ticker"]: f"{int(v['cik_str']):010d}" for v in tick.values()}
    start, end = h["date"].min(), h["date"].max()
    deal_rows = []
    for t, g in ev.groupby("ticker"):
        if t not in cik:
            continue
        try:
            sub = pead.sec_json(config.SEC_SUBMISSIONS_URL.format(cik=cik[t]))
            dd = deal_dates(pead.filings(sub, lambda n: pead.sec_json(config.SEC_SUBMISSIONS_FILE_URL.format(name=n)), since="2022-06-01"))
        except Exception as exc:
            bt.log(f"{t}: {type(exc).__name__}: {exc}")
            continue
        br = base_rate(dd, start, end - timedelta(days=DEAL_WINDOW))
        for r in g.itertuples():
            if r.date <= end - timedelta(days=DEAL_WINDOW):
                deal_rows.append({"kind": r.kind, "ticker": t, "date": r.date, "deal": deal_hit(dd, r.date), "base": br})
    deals = pd.DataFrame(deal_rows)
    try:
        brk = brk_new_positions()
    except Exception as exc:
        bt.log(f"berkshire 13F: {type(exc).__name__}: {exc}")
        brk = pd.DataFrame()
    oma_all = h[h["omaha"] == 1]
    config.REPORTS_DIR.mkdir(exist_ok=True)
    ev.drop(columns=["owner_op"], errors="ignore").to_csv(EVENTS_CSV, index=False)
    text = report(h, wl, a, ev, deals, brk, oma_all)
    REPORT.write_text(text + "\n")
    print(text)
