# Commodity-linked country ETFs: do they lag their commodity?

**Verdict:** NO EDGE: out of sample the long-short earns -1.0% a year (t -0.24) at 0.3% costs (at 2% round trip -16.3% a year; at 3% round trip -25.3% a year).

Rule: each month-end rank single-country ETFs by a commodity signal (raw = linked commodity return; gap = beta x commodity return minus the ETF's own return, i.e. the move not yet priced), long the top third, short the bottom third, equal weight, hold one month. Monthly Yahoo adjusted closes for ETFs and continuous front-month futures. Costs: turnover x half the round trip.

Chosen in sample (best net Sharpe at 0.3%, formations before 2016-01): **gap signal, 3 month look-back**.

## In-sample variant comparison

| variant | gross ann. | net Sharpe | mean rank IC | IC t | monthly turnover |
|---|---|---|---|---|---|
| raw, 1m | -1.7% | -0.40 | -0.063 | -1.18 | 271% |
| raw, 3m | 1.4% | -0.04 | -0.006 | -0.10 | 162% |
| gap, 1m | 19.2% | 1.01 | +0.108 | 2.10 | 305% |
| gap, 3m | 20.2% | 1.15 | +0.152 | 2.47 | 224% |

## Out-of-sample variant comparison (for transparency, not used to choose)

| variant | gross ann. | net Sharpe | mean rank IC | IC t |
|---|---|---|---|---|
| raw, 1m | -3.5% | -0.50 | -0.041 | -1.21 |
| raw, 3m | 0.8% | -0.08 | -0.029 | -0.88 |
| gap, 1m | 1.0% | -0.19 | -0.022 | -0.69 |
| gap, 3m | 0.8% | -0.07 | -0.014 | -0.42 |

## In sample: 2011-07 to 2016-01 (55 months)

| series | ann. return | Sharpe | max drawdown | t-stat |
|---|---|---|---|---|
| gross | 20.2% | 1.45 | -10% | 3.10 |
| net_0.003 | 15.5% | 1.15 | -11% | 2.47 |
| net_0.02 | -8.0% | -0.55 | -38% | -1.18 |
| net_0.03 | -19.7% | -1.51 | -66% | -3.24 |

Long leg minus the equal-weight ETF universe: +11.1% a year gross (t 2.91). Mean rank IC +0.152 (t 2.47).

## Out of sample: 2016-02 to 2026-11 (130 months)

| series | ann. return | Sharpe | max drawdown | t-stat |
|---|---|---|---|---|
| gross | 0.8% | 0.13 | -30% | 0.42 |
| net_0.003 | -1.9% | -0.07 | -31% | -0.24 |
| net_0.02 | -15.9% | -1.20 | -85% | -3.96 |
| net_0.03 | -23.3% | -1.84 | -95% | -6.07 |

Long leg minus the equal-weight ETF universe: +1.0% a year gross (t 0.41). Mean rank IC -0.014 (t -0.42).

## Data and biases

- ETFs priced: ECH (from 2007-11), EPU (from 2009-06), EZA (from 2003-02), ENOR (from 2012-01), EWC (from 1998-01), EWA (from 1998-01), EWW (from 1998-01), KSA (from 2015-09), ARGT (from 2011-03); no Yahoo history for GXG (delisted).
- Only ETFs that still trade are included (dead ones such as the Russia and Nigeria ETFs are missing): survivorship bias flatters long positions.
- Only 10 ETFs and 3 per leg, so results are noisy; in-sample window is short (about 4.5 years).
- Futures are Yahoo continuous front-month series; roll gaps add noise to commodity returns.
- Shorting these ETFs from a UK retail account means CFDs or spread bets with financing costs not modelled here; the long leg is the practical one.
- Average monthly turnover of the chosen variant: 172%.

Monthly series: `reports/frontier_etf_monthly.csv`.
