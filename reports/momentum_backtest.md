# 12-1 momentum on S&P 500 members

**Verdict:** NO EDGE: out of sample the excess over the equal-weight universe is -0.1% a year (t -0.04) at 0.2% costs, not reliably above zero (at 2% round trip -3.8% a year; at 3% round trip -5.9% a year).

Rule: each month-end rank point-in-time S&P 500 members by return from month t-12 to t-1, buy the top slice equal-weight, hold with overlapping cohorts. Monthly Yahoo adjusted closes. Benchmark: equal weight over all priced members at formation (isolates the stock selection from the market). Costs: turnover x half the round trip.

Chosen in sample (best net Sharpe at 0.2%, formations before 2013-01): **top 20%, hold 2 month(s)**.

## In-sample variant comparison (formations before the split)

| variant | gross CAGR | net CAGR at realistic cost | net Sharpe | monthly turnover |
|---|---|---|---|---|
| top 10%, hold 1 | 6.6% | 5.8% | 0.38 | 61% |
| top 10%, hold 2 | 5.7% | 5.2% | 0.35 | 42% |
| top 20%, hold 1 | 7.5% | 6.8% | 0.47 | 51% |
| top 20%, hold 2 | 8.0% | 7.5% | 0.50 | 36% |

## In sample: 2000-02 to 2013-01 (156 months)

| series | CAGR | Sharpe | max drawdown | excess vs EW universe (ann.) | t-stat |
|---|---|---|---|---|---|
| gross | 8.0% | 0.53 | -52% | -2.1% | -0.69 |
| net_0.002 | 7.5% | 0.50 | -52% | -2.6% | -0.83 |
| net_0.02 | 3.4% | 0.28 | -55% | -6.5% | -2.11 |
| net_0.03 | 1.2% | 0.16 | -57% | -8.6% | -2.82 |
| bench_ew | 10.2% | 0.64 | -54% | +0.0% |  |

## Out of sample: 2013-02 to 2026-11 (166 months)

| series | CAGR | Sharpe | max drawdown | excess vs EW universe (ann.) | t-stat |
|---|---|---|---|---|---|
| gross | 12.8% | 0.85 | -20% | +0.3% | 0.16 |
| net_0.002 | 12.4% | 0.83 | -20% | -0.1% | -0.04 |
| net_0.02 | 8.3% | 0.59 | -22% | -3.8% | -1.80 |
| net_0.03 | 6.1% | 0.46 | -24% | -5.9% | -2.77 |
| bench_ew | 12.5% | 0.85 | -27% | +0.0% |  |

## Data and biases

- 1209 tickers were ever members; 766 have Yahoo history. Eligible share of members per month: median 70%, min 46%. Missing names are mostly delisted or acquired companies (survivorship bias).
- 60 stock-month returns above +200% (or at -100%) were dropped as bad data.
- Held names with no next-month price are dropped and the book reweighted, so delisting losses are missed.
- Average monthly turnover of the chosen variant: 35% (sum of absolute weight changes).
- The 0.2% round trip is realistic for S&P 500 names; 2%, 3% are the project's small-cap house assumptions and are shown as a stress test.

Monthly series: `reports/momentum_monthly.csv`.
