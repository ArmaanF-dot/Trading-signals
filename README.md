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

`python run.py momentum` (Actions: "momentum") backtests 12-1 month cross-sectional momentum on point-in-time S&P 500 members since 2000 (top decile or quintile, held 1 or 2 months with overlapping cohorts), against an equal-weight universe benchmark. Variants are chosen on formations before 2013 and judged on 2013 onwards, at a realistic 0.2% round trip and the house 2% and 3%. Output: `reports/momentum_backtest.md` and `reports/momentum_monthly.csv`.

`python run.py ml-rank` (Actions: "ml-rank") tests whether machine learning can combine weak price/volume features (momentum, reversal, volatility, 52-week high, beta, liquidity, volume trend, biggest recent 3-day move) into a ranking of point-in-time S&P 500 members. A gradient-boosted tree model and a ridge baseline are refitted each January on past months only (walk-forward), and the top slice is held 1 or 3 months. Variants are chosen on 2005-2012 predictions and judged on 2013 onwards at 0.2%, 2% and 3% round trips. Output: `reports/ml_rank_backtest.md` and `reports/ml_rank_monthly.csv`.

`python run.py oil-tanks` tests whether free Sentinel-2 images (10 m) of the Cushing, Oklahoma tank farm can track EIA weekly Cushing crude stocks, by measuring the roof shadows of floating-roof tanks across 2018-2026. It runs offline from `data/oil_tanks/`; `scripts/oil_tanks_fetch.py` rebuilds the shadow file from the public AWS archive. Verdict: a faint real signal, far too noisy to call weekly changes, so no edge. Output: `reports/oil_tank_satellite.md`.

## Post-earnings drift study

`python run.py pead-study` (Actions: "pead-study") tests post-earnings announcement drift on liquid US stocks (20-day average dollar volume at least $20m, price at least $5). Earnings dates are 8-K filings with Item 2.02 from EDGAR; the surprise is the stock's reaction around the filing minus SPY. Events are ranked into quintiles against the previous quarter's reactions only, entered one close after the reaction is known, and held 20, 40 and 60 trading days. The rule (buy the top quintile) is judged out of sample (2022 onward) after realistic and 2.5% costs. Output: `reports/pead_study.md` and `reports/pead_events.csv.gz`.

## Signal feed and track record

`python run.py feed` writes `signals/feed.json` and `signals/feed.md` (current signals with stance avoid, watch or info, and the backtest evidence for each) plus `signals/track_record.md` (what the live signals actually did, versus a benchmark, once enough have a 20-day return). `feed.yml` runs it daily after the FCA update. Every record says plainly that the backtests found no standalone edge: use it as an input, not an instruction.

## Sharpe, drawdown and leverage sizing

`python run.py risk` (also run after every study) writes `reports/risk_summary.md` and `.json`: for each study's out-of-sample period at realistic costs, the Sharpe ratio, volatility and max drawdown of the book itself (net) and of its excess over the benchmark (edge, a market-hedged book), plus a leverage line. It also adds a "Risk and sizing" section to each study's own report. Event studies become monthly cohorts of 20-day trades. The live track record (`signals/track_record.md` and `.json`) gets the same measures, and Baco shows both in its "Risk-adjusted record" card.

The leverage rule is deliberately conservative: none unless the out-of-sample edge Sharpe net of costs is at least 1.0 over 36 months or more, then size to 10% volatility, capped by half-Kelly and 2x. No study so far qualifies.

## Baco dashboard

A professional, lively homescreen with a voice assistant, hosted on GitHub Pages: `https://armaanf-dot.github.io/Trading-signals/`. Baco is said "bay-coe" (the page spells it that way when it speaks). The `dashboard` workflow rebuilds it every 30 minutes on weekdays (07:00-21:30 UTC), after each `form4`/`fca` run, and on pushes. `python run.py dashboard` builds it locally into `_site/` (serve with `python -m http.server -d _site`).

Six sections (tabs): **Overview**, **Portfolio**, **Calendar**, **Fight night**, **Signals**, **Tools**.

