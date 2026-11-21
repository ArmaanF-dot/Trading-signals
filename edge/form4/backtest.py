"""Backtest of the Form 4 cluster rule on SEC bulk insider-transaction datasets.

No lookahead: a cluster is only known once its last Form 4 is *filed*, so we enter at the
close of the first trading day strictly after that filing date. Returns are net of
config.ROUND_TRIP_COST and compared with a small-cap ETF over the same window.

Known biases, repeated in the report: survivorship (Stooq lacks many delisted names, so
those clusters are dropped) and no historical market-cap filter (shares outstanding is not
point-in-time here, so a price proxy is reported instead).
"""
import io
import zipfile

import pandas as pd

import config
from edge import http, prices
from edge.form4 import cluster, parse

TXN_COLS = ["accession", "form_type", "issuer_cik", "issuer", "ticker", "owner_cik", "owner", "role",
            "is_director", "is_officer", "officer_title", "is_ten_pct", "date", "shares", "price", "value", "filed"]


def _tsv(zf: zipfile.ZipFile, name: str) -> pd.DataFrame:
    member = next(n for n in zf.namelist() if n.upper().endswith(name.upper()))
    df = pd.read_csv(zf.open(member), sep="\t", dtype=str, keep_default_na=False, encoding="latin-1")
    df.columns = [c.strip().upper() for c in df.columns]
    return df


def _date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="%d-%b-%Y", errors="coerce")


def rows_from_zip(zf: zipfile.ZipFile) -> pd.DataFrame:
    """Open-market purchases (code P, acquired, price > 0) in the same shape the live scanner stores."""
    sub = _tsv(zf, "SUBMISSION.tsv")
    own = _tsv(zf, "REPORTINGOWNER.tsv")
    tx = _tsv(zf, "NONDERIV_TRANS.tsv")
    tx = tx[(tx["TRANS_CODE"] == "P") & (tx["TRANS_ACQUIRED_DISP_CD"].isin(["A", ""]))].copy()
    tx["shares"] = pd.to_numeric(tx["TRANS_SHARES"], errors="coerce")
    tx["price"] = pd.to_numeric(tx["TRANS_PRICEPERSHARE"], errors="coerce")
    tx["date"] = _date(tx["TRANS_DATE"])
    tx = tx[(tx["shares"] > 0) & (tx["price"] > 0) & tx["date"].notna()]
    sub = sub[sub["DOCUMENT_TYPE"].isin(["4", "4/A"])]
    sub = sub.assign(filed=_date(sub["FILING_DATE"]))
    df = tx.merge(sub, on="ACCESSION_NUMBER").merge(own, on="ACCESSION_NUMBER")
    rel = df["RPTOWNER_RELATIONSHIP"].str.lower()
    out = pd.DataFrame({
        "accession": df["ACCESSION_NUMBER"], "form_type": df["DOCUMENT_TYPE"],
        "issuer_cik": df["ISSUERCIK"].str.zfill(10), "issuer": df["ISSUERNAME"],
        "ticker": df["ISSUERTRADINGSYMBOL"].str.upper().str.strip(),
        "owner_cik": df["RPTOWNERCIK"].str.zfill(10), "owner": df["RPTOWNERNAME"],
        "role": df["RPTOWNER_RELATIONSHIP"], "is_director": rel.str.contains("director"),
        "is_officer": rel.str.contains("officer"), "officer_title": df.get("RPTOWNER_TITLE", ""),
        "is_ten_pct": rel.str.contains("tenpercent|10"), "date": df["date"],
        "shares": df["shares"], "price": df["price"], "value": (df["shares"] * df["price"]).round(2),
        "filed": df["filed"],
    })
    return out[TXN_COLS].dropna(subset=["filed"])


def download_quarter(year: int, q: int) -> zipfile.ZipFile | None:
    headers = {"User-Agent": config.sec_user_agent(), "Accept-Encoding": "gzip, deflate"}
    for tmpl in config.INSIDER_DATASET_URLS:
        try:
            r = http.get(tmpl.format(y=year, q=q), headers=headers, min_interval=config.SEC_MIN_INTERVAL)
            return zipfile.ZipFile(io.BytesIO(r.content))
        except Exception:
            continue
    print(f"backtest: no dataset for {year}q{q}")
    return None


def public_dates(clusters: pd.DataFrame, buys: pd.DataFrame) -> pd.Series:
    """Date the cluster became public = latest filing date among buys in its window."""
    out = []
    for r in clusters.itertuples():
        w = buys[(buys["issuer_cik"] == r.issuer_cik) & (buys["date"] >= pd.Timestamp(r.window_start))
                 & (buys["date"] <= pd.Timestamp(r.signal_date))]
        out.append(w["filed"].max().strftime("%Y-%m-%d"))
    return pd.Series(out, index=clusters.index, dtype=object)


