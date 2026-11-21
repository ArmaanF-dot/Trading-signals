"""Form 4 pipeline: fetch new filings -> purchases -> clusters -> alerts -> returns."""
import pandas as pd

import config
from edge import notify, prices, store
from edge.form4 import cluster, fetch, parse

CLUSTER_KEY = ["issuer_cik", "window_start"]


def _seen() -> set[str]:
    p = config.FORM4_SEEN_TXT
    return set(p.read_text().split()) if p.exists() else set()


def _mark_seen(accessions) -> None:
    config.FORM4_SEEN_TXT.parent.mkdir(parents=True, exist_ok=True)
    with config.FORM4_SEEN_TXT.open("a") as f:
        for a in accessions:
            f.write(a + "\n")


def collect_buys() -> int:
    seen = _seen()
    filings = [f for f in fetch.list_recent_filings() if f["accession"] not in seen]
    rows, done = [], []
    for f in filings:
        try:
            xml = fetch.fetch_filing_xml(f["index_url"])
            if xml:
                rows += parse.parse_form4(xml, f["accession"])
            done.append(f["accession"])
        except Exception as exc:  # one bad filing must not stop the batch; retried next run
            print(f"skip {f['accession']}: {type(exc).__name__}")
    if rows:
        store.append_dedupe(config.FORM4_BUYS_CSV, pd.DataFrame(rows, columns=parse.COLUMNS),
                            ["accession", "owner_cik", "date", "shares", "price"])
    _mark_seen(done)
    return len(rows)


def detect_and_alert() -> pd.DataFrame:
    buys = store.read_csv(config.FORM4_BUYS_CSV)
    if buys.empty:
        return pd.DataFrame()
    clusters = cluster.find_clusters(cluster.load_buys(buys))
    new = store.append_dedupe(config.FORM4_CLUSTERS_CSV, clusters.astype(str), CLUSTER_KEY)
    for r in new.itertuples():
        notify.send(
            f"Insider cluster: {r.ticker or r.issuer}",
            f"{r.n_insiders} insiders bought ${float(r.total_value):,.0f} by {r.signal_date}\n{r.insiders}",
            priority="high", tags=["moneybag"],
        )
    return new


def update_returns() -> None:
    df = store.read_csv(config.FORM4_CLUSTERS_CSV)
    if df.empty:
        return
    df = prices.fill_returns(df, "ticker", "signal_date", "us")
    df.to_csv(config.FORM4_CLUSTERS_CSV, index=False)


def run() -> None:
    n = collect_buys()
    print(f"form4: {n} new purchase rows")
    detect_and_alert()
    update_returns()
