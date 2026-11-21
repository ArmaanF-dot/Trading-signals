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
CLUSTER_REQUIRE_OFFICER_OR_DIRECTOR = True  # drop pure 10%-owner clusters (funds, activists)
CLUSTER_MAX_MARKET_CAP = 2_000_000_000  # small caps only; unknown market cap is kept
SHARES_OUT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/dei/EntityCommonStockSharesOutstanding.json"
SHARES_CACHE_CSV = DATA_DIR / "form4_shares.csv"

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
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=10y&interval=1d"
YAHOO_USER_AGENT = "Mozilla/5.0 (compatible; trading-signals-research)"


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

# --- backtest ---
INSIDER_DATASET_URLS = [
    "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{y}q{q}_form345.zip",
    "https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets/{y}q{q}_form345.zip",
]
ROUND_TRIP_COST = 0.025  # 2.5% round trip spread/commission assumption for small caps
BACKTEST_HORIZONS = (5, 20, 60)
BACKTEST_BENCHMARK = "IWM"  # Russell 2000 ETF
REPORTS_DIR = ROOT / "reports"

# --- opportunistic-insider / cross-sectional study ---
# Round-trip trading cost assumed by liquidity (average dollar volume, last 20 days).
# These are ASSUMPTIONS, not measured spreads; the report says so.
LIQUIDITY_COST_TIERS = [(20_000_000, 0.004), (5_000_000, 0.010), (0, 0.025)]
LIQUID_MIN_ADV = 5_000_000
STUDY_HORIZONS = (20, 40, 60)  # trading days: weeks-long holds
EVENT_QUIET_DAYS = 30  # one event per issuer and buyer type per this many days
MIN_EVENT_VALUE = 20_000
MIN_EVENTS_PER_MONTH = 10  # months with fewer events are skipped for quintile ranking
