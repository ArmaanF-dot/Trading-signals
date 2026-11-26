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
JOBS_DIR = DATA_DIR / "jobs"  # daily job-board snapshots (edge/jobs)
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
# period1/period2 rather than range=max: with range=max Yahoo coarsens long histories, leaving gaps in a monthly series
YAHOO_MONTHLY_MAX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=852076800&period2=4102444800&interval=1mo"

# --- momentum study (12-1 month cross-sectional momentum on S&P 500 members) ---
# Point-in-time S&P 500 membership since 1996 (community-maintained, from Clenow's list plus Wikipedia changes).
SP500_MEMBERSHIP_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv"
MOMENTUM_FIRST_FORMATION = "2000-01"
MOMENTUM_SPLIT = "2013-01"  # first out-of-sample formation month; variants are chosen on earlier months only
MOMENTUM_COSTS = [0.002, 0.02, 0.03]  # round trip: realistic for S&P 500 names, then the house 2% and 3%
MOMENTUM_MAX_MONTHLY_RET = 2.0  # stock-month returns above +200% are treated as bad data (recycled tickers etc.)
YAHOO_DAILY_MAX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=852076800&period2=4102444800&interval=1d"
REVERSAL_FIRST_DAY = "2000-01-03"
REVERSAL_SPLIT = "2013-01-01"  # first out-of-sample day; variants are chosen on earlier days only
REVERSAL_COSTS = [0.002, 0.02, 0.03]  # round trip: realistic for S&P 500 names, then the house 2% and 3%
REVERSAL_MAX_DAILY_RET = 1.0  # open-to-open moves above +100% are treated as bad data (recycled tickers etc.)

# --- quality and value study (SEC XBRL fundamentals on S&P 500 members; reuses the momentum engine and costs) ---
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
QV_FIRST_FORMATION = "2010-06"  # XBRL filings start in 2009
QV_SPLIT = "2018-07"  # first out-of-sample formation month
QV_MAX_ANNUAL_AGE_DAYS = 480  # fiscal-year end to formation; a 10-K lands within ~90 days, the next one a year later
QV_MAX_INSTANT_AGE_DAYS = 200  # balance sheet date to formation (quarterly filers)
QV_MIN_MCAP, QV_MAX_MCAP = 1e8, 1e13  # outside this the share count or price is wrong
QV_MIN_RANKED = 100  # skip a month if fewer members have the signal


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
MAX_ENTRY_GAP_DAYS = 7  # entry must be within this many calendar days of the filing, else the price history does not cover the event (e.g. recycled ticker)
MIN_BARS_BEFORE = 20

# --- FCA shorts study ---
# Archived named-position workbook (old regime): sheets "Current Disclosures" and "Historic Disclosures".
FCA_ARCHIVE_URL = "https://www.fca.org.uk/publication/data/short-positions-daily-update.xlsx"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=5&newsCount=0"
FCA_PUBLICATION_LAG_BDAYS = 2  # conservative: a position date is treated as public two business days later
FCA_RISE_PP = 0.5  # aggregate net short moved by at least this many percentage points
UK_BENCHMARKS = ["VMID.L", "ISF.L"]  # FTSE 250 ETF, falling back to FTSE 100 ETF
# UK round-trip cost by average daily value traded in GBP: spread plus 0.5% stamp duty on buys (main market).
# Assumptions, not measured.
UK_LIQUIDITY_COST_TIERS = [(10_000_000, 0.009), (2_000_000, 0.017), (0, 0.035)]
UK_LIQUID_MIN_ADV = 2_000_000

# --- signal feed (for the agent council) ---
FEED_JSON = SIGNALS_DIR / "feed.json"
FEED_MD = SIGNALS_DIR / "feed.md"
TRACK_RECORD_MD = SIGNALS_DIR / "track_record.md"
FEED_LOOKBACK_DAYS = 30
FEED_DISCLAIMER = "Research signals, not advice. Backtests found no standalone edge after costs; use as inputs only and paper trade first."
FEED_EVIDENCE = {
    "form4_cluster": "Backtest 2023-25: no net edge (about -1% to -2% excess vs IWM after costs). Watchlist input only.",
    "fca_short_rise": "Backtest 2016-26: aggregate-short rises were followed by about -1.4% excess over 60 days before costs (monthly t about -2.3). Weak avoid filter; too thin to short.",
    "uk_combo": "Untested: no free history of director dealings. Treat as an idea to inspect by hand.",
}
MIN_TRACK_N = 30  # do not read anything into a track record smaller than this

# --- post-earnings announcement drift study ---
SEC_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_SUBMISSIONS_FILE_URL = "https://data.sec.gov/submissions/{name}"
PEAD_START = "2017-01-01"  # Yahoo's 10-year range starts late 2016
PEAD_OOS_START = "2022-01-01"  # in sample 2017-21, out of sample 2022 onward
PEAD_BENCHMARK = "SPY"
PEAD_HORIZONS = (20, 40, 60)  # trading days held after entry
PEAD_ENTRY_LAG = 1  # enter this many closes after the first close following the 8-K
PEAD_MIN_GAP_DAYS = 45  # at most one earnings 8-K per company per this many days
PEAD_MIN_ADV = 20_000_000  # liquid: 20-day average dollar volume before the announcement
PEAD_MIN_PRICE = 5.0
PEAD_BREAKPOINT_DAYS = 91  # quintile breakpoints from the previous quarter's announcements
PEAD_MIN_BREAKPOINT_EVENTS = 100

