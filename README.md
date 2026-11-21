# Trading signals

Cheap, free-data signals for markets institutions ignore (UK/US small caps). Daily batch jobs on GitHub Actions, alerts to your phone via [ntfy](https://ntfy.sh), CSV outputs that feed a paper-first trading bot. *Not financial advice. Paper trade first.*

## Signals

| Command | Signal | Output |
|---|---|---|
| `python run.py form4` | US SEC Form 4 cluster buys: at least 2 insiders, 10 days, $100k+ | `data/form4_buys.csv`, `signals/form4_clusters.csv` |
| `python run.py fca` | FCA named-fund short positions: daily diff (new / cover / increase / decrease) | `data/fca_shorts/*.csv`, `signals/fca_events.csv` |
| `python run.py combo` | UK director buy (RNS) on an ISIN where funds are net short | `signals/combo.csv` |
| `python run.py all` | All of the above | |

Thresholds live in `config.py`.

## Return tracking

Every signal CSV has `price_at_signal`, `ret_5d` and `ret_20d` columns. They are filled automatically from free Stooq closes once the horizon has passed (blank until then). Returns are gross: **subtract spreads (roughly 2-3% round trip on small caps) before trusting any backtest.**

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

- The FCA spreadsheet URL in `config.py` is unverified; if the first run 404s, copy the current link from the FCA short positions page.
- The EDGAR feed shows only the latest ~300 filings, so the 2-hourly schedule matters; gaps are not backfilled.
- Parsers are tested offline against fixtures; live formats may drift.
