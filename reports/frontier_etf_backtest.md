# Commodity-linked country ETFs: do they lag their commodity?

**Verdict:** NO EDGE: out of sample the long-short earns -10.5% a year (t -1.79) at 0.3% costs (at 2% round trip -36.7% a year; at 3% round trip -52.1% a year).

Rule: each month-end rank single-country ETFs by a commodity signal (raw = linked commodity return; gap = beta x commodity return minus the ETF's own return, i.e. the move not yet priced), long the top third, short the bottom third, equal weight, hold one month. Monthly Yahoo adjusted closes for ETFs and continuous front-month futures. Costs: turnover x half the round trip.

Chosen in sample (best net Sharpe at 0.3%, formations before 2016-01): **gap signal, 1 month look-back**.

## In-sample variant comparison

| variant | gross ann. | net Sharpe | mean rank IC | IC t | monthly turnover |
|---|---|---|---|---|---|
| raw, 1m | 0.3% | -0.24 | -0.046 | -0.65 | 259% |
| raw, 3m | 11.8% | 0.65 | +0.060 | 0.69 | 168% |
| gap, 1m | 31.9% | 2.22 | +0.168 | 1.75 | 271% |
| gap, 3m | 3.4% | 0.09 | +0.056 | 0.39 | 167% |

## Out-of-sample variant comparison (for transparency, not used to choose)

| variant | gross ann. | net Sharpe | mean rank IC | IC t |
|---|---|---|---|---|
| raw, 1m | -4.1% | -0.55 | -0.041 | -1.02 |
| raw, 3m | 7.7% | 0.37 | +0.039 | 0.86 |
| gap, 1m | -6.5% | -0.83 | -0.096 | -2.16 |
| gap, 3m | 0.6% | -0.16 | +0.014 | 0.24 |

## In sample: 2011-08 to 2015-02 (17 months)

| series | ann. return | Sharpe | max drawdown | t-stat |
|---|---|---|---|---|
| gross | 31.9% | 2.70 | -2% | 3.21 |
| net_0.003 | 25.8% | 2.22 | -3% | 2.64 |
| net_0.02 | -4.5% | -0.34 | -10% | -0.40 |
| net_0.03 | -19.0% | -1.60 | -25% | -1.90 |

Long leg minus the equal-weight ETF universe: +22.1% a year gross (t 3.06). Mean rank IC +0.168 (t 1.75).

## Out of sample: 2017-05 to 2026-02 (56 months)

| series | ann. return | Sharpe | max drawdown | t-stat |
|---|---|---|---|---|
| gross | -6.5% | -0.47 | -35% | -1.01 |
| net_0.003 | -10.7% | -0.83 | -42% | -1.79 |
| net_0.02 | -31.7% | -2.79 | -83% | -6.04 |
| net_0.03 | -41.9% | -3.85 | -92% | -8.31 |

Long leg minus the equal-weight ETF universe: -1.7% a year gross (t -0.48). Mean rank IC -0.096 (t -2.16).

## Data and biases

- ETFs priced: ECH (from 2007-11), EPU (from 2009-06), EZA (from 2003-02), ENOR (from 2012-01), EWC (from 1997-01), EWA (from 1997-01), EWW (from 1997-01), KSA (from 2015-09), ARGT (from 2011-03).
- Only ETFs that still trade are included (dead ones such as the Russia and Nigeria ETFs are missing): survivorship bias flatters long positions.
- Only 10 ETFs and 3 per leg, so results are noisy; in-sample window is short (about 4.5 years).
- Futures are Yahoo continuous front-month series; roll gaps add noise to commodity returns.
- Shorting these ETFs from a UK retail account means CFDs or spread bets with financing costs not modelled here; the long leg is the practical one.
- Average monthly turnover of the chosen variant: 260%.

Monthly series: `reports/frontier_etf_monthly.csv`.