| Panel | Source | Freshness |
|---|---|---|
| Watchlist (type a ticker in the add box) | Alpaca IEX websocket, or Finnhub trade websocket | Live, with your own free keys |
| Crypto | Coinbase or Binance public websocket | Live, no key |
| UK markets, US and macro | Yahoo chart endpoint at build time | Delayed (~15 min plus rebuild gap), labelled |
| Getting around: bus to Warwick | bustimes.org (national bus timetable plus live running where available), `config.TRAVEL` | Timetable exact; live status as at the last build |
| Getting around: tube from Northwood | TfL open API, called by the browser, no key | Live, every 30 seconds |
| Coming up, Calendar: earnings | Nasdaq public earnings calendar, 14 days, biggest companies plus your watchlist, portfolio and insider names | Each build |
| Calendar: economy | Forex Factory weekly JSON, high and medium impact USD, GBP and EUR | Each build |
| Headlines | BBC News business RSS and Yahoo Finance RSS (titles and links only) | Each build |
| Portfolio (holdings, cash, value over time, allocation, against the S&P 500) | You type holdings; prices from the live feeds above; history saved in your browser | Live where priced |
| Fight night (UFC model picks, potential bets, bet tracker) | `data/ufc_predictions.json` or a model file loaded in the browser, see below | When you refresh it |
| Tools | Position-size, bet value and Kelly stake, cost and currency calculators, notebook, backup | Local |
| US insider clusters | `signals/form4_clusters.csv` | Watchlist input only (no edge in backtest) |
| Avoid: rising UK shorts | FCA aggregate snapshots and `signals/fca_events.csv`, rise of 0.5pp+ in 30 days | Avoid filter |
| Most shorted UK, UK combo | latest FCA snapshot, `signals/combo.csv` | Daily |
| Analyst trends | Finnhub free recommendation trends | On demand |
| Market mood | Animated gauge: needle at the average move of the S&P 500, Nasdaq 100, Russell 2000, FTSE 100 and FTSE 250, a marker per index, a bar per index around zero, plus the VIX | Live where those prices are live |
| Needs your attention | Moves past each market's "big move" threshold, insider clusters, big crypto, watchlist and portfolio swings, your earnings, fight night, the next bus, the top avoid name | Live |
| Ask Baco | Typed or spoken questions, answered in the page from the data above (portfolio, bets, earnings, UFC picks, next bus or tube, markets) and read aloud | Live |
| Daily brief | Claude once a day on your Claude plan (`CLAUDE_CODE_OAUTH_TOKEN` secret), or the API (`ANTHROPIC_API_KEY`), otherwise rule-based | Each rebuild |

**UFC model (Fight night).** The model is in `ArmaanF-dot/MMA-betting`; its `scripts/signal_data.py` writes `ufc-ui/data.json`, which that repo git-ignores because it holds scraped bookmaker prices. Two ways in: (1) press **Load model file** on Fight night and choose that file: it is converted in your browser, kept only in this browser, and shows prices, edges and stakes; (2) to see the model's own picks on every device, run `python run.py ufc ../MMA-betting/ufc-ui/data.json` here and commit `data/ufc_predictions.json`. That export is public-safe: probabilities, picks, confidence and drivers only, no bookmaker prices, books or stakes. Its schema (version 1) is documented at the top of `edge/ufc.py`. On the page you type the price you can get, and Baco shows the edge and a cautious stake (quarter Kelly, capped at 5% of the bankroll). "Show sample" displays made-up fighters so you can see the layout. The tests so far show no proven edge over bookmaker prices, so everything is labelled paper trading.

**Travel.** Stops and walking times live in `config.TRAVEL` (a public bus stop and a tube station, no address); the walk times can also be changed in Settings. The "Wheatsheaf" stop on Tachbrook Road (`4200F036401`) is the south-bound side whose buses go away from the University, so the University-bound U1 and U1A are read from the stop on the other side (`4200F206801`, named Cashmore Avenue in the national stop list). Only services that go on to call at a stop containing "University" are shown. Bus Open Data Service live vehicle positions would need a free key stored as a GitHub Secret; not needed for this.

**As an app:** on Windows, press **Get Windows app** on the dashboard, unzip it and double-click `install-app.bat`. It adds a Baco shortcut to the Start Menu and desktop that opens in its own window (Edge app mode, no tabs or address bar), and can start Baco when you log in. Undo with `app/app-remove.bat`. On a phone or any other computer, open the page in Chrome or Edge and press **Install** (or "Add to Home Screen" in Safari); the page is a PWA with an offline shell.

**Keys:** live-data keys are typed into the page (Settings button) and kept only in that browser's localStorage. They never go into the repo. The optional first name for the greeting is stored the same way. Optional GitHub Secrets: `CLAUDE_CODE_OAUTH_TOKEN` (AI brief on your Claude plan: run `claude setup-token` locally and paste the token), `ANTHROPIC_API_KEY` (API fallback for the brief) and `FINNHUB_API_KEY` (pre-fills analyst trends). **First time:** Settings, Pages, Source "GitHub Actions".

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
