# Quality and value tilts on S&P 500 members

**Verdict:** NO EDGE: out of sample the excess over the equal-weight universe is -1.5% a year (t -0.61) at 0.2% costs, not reliably above zero (at 2% round trip -2.1% a year; at 3% round trip -2.4% a year).

Rule: each month-end rank point-in-time S&P 500 members on a fundamental signal built only from SEC XBRL figures already filed by that date, buy the top slice equal-weight, hold with overlapping cohorts. Signals: `gpa` quality: gross profit / assets; `bm` value: book / market; `ep` value: earnings / price; `qv` quality + value (gpa and bm ranks). Monthly Yahoo adjusted closes. Benchmark: equal weight over every member with that signal that month (isolates the ranking from the market). Costs: turnover x half the round trip.

Chosen in sample (best net Sharpe at 0.2%, formations before 2018-07): **qv, top 20%, hold 12** (quality + value (gpa and bm ranks)).

## In-sample variant comparison (formations before the split)

| variant | gross CAGR | net CAGR | net Sharpe | excess vs EW (ann.) | t-stat | monthly turnover |
|---|---|---|---|---|---|---|
| gpa, top 10%, hold 3 | 16.9% | 16.8% | 1.27 | -0.8% | -0.39 | 6% |
| gpa, top 10%, hold 12 | 16.7% | 16.6% | 1.27 | -1.0% | -0.47 | 5% |
| gpa, top 20%, hold 3 | 16.3% | 16.2% | 1.32 | -1.5% | -0.86 | 6% |
| gpa, top 20%, hold 12 | 16.5% | 16.5% | 1.36 | -1.2% | -0.73 | 5% |
| bm, top 10%, hold 3 | 15.9% | 15.7% | 0.84 | +0.4% | 0.10 | 10% |
| bm, top 10%, hold 12 | 15.1% | 15.0% | 0.82 | -0.3% | -0.08 | 5% |
| bm, top 20%, hold 3 | 15.8% | 15.7% | 0.99 | -0.3% | -0.16 | 8% |
| bm, top 20%, hold 12 | 15.7% | 15.7% | 1.01 | -0.4% | -0.18 | 5% |
| ep, top 10%, hold 3 | 14.8% | 14.5% | 0.89 | -1.4% | -0.55 | 19% |
| ep, top 10%, hold 12 | 16.1% | 15.9% | 1.03 | -0.3% | -0.15 | 12% |
| ep, top 20%, hold 3 | 15.3% | 15.1% | 1.02 | -1.2% | -0.62 | 16% |
| ep, top 20%, hold 12 | 16.2% | 16.1% | 1.12 | -0.5% | -0.27 | 10% |
| qv, top 10%, hold 3 | 18.5% | 18.3% | 1.29 | +0.5% | 0.18 | 14% |
| qv, top 10%, hold 12 | 18.8% | 18.7% | 1.33 | +0.9% | 0.34 | 7% |
| qv, top 20%, hold 3 | 17.5% | 17.3% | 1.32 | -0.5% | -0.25 | 12% |
| qv, top 20%, hold 12 | 17.9% | 17.9% | 1.39 | -0.0% | -0.02 | 7% |

## In sample, chosen variant: 2010-07 to 2018-07 (97 months)

| series | CAGR | Sharpe | max drawdown | excess vs EW universe (ann.) | t-stat |
|---|---|---|---|---|---|
| gross | 17.9% | 1.40 | -14% | +0.1% | 0.03 |
| net_0.002 | 17.9% | 1.39 | -14% | -0.0% | -0.02 |
| net_0.02 | 17.0% | 1.34 | -15% | -0.8% | -0.42 |
| net_0.03 | 16.6% | 1.31 | -15% | -1.2% | -0.64 |
| bench_ew | 17.8% | 1.36 | -18% | +0.0% |  |

## Out of sample, chosen variant: 2018-08 to 2026-11 (100 months)