# --- ML ranking study (gradient boosting on weak price/volume features, S&P 500 members) ---
YAHOO_DAILY_MAX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=883612800&period2=4102444800&interval=1d"
ML_FIRST_FORMATION = "2000-01"  # features need a year of daily history (prices from 1998)
ML_FIRST_PREDICTION = "2005-01"  # first walk-forward model is trained on 2000-01 .. 2004-11 formations
ML_SPLIT = "2013-01"  # variant chosen on 2005-2012 walk-forward predictions; 2013 onward is the held-out test
ML_COSTS = MOMENTUM_COSTS

# Frontier / commodity-linked country ETF study (edge/frontier.py)
FRONTIER_COSTS = [0.003, 0.02, 0.03]  # round trip: liquid country ETF, then the house 2% and 3%
FRONTIER_SPLIT = "2016-01"  # first out-of-sample formation month
FRONTIER_FIRST_FORMATION = "2011-06"

# ---- Baco travel widget (a public bus stop and a tube station; no address) ----
TRAVEL = {
    "bus": {
        "label": "Wheatsheaf, Leamington Spa to University of Warwick",
        "walk_min": 12,
        "destination_keyword": "University",
        # The Wheatsheaf stop on Tachbrook Road (4200F036401) is the south-bound side: its buses run to
        # Warwick Gates, away from the University. The University-bound U1 and U1A call at the stop on the
        # opposite side, which the national stop list names Cashmore Avenue (about 130 m away).
        "stops": [
            {"atco": "4200F206801", "name": "Wheatsheaf, University-bound side (Cashmore Avenue stop)"},
            {"atco": "4200F036401", "name": "Wheatsheaf, Tachbrook Road"},
        ],
    },
    "tube": {"label": "Northwood station (Metropolitan line)", "naptan": "940GZZLUNOW", "walk_min": 11},
}

# Job postings (edge/jobs)
JOBS_USER_AGENT = "trading-signals-research/1.0 (github.com/ArmaanF-dot/trading-signals)"
JOBS_MIN_INTERVAL = 1.5  # seconds between job-board requests (Lever asks for 1 s)
JOBS_WAYBACK_INTERVAL = 1.0  # seconds between Internet Archive requests per worker
JOBS_STUDY_START = "2017-01-01"
JOBS_RECENT_MAX_DAYS = 45  # latest snapshot must be at most this old at the earnings date
JOBS_LOOKBACK_DAYS = 80  # compare with a snapshot at least this much older (about a quarter)
JOBS_LOOKBACK_MAX_DAYS = 150
JOBS_BREAKPOINT_DAYS = 365
JOBS_MIN_BREAKPOINT_EVENTS = 30
JOBS_WORKDAY_INTERVAL = 3.0  # Workday rate-limits harder than the other boards

# Crypto carry study (edge/carry.py): Binance public data dump (reachable from the cloud; the live API is geo-blocked)
CARRY_DATA_URL = "https://data.binance.vision/data/{market}/monthly/{kind}/{symbol}{sub}/{symbol}-{name}-{ym}.zip"
CARRY_COINS = ["BTC", "ETH", "BNB", "XRP", "LTC", "ADA", "DOGE", "LINK", "SOL", "AVAX"]  # large coins of today (survivorship bias, said in the report)
CARRY_START = "2019-09"
CARRY_CACHE = DATA_DIR / "carry_cache"  # raw monthly zips, git-ignored
CARRY_PANEL = REPORTS_DIR / "carry_panel.csv.gz"  # compact daily panel the study reads (rebuilt by `python run.py carry --refresh`)
CARRY_SPLIT = "2023-01-01"  # parameters chosen before this date; 2023 onward is out of sample
CARRY_MARGIN = 0.25  # extra capital held as perp margin, per 1.0 of notional (about 4x leverage on the short leg)
CARRY_SPOT_FEE, CARRY_PERP_FEE = 0.0010, 0.0005  # Binance taker, no BNB discount, per side
CARRY_SLIPPAGE = {"BTC": 0.0002, "ETH": 0.0002}  # per leg per side; everything else uses the default
CARRY_SLIPPAGE_DEFAULT = 0.0008
CARRY_FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"
# Cross-asset trend following (edge/trend.py)
TREND_COSTS = [0.001, 0.0025, 0.025]  # round trip: realistic liquid ETF, a wide-spread case, then the house 2.5%
TREND_SPLIT = "2017-01"  # first out-of-sample formation month
TREND_FIRST_FORMATION = "2008-01"
TREND_VOL_TARGET = 0.10
TREND_LEVERAGE_CAP = 3.0

# --- Leveraged ETF structural arbitrage study (3x bull/bear pairs) ---
LETF_SPLIT = "2018-01-01"  # reset interval chosen before this date; later data is out of sample
LETF_HOURLY_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=730d&interval=60m"
