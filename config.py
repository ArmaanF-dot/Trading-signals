"""All URLs, paths and thresholds in one place.

Secrets are read ONLY from environment variables (never hard-code them):
  NTFY_TOPIC      - ntfy topic name; if unset, alerts print to stdout (dry run)
  SEC_USER_AGENT  - e.g. "Your Name you@example.com" (SEC requires this)
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SIGNALS_DIR = ROOT / "signals"

# --- paths ---
FORM4_BUYS_CSV = DATA_DIR / "form4_buys.csv"
FORM4_SEEN_TXT = DATA_DIR / "form4_seen.txt"
FORM4_CLUSTERS_CSV = SIGNALS_DIR / "form4_clusters.csv"
FCA_SNAPSHOT_DIR = DATA_DIR / "fca_shorts"
FCA_EVENTS_CSV = SIGNALS_DIR / "fca_events.csv"
RNS_CSV = DATA_DIR / "rns_director_buys.csv"
COMBO_CSV = SIGNALS_DIR / "combo.csv"
ISIN_TICKER_CSV = DATA_DIR / "isin_ticker.csv"  # optional: isin,ticker (for FCA returns)

# --- notifications ---
NTFY_BASE_URL = "https://ntfy.sh"

# --- SEC Form 4 ---
SEC_BASE = "https://www.sec.gov"
# EDGAR current-filings Atom feed; "&start=N" is appended for pagination.
FORM4_FEED_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=4&owner=include&count=100&output=atom"
)
FORM4_FEED_PAGES = 3
FORM4_FEED_PAGE_SIZE = 100
SEC_MIN_INTERVAL = 0.125  # seconds between requests (~8 req/s, SEC limit is 10)
HTTP_RETRIES = 4
HTTP_TIMEOUT = 30

# Cluster rule: >= N distinct insiders buying at one issuer within WINDOW days,
# total value at least MIN_VALUE dollars.
CLUSTER_MIN_INSIDERS = 2
CLUSTER_WINDOW_DAYS = 10
CLUSTER_MIN_VALUE = 100_000

# --- FCA short positions ---
# Daily aggregate (anonymised) net short positions CSV; the FCA stopped publishing
# named positions when the new regime started on 13 July 2026.
FCA_SHORTS_URL = "https://www.fca.org.uk/publication/documents/aggregated-current-net-short-positions.csv"
FCA_CHANGE_THRESHOLD_PP = 0.1   # report increases/decreases of at least this many pp
FCA_ALERT_EVENTS = {"new", "cover"}  # event types that trigger an ntfy alert

# --- combo (director buy + FCA net short) ---
COMBO_MIN_NET_SHORT_PCT = 0.5
COMBO_LOOKBACK_DAYS = 30  # director buys older than this are ignored

# --- prices (return tracking) ---
STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"


def ntfy_topic() -> str | None:
    """Read at call time so tests can change the environment."""
    return os.environ.get("NTFY_TOPIC") or None


def sec_user_agent() -> str:
    # Secrets pasted into GitHub often carry a trailing newline or stray spaces,
    # which make the header invalid; collapse all whitespace.
    ua = " ".join((os.environ.get("SEC_USER_AGENT") or "").split())
    if not ua:
        raise RuntimeError(
            "SEC_USER_AGENT is not set. SEC requires a descriptive User-Agent "
            'such as "Your Name you@example.com".'
        )
    return ua
