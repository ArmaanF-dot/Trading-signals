# Trading signals

Cheap, free-data signals for markets institutions ignore (UK/US small caps). Daily batch jobs on GitHub Actions, alerts to your phone via [ntfy](https://ntfy.sh), CSV outputs that feed a paper-first trading bot. *Not financial advice. Paper trade first.*

## Signals

| Command | Signal | Output |
|---|---|---|
| `python run.py form4` | US SEC Form 4 cluster buys: at least 2 distinct buyers, at least one officer or director, 10 days, $100k+, market cap at most $2bn (unknown kept) | `data/form4_buys.csv`, `signals/form4_clusters.csv` |
| `python run.py fca` | FCA aggregate net short positions: daily diff per company (new / cover / increase / decrease) | `data/fca_shorts/*.csv`, `signals/fca_events.csv` |
| `python run.py combo` | UK director buy (RNS) on an ISIN with an aggregate net short of at least 0.5% | `signals/combo.csv` |
| `python run.py all` | All of the above | |

Thresholds live in `config.py`.

> **Data change:** since 13 July 2026 the FCA publishes only anonymised *aggregate* net shorts (one number per company, T+2), not named funds. The pipeline uses that daily CSV, so it cannot tell you *who* is short, only how much.

## Backtest

`python run.py backtest 2021 2025` (or Actions, "backtest", "Run workflow") rebuilds Form 4 clusters from the SEC's bulk insider-transaction datasets, enters at the first close after the last filing date (no lookahead), subtracts a 2.5% round trip and compares with IWM. It writes `reports/form4_backtest.md`. Read the caveats in the report: survivorship bias and no point-in-time market-cap filter flatter the result.

## Opportunistic insiders and cross-sectional ranking

`python run.py opportunistic 2023 2025` (Actions: "opportunistic") classifies insider buys as routine or opportunistic (Cohen, Malloy and Pomorski), ranks buy events each month on four fixed features (value, number of buyers, officer involved, drawdown), and reports quintile returns for all names and for liquid names only, net of a liquidity-dependent cost assumption. Output: `reports/form4_opportunistic.md`.

## FCA shorts study

`python run.py fca-study` (Actions: "fca-study") rebuilds each ISIN's aggregate net short from the FCA's archived named positions, finds moves of 0.5pp or more, and measures forward returns versus a UK index ETF with stamp duty and liquidity-tiered costs. It also fills `data/isin_ticker.csv`, which the live FCA pipeline uses for return tracking. Output: `reports/fca_shorts_study.md`.

## Signal feed and track record

`python run.py feed` writes `signals/feed.json` and `signals/feed.md` (current signals with stance avoid, watch or info, and the backtest evidence for each) plus `signals/track_record.md` (what the live signals actually did, versus a benchmark, once enough have a 20-day return). `feed.yml` runs it daily after the FCA update. Every record says plainly that the backtests found no standalone edge: use it as an input, not an instruction.

## Jarvis dashboard

A futuristic, HUD-style market homescreen hosted on GitHub Pages: `https://armaanf-dot.github.io/Trading-signals/`. The `dashboard` workflow rebuilds it every 30 minutes on weekdays (07:00-21:30 UTC), after each `form4`/`fca` run, and on pushes. `python run.py dashboard` builds it locally into `_site/` (serve with `python -m http.server -d _site`).

| Panel | Source | Freshness |
|---|---|---|
| My watchlist (type a ticker in the command bar) | Alpaca IEX websocket, or Finnhub trade websocket | Live, with your own free keys |
| Crypto | Coinbase or Binance public websocket | Live, no key |
| UK markets, US and macro | Yahoo chart endpoint at build time | Delayed (~15 min plus rebuild gap), labelled |
| US insider clusters | `signals/form4_clusters.csv` | Watchlist input only (no edge in backtest) |
| Avoid: rising UK shorts | FCA aggregate snapshots and `signals/fca_events.csv`, rise of 0.5pp+ in 30 days | Avoid filter |
| Most shorted UK, UK combo | latest FCA snapshot, `signals/combo.csv` | Daily |
| Analyst trends | Finnhub free recommendation trends | On demand |
| Market mood gauge | Average move of the S&P 500, Nasdaq 100, Russell 2000, FTSE 100 and FTSE 250, plus the VIX | Live where those prices are live |
| Needs your attention | Moves past each market's "big move" threshold, insider clusters from the last 7 days, big crypto and watchlist swings, the top avoid name | Live |
| Daily brief | Claude once a day on your Claude plan (`CLAUDE_CODE_OAUTH_TOKEN` secret), or the API (`ANTHROPIC_API_KEY`), otherwise rule-based | Each rebuild |

**As an app:** on Windows, press **Get Windows app** on the dashboard, unzip it and double-click `install-app.bat`. It adds a Jarvis shortcut to the Start Menu and desktop that opens in its own window (Edge app mode, no tabs or address bar), and can start Jarvis when you log in. Undo with `app/app-remove.bat`. On a phone or any other computer, open the page in Chrome or Edge and press **Install** (or "Add to Home Screen" in Safari); the page is a PWA with an offline shell.

**Keys:** live-data keys are typed into the page (Keys button) and kept only in that browser's localStorage. They never go into the repo. The optional first name for the greeting is stored the same way. Optional GitHub Secrets: `CLAUDE_CODE_OAUTH_TOKEN` (AI brief on your Claude plan: run `claude setup-token` locally and paste the token), `ANTHROPIC_API_KEY` (API fallback for the brief) and `FINNHUB_API_KEY` (pre-fills analyst trends). **First time:** Settings, Pages, Source "GitHub Actions".

## Return tracking

Every signal CSV has `price_at_signal`, `ret_5d`, `ret_20d` and benchmark columns `bench_ret_5d`, `bench_ret_20d`, measured from the first close after the signal became public. They are filled automatically from free Yahoo Finance closes once the horizon has passed (blank until then). Returns are gross: **subtract spreads (roughly 2-3% round trip on small caps) before trusting any backtest.**

FCA events need a ticker to get returns: add optional `data/isin_ticker.csv` with `isin,ticker` columns.

## Director dealings (manual for now)

Add rows to `data/rns_director_buys.csv` by hand from RNS director/PDMR notices (open-market buys only):

```
date,company,isin,ticker,director,role,shares,price,value_gbp,source_url
```

## Setup

1. Python 3.11, `pip install -r requirements.txt`, `pytest` for the offline tests.
2. Add two **GitHub Secrets** (Settings, Secrets and variables, Actions). Never commit them; the repo is public.
   - `NTFY_TOPIC`: a long random topic name; subscribe to it in the ntfy phone app.
   - `SEC_USER_AGENT`: `"Your Name you@example.com"` (SEC requires it).
3. Locally, export the same two variables. Without `NTFY_TOPIC`, alerts print to the terminal (dry run).
4. First time: Actions tab, run `form4` and `fca` manually with "Run workflow" to validate the live URLs.

## Workflows

- `ci.yml`: secret scan (`scripts/check_secrets.py`) plus tests on every push and PR.
- `form4.yml`: every 2 hours on weekdays. `fca.yml`: daily, then the combo. Both commit updated `data/` and `signals/`.

## Known caveats

- The FCA file URL was checked against the FCA page on 21 November 2026; if it ever 404s, copy the current link from the "Notification and disclosure of net short positions" page.
- The EDGAR feed shows only the latest ~300 filings, so the 2-hourly schedule matters; gaps are not backfilled.
- Parsers are tested offline against fixtures; live formats may drift.
