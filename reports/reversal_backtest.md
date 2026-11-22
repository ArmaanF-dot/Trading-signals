# Short-term mean reversion on S&P 500 members

**Verdict:** NO EDGE: out of sample the excess over the equal-weight universe is -4.7% a year (t -1.67) at 0.2% costs, not reliably above zero (at 2% round trip -81% a year; at 3% round trip -121% a year).

Rule: after each close, rank point-in-time S&P 500 members by their return over the last k trading days, buy the worst 10% equal-weight at the next open, sell at the open h trading days later; a new cohort every day, h cohorts live. Optional filter: only stocks above their 200-day average. Yahoo prices adjusted for splits and dividends. Benchmark: equal weight over all priced members (isolates the stock selection from the market). Costs: daily turnover x half the round trip. Statistics on monthly compounded returns.

Chosen in sample (best net Sharpe at 0.2%, days before 2013-01-01): **5-day dip, hold 5d**.

## In-sample variant comparison (days before the split)

| variant | gross CAGR | gross excess vs EW (ann.) | net CAGR at realistic cost | net Sharpe | daily turnover |
|---|---|---|---|---|---|
| 3-day dip, hold 5d | 27.6% | +15.7% | 17.2% | 0.74 | 34% |
| 3-day dip, hold 5d, above 200d avg | 21.2% | +9.0% | 11.2% | 0.71 | 35% |
| 3-day dip, hold 10d | 22.4% | +11.2% | 17.3% | 0.76 | 17% |
| 3-day dip, hold 10d, above 200d avg | 15.8% | +4.3% | 10.9% | 0.70 | 17% |
| 5-day dip, hold 5d | 29.8% | +17.6% | 19.1% | 0.79 | 34% |
| 5-day dip, hold 5d, above 200d avg | 20.9% | +8.9% | 10.8% | 0.68 | 35% |
| 5-day dip, hold 10d | 23.2% | +12.1% | 18.1% | 0.77 | 17% |
| 5-day dip, hold 10d, above 200d avg | 15.8% | +4.2% | 10.8% | 0.70 | 18% |

## In sample: 2000-01-03 to 2012-12-31 (156 months)

| series | CAGR | Sharpe | max drawdown | excess vs EW universe (ann.) | t-stat |
|---|---|---|---|---|---|
| gross | 29.8% | 1.11 | -38% | +17.6% | 4.85 |
| net_0.002 | 19.1% | 0.79 | -44% | +8.7% | 2.46 |
| net_0.02 | -45.2% | -2.30 | -100% | -68.0% | -22.34 |
| net_0.03 | -64.5% | -4.18 | -100% | -108.6% | -38.49 |
| bench_ew | 11.1% | 0.66 | -52% | +0.0% |  |

## Out of sample: 2013-01-02 to 2026-11-19 (167 months)

| series | CAGR | Sharpe | max drawdown | excess vs EW universe (ann.) | t-stat |
|---|---|---|---|---|---|
| gross | 16.7% | 0.80 | -38% | +4.1% | 1.43 |
| net_0.002 | 7.0% | 0.42 | -39% | -4.7% | -1.67 |
| net_0.02 | -51.0% | -3.28 | -100% | -81.0% | -33.23 |
| net_0.03 | -68.3% | -5.48 | -100% | -121.4% | -53.25 |
| bench_ew | 13.4% | 0.87 | -30% | +0.0% |  |

## Out of sample by year (excess over the EW universe)

| year | gross | net at 0.2% |
|---|---|---|
| 2013 | +8.1% | -3.8% |
| 2014 | -0.4% | -10.0% |
| 2015 | -6.1% | -13.4% |
| 2016 | +1.8% | -8.2% |
| 2017 | +4.8% | -5.5% |
| 2018 | +5.8% | -2.3% |
| 2019 | +1.9% | -9.4% |
| 2020 | +19.5% | +8.2% |
| 2021 | +3.5% | -7.7% |
| 2022 | +1.2% | -6.3% |
| 2023 | +1.1% | -8.5% |
| 2024 | -4.6% | -13.7% |
| 2025 | +8.1% | -1.9% |
| 2026 | +5.8% | -2.9% |

## Data and biases

- Out of sample the gross excess (before any costs) is +4.1% a year; the round-trip cost that would wipe it out is about 0.09%.
- 1209 tickers were ever members; 759 have Yahoo history. Eligible share of members per day: median 93%, min 78%. Missing names are mostly delisted or acquired companies (survivorship bias: the dips that ended in delisting are under-represented, which flatters dip buying).
- 243 stock-day open-to-open returns above +100% (or at -100%) were dropped as bad data.
- Held names with no next price are dropped and the book reweighted, so delisting losses are missed.
- Average daily turnover of the chosen variant: 34% (sum of absolute weight changes).
- The 0.2% round trip is realistic for S&P 500 names with a commission-free broker; 2%, 3% are the project's small-cap house assumptions, shown as a stress test.

Daily series: `reports/reversal_daily.csv`.

<!-- risk-sizing:start -->
## Risk and sizing

Period 2013-01 to 2026-11 (167 months), realistic costs. Net book: Sharpe 0.42, volatility 22.1%, max drawdown -39%. Edge (net excess over the benchmark): Sharpe -0.46, volatility 9.9%, max drawdown -53%.

**Suggested leverage:** None: out-of-sample edge Sharpe -0.46 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns.

Leverage is suggested only when the out-of-sample edge Sharpe, net of costs, is at least 1.0 over 36+ months; it then targets 10% volatility, capped by half-Kelly and 2x. Not financial advice.

All studies side by side: `reports/risk_summary.md`.
<!-- risk-sizing:end -->