| series | CAGR | Sharpe | max drawdown | excess vs EW universe (ann.) | t-stat |
|---|---|---|---|---|---|
| gross | 8.8% | 0.51 | -34% | -1.4% | -0.58 |
| net_0.002 | 8.8% | 0.50 | -34% | -1.5% | -0.61 |
| net_0.02 | 8.1% | 0.47 | -34% | -2.1% | -0.86 |
| net_0.03 | 7.8% | 0.46 | -34% | -2.4% | -1.00 |
| bench_ew | 11.0% | 0.66 | -25% | +0.0% |  |

## Every variant out of sample (for context only; the verdict uses the in-sample choice)

| variant | net CAGR | excess vs EW (ann.) | t-stat |
|---|---|---|---|
| gpa, top 10%, hold 3 | 8.0% | -2.5% | -1.04 |
| gpa, top 10%, hold 12 | 9.0% | -1.5% | -0.67 |
| gpa, top 20%, hold 3 | 9.2% | -1.4% | -0.83 |
| gpa, top 20%, hold 12 | 9.7% | -0.9% | -0.53 |
| bm, top 10%, hold 3 | 10.1% | +1.5% | 0.32 |
| bm, top 10%, hold 12 | 10.7% | +1.9% | 0.41 |
| bm, top 20%, hold 3 | 10.8% | +1.0% | 0.31 |
| bm, top 20%, hold 12 | 11.1% | +1.3% | 0.37 |
| ep, top 10%, hold 3 | 10.0% | +0.9% | 0.22 |
| ep, top 10%, hold 12 | 10.7% | +1.2% | 0.32 |
| ep, top 20%, hold 3 | 10.6% | +0.9% | 0.27 |
| ep, top 20%, hold 12 | 11.1% | +1.2% | 0.39 |
| qv, top 10%, hold 3 | 6.3% | -3.4% | -0.98 |
| qv, top 10%, hold 12 | 6.8% | -2.8% | -0.79 |
| qv, top 20%, hold 3 | 7.7% | -2.5% | -1.00 |
| qv, top 20%, hold 12 | 8.8% | -1.5% | -0.61 |

## Data and biases

- 841 tickers were ever members after 2010-06; 621 map to a current SEC CIK and 621 of those have Yahoo history. Companies that were delisted, acquired or renamed have no current CIK, so they are missing (survivorship bias, as in the momentum study).
- Members per month with prices and a CIK: median 411. Share of those with the chosen signal: median 50%, min 36% (banks and insurers have no gross profit, so `gpa` and `qv` skip most financials).
- Point in time: each XBRL value is used only from its SEC `filed` date; fiscal-year figures older than 480 days and balance sheets older than 200 days are treated as missing.
- Tickers are matched to companies by today's SEC ticker list, so a recycled ticker could pair one company's prices with another's filings when both filed in the same years. This is rare in the S&P 500 but not checked.
- 26 stock-month returns above +200% (or at -100%) were dropped as bad data. Held names with no next-month price are dropped and the book reweighted, so delisting losses are missed.
- Average monthly turnover of the chosen variant: 6%.
- The 0.2% round trip is realistic for S&P 500 names; 2%, 3% are the project's small-cap house assumptions and are shown as a stress test.
- Sanity check, market caps at 2015-12: AAPL $587bn, MSFT $443bn, NVDA $18bn, JPM $243bn.

Monthly series of the chosen variant: `reports/quality_value_monthly.csv`.

<!-- risk-sizing:start -->
## Risk and sizing

Period 2018-08 to 2026-11 (100 months), realistic costs. Net book: Sharpe 0.50, volatility 21.3%, max drawdown -34%. Edge (net excess over the benchmark): Sharpe -0.21, volatility 7.0%, max drawdown -21%.

**Suggested leverage:** None: out-of-sample edge Sharpe -0.21 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns.

Leverage is suggested only when the out-of-sample edge Sharpe, net of costs, is at least 1.0 over 36+ months; it then targets 10% volatility, capped by half-Kelly and 2x. Not financial advice.

All studies side by side: `reports/risk_summary.md`.
<!-- risk-sizing:end -->
