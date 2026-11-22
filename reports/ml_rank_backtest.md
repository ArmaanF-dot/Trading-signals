# Machine-learning ranking of weak signals (S&P 500 members)

**Verdict:** NO EDGE: out of sample (gbm, top 20%, hold 3) the excess over the equal-weight universe is -0.4% a year (t -0.37) at 0.2% costs, not reliably above zero (at 2% round trip -5.4% a year; at 3% round trip -8.2% a year).

Method: each month-end, 13 price/volume features per point-in-time S&P 500 member (computed to the day before the month's last close), ranked within the month. A gradient-boosted tree model and a ridge baseline learn the rank of next-month return. Walk-forward: refitted each January on an expanding window of past months only; hyperparameters fixed in advance. Buy the top slice equal-weight at the month-end close, overlapping cohorts. Benchmark: equal weight over all priced members. Costs: turnover x half the round trip.

Features: mom_12_1, mom_6_1, rev_1m, rev_1w, vol_1m, vol_12m, max_1m, hi52, beta_12m, dollar_vol, amihud, vol_trend, jump_63.

Chosen on 2005-01 to 2013-01 walk-forward predictions (best net Sharpe at 0.2%): **gbm, top 20%, hold 3**.

## Does the model rank stocks at all? (monthly rank IC, all names)

| model | period | mean IC | IC t-stat | top-bottom decile spread (ann., gross) | spread t |
|---|---|---|---|---|---|
| gbm | selection | +0.010 | 0.78 | +1.2% | 0.22 |
| gbm | test | +0.003 | 0.31 | -0.3% | -0.09 |
| ridge | selection | -0.008 | -0.52 | -2.4% | -0.37 |
| ridge | test | -0.013 | -1.12 | -3.3% | -0.78 |

## Variant comparison (selection period)

| variant | gross CAGR | net CAGR at realistic cost | net Sharpe | monthly turnover |
|---|---|---|---|---|
| gbm, top 10%, hold 1 | 7.8% | 6.0% | 0.37 | 141% |
| gbm, top 10%, hold 3 | 7.7% | 7.0% | 0.41 | 54% |
| gbm, top 20%, hold 1 | 9.0% | 7.5% | 0.44 | 115% |
| gbm, top 20%, hold 3 | 9.8% | 9.2% | 0.51 | 46% |
| ridge, top 10%, hold 1 | 6.7% | 5.1% | 0.33 | 123% |
| ridge, top 10%, hold 3 | 7.5% | 6.9% | 0.40 | 47% |
| ridge, top 20%, hold 1 | 7.0% | 5.7% | 0.37 | 97% |
| ridge, top 20%, hold 3 | 7.5% | 7.0% | 0.42 | 39% |

## Selection period: 2005-02 to 2013-01 (96 months), gbm, top 20%, hold 3

| series | CAGR | Sharpe | max drawdown | excess vs EW universe (ann.) | t-stat |
|---|---|---|---|---|---|
| gross | 9.8% | 0.53 | -60% | +1.7% | 0.92 |
| net_0.002 | 9.2% | 0.51 | -61% | +1.2% | 0.63 |
| net_0.02 | 4.0% | 0.29 | -64% | -3.7% | -2.01 |
| net_0.03 | 1.2% | 0.17 | -66% | -6.5% | -3.48 |
| bench_ew | 8.8% | 0.54 | -53% | +0.0% |  |

## Held-out test: 2013-02 to 2026-10 (165 months), gbm, top 20%, hold 3

| series | CAGR | Sharpe | max drawdown | excess vs EW universe (ann.) | t-stat |
|---|---|---|---|---|---|
| gross | 12.7% | 0.77 | -31% | +0.2% | 0.14 |
| net_0.002 | 12.1% | 0.74 | -31% | -0.4% | -0.37 |
| net_0.02 | 6.7% | 0.45 | -32% | -5.4% | -4.98 |
| net_0.03 | 3.8% | 0.30 | -35% | -8.2% | -7.53 |
| bench_ew | 13.0% | 0.88 | -27% | +0.0% |  |

## Every variant on the held-out test (excess over EW universe, ann.)

| variant | gross | net at 0.2% | net at 2.0% | net at 3.0% | t at realistic cost |
|---|---|---|---|---|---|
| gbm, top 10%, hold 1 | -0.1% | -1.9% | -18.0% | -26.9% | -1.05 |
| gbm, top 10%, hold 3 | +0.3% | -0.3% | -6.2% | -9.4% | -0.25 |
| gbm, top 20%, hold 1 | +0.2% | -1.3% | -14.8% | -22.3% | -0.90 |
| gbm, top 20%, hold 3 | +0.2% | -0.4% | -5.4% | -8.2% | -0.37 |
| ridge, top 10%, hold 1 | -2.5% | -4.1% | -18.6% | -26.7% | -1.67 |
| ridge, top 10%, hold 3 | -2.0% | -2.6% | -7.8% | -10.8% | -1.31 |
| ridge, top 20%, hold 1 | -0.9% | -2.2% | -14.1% | -20.7% | -1.14 |
| ridge, top 20%, hold 3 | -0.9% | -1.4% | -5.7% | -8.1% | -0.91 |

## Single features on the held-out test (mean monthly rank IC from 2013-01)

| feature | mean IC | t-stat | ridge weight (last fit) |
|---|---|---|---|
| mom_12_1 | +0.002 | 0.12 | +0.0001 |
| mom_6_1 | -0.000 | -0.00 | -0.0120 |
| rev_1m | -0.006 | -0.43 | -0.0081 |
| rev_1w | -0.000 | -0.04 | -0.0088 |
| vol_1m | +0.003 | 0.17 | -0.0001 |
| vol_12m | +0.009 | 0.45 | +0.0095 |
| max_1m | +0.003 | 0.21 | -0.0021 |
| hi52 | +0.001 | 0.08 | +0.0164 |
| beta_12m | +0.012 | 0.54 | +0.0085 |
| dollar_vol | +0.008 | 0.95 | -0.0067 |
| amihud | -0.009 | -0.86 | -0.0000 |
| vol_trend | +0.001 | 0.20 | +0.0013 |
| jump_63 | -0.007 | -0.75 | -0.0067 |

## Data and biases

- 1209 tickers were ever members; 760 have Yahoo daily history. 114,617 stock-months in the dataset, median 349 names a month (70% of members). Missing names are mostly delisted or acquired (survivorship bias, which flatters every variant and the benchmark alike).
- 60 stock-month returns above +200% (or at -100%) were dropped as bad data.
- Held names with no next-month price are dropped and the book reweighted, so delisting losses are missed.
- Features stop the day before the trade close; trades fill at the month-end adjusted close.
- No value, quality or true earnings-surprise features: there is no free point-in-time source for 2000 onwards.
- 8 variants were compared (2 models x 4 portfolios) and one picked before the test period; the held-out table shows them all so the choice can be checked.
- The 0.2% round trip is realistic for S&P 500 names; 2%, 3% are the project's house assumptions, shown as a stress test.

Monthly series of the chosen variant: `reports/ml_rank_monthly.csv`.