def trade_returns(closes: pd.Series, public_date: str, horizons=config.BACKTEST_HORIZONS,
                  cost: float = config.ROUND_TRIP_COST) -> dict:
    """Enter at the first close strictly after public_date; gross and net returns per horizon."""
    out = {"entry_date": "", "entry_price": ""}
    for h in horizons:
        out[f"gross_{h}d"] = out[f"net_{h}d"] = None
    if closes.empty:
        return out
    after = closes[closes.index > pd.Timestamp(public_date)]
    if after.empty:
        return out
    p0 = float(after.iloc[0])
    out["entry_date"], out["entry_price"] = after.index[0].strftime("%Y-%m-%d"), p0
    for h in horizons:
        if len(after) > h:
            g = float(after.iloc[h]) / p0 - 1
            out[f"gross_{h}d"], out[f"net_{h}d"] = g, g - cost
    return out


def run_backtest(buys: pd.DataFrame, fetch=prices.fetch_closes, benchmark=config.BACKTEST_BENCHMARK) -> pd.DataFrame:
    """One row per cluster with net returns and the benchmark's return over the same holding period."""
    clusters = cluster.find_clusters(buys)
    if clusters.empty:
        return clusters
    clusters["public_date"] = public_dates(clusters, buys)
    bench = fetch(benchmark)
    cache, rows = {}, []
    for r in clusters.itertuples():
        sym = prices.stooq_symbol(r.ticker, "us") if r.ticker else ""
        if sym and sym not in cache:
            cache[sym] = fetch(sym)
        closes = cache.get(sym, pd.Series(dtype=float))
        res = trade_returns(closes, r.public_date)
        row = {**r._asdict(), **res, "have_prices": not closes.empty}
        b = trade_returns(bench, r.public_date, cost=0.0) if res["entry_date"] else {}
        for h in config.BACKTEST_HORIZONS:
            g = res.get(f"gross_{h}d")
            bg = b.get(f"gross_{h}d")
            row[f"excess_{h}d"] = (g - bg) - config.ROUND_TRIP_COST if g is not None and bg is not None else None
        rows.append(row)
    return pd.DataFrame(rows).drop(columns=["Index"], errors="ignore")


def summarise(res: pd.DataFrame) -> str:
    """Markdown report."""
    n_all = len(res)
    have = res[res["have_prices"]] if n_all else res
    lines = ["# Form 4 cluster backtest", "",
             f"Rule: >= {config.CLUSTER_MIN_INSIDERS} distinct buyers, officer/director required, "
             f"{config.CLUSTER_WINDOW_DAYS}-day window, >= ${config.CLUSTER_MIN_VALUE:,}. "
             f"Entry at first close after the last filing date. Round-trip cost assumed {config.ROUND_TRIP_COST:.1%}.",
             "", f"Clusters found: {n_all}. With usable prices: {len(have)} "
             f"({(len(have) / n_all if n_all else 0):.0%}); the rest (often delisted names) are excluded, "
             "so **results are flattered by survivorship bias**.", ""]
    if have.empty:
        return "\n".join(lines + ["No priced clusters."])

    def table(df: pd.DataFrame, title: str) -> list[str]:
        out = [f"## {title}", "", "| horizon | n | mean net | median net | hit rate (net>0) | mean excess vs IWM (net) |", "|---|---|---|---|---|---|"]
        for h in config.BACKTEST_HORIZONS:
            s, e = df[f"net_{h}d"].dropna().astype(float), df[f"excess_{h}d"].dropna().astype(float)
            if len(s):
                out.append(f"| {h}d | {len(s)} | {s.mean():.2%} | {s.median():.2%} | {(s > 0).mean():.0%} | "
                           f"{(f'{e.mean():.2%}' if len(e) else 'n/a')} |")
        return out + [""]

    lines += table(have, "All priced clusters")
    cheap = have[have["last_price"].astype(float) < 20]
    if len(cheap):
        lines += table(cheap, "Last buy price under $20 (small-cap proxy)")
    have = have.assign(year=pd.to_datetime(have["public_date"]).dt.year)
    for y, g in have.groupby("year"):
        lines += table(g, f"Year {y}")
    lines += ["Caveats: no point-in-time market-cap filter; clusters overlap in time (not independent); "
              "returns use daily closes (no intraday slippage); small samples are noisy. Not financial advice."]
    return "\n".join(lines)


def load_range(start_year: int, end_year: int, dl=download_quarter) -> pd.DataFrame:
    frames = []
    for y in range(start_year, end_year + 1):
        for q in (1, 2, 3, 4):
            zf = dl(y, q)
            if zf is not None:
                frames.append(rows_from_zip(zf))
    if not frames:
        return pd.DataFrame(columns=TXN_COLS)
    df = pd.concat(frames, ignore_index=True)
    for c in ("is_director", "is_officer", "is_ten_pct"):
        df[c] = df[c].astype(bool)
    return df.drop_duplicates(["accession", "owner_cik", "date", "shares", "price"])


def main(start_year: int, end_year: int) -> None:
    buys = load_range(start_year, end_year)
    print(f"backtest: {len(buys)} purchase rows, {buys['issuer_cik'].nunique()} issuers")
    res = run_backtest(buys)
    config.REPORTS_DIR.mkdir(exist_ok=True)
    res.to_csv(config.REPORTS_DIR / "form4_backtest_clusters.csv", index=False)
    report = summarise(res)
    (config.REPORTS_DIR / "form4_backtest.md").write_text(report + "\n")
    print(report)
