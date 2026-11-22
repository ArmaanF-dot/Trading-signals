# Risk-adjusted record of the studies

**Verdict:** no study earns leverage: none showed an edge out of sample. Leverage is suggested only when the out-of-sample edge Sharpe, net of costs, is at least 1.0 over 36+ months; it then targets 10% volatility, capped by half-Kelly and 2x. Not financial advice.

Out-of-sample periods where a study chose a variant (whole sample for event rules with nothing fitted), at the realistic cost for each universe. **Net** is the book itself after costs; a long-only book's Sharpe is mostly the market's, so read **edge** (net excess over the benchmark, i.e. a market-hedged book) to judge the signal. Event studies are monthly cohorts of 20-day trades (cash in months with no signal), annualised with sqrt(12).

| study | period | net Sharpe | net max drawdown | edge Sharpe | edge vol | edge max drawdown | suggested leverage |
|---|---|---|---|---|---|---|---|
| 12-1 momentum (S&P 500) | 2013-02 to 2026-11 | 0.83 | -20% | -0.01 | 7.9% | -21% | none |
| Short-term reversal (S&P 500) | 2013-01 to 2026-11 | 0.42 | -39% | -0.46 | 9.9% | -53% | none |
| ML rank, gradient boosting (S&P 500) | 2013-02 to 2026-10 | 0.74 | -31% | -0.10 | 4.0% | -13% | none |
| Quality and value tilts (S&P 500) | 2018-08 to 2026-11 | 0.50 | -34% | -0.21 | 7.0% | -21% | none |
| Frontier country ETFs | 2016-02 to 2026-11 | -0.07 | -31% | -0.22 | 8.0% | -30% | none |
| Form 4 cluster buys (US) | 2023-01 to 2026-01 | -1.11 | -57% | -2.77 | 13.3% | -71% | none |
| Form 4 opportunistic insiders (US) | 2023-01 to 2026-01 | -0.10 | -30% | -3.54 | 5.3% | -44% | none |
| FCA short rises, shorted (UK) | 2016-12 to 2026-07 | -1.46 | -96% | -1.64 | 12.2% | -87% | none |
| Post-earnings drift, top quintile (US) | 2022-01 to 2026-10 | 0.09 | -21% | -1.29 | 7.6% | -44% | none |

## Notes

- **12-1 momentum (S&P 500)**: None: out-of-sample edge Sharpe -0.01 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns.
- **Short-term reversal (S&P 500)**: None: out-of-sample edge Sharpe -0.46 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns. Daily book compounded to months.
- **ML rank, gradient boosting (S&P 500)**: None: out-of-sample edge Sharpe -0.10 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns.
- **Quality and value tilts (S&P 500)**: None: out-of-sample edge Sharpe -0.21 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns.
- **Frontier country ETFs**: None: out-of-sample edge Sharpe -0.22 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns. Edge is the long-only excess over the equal-weight ETF basket, net of costs.
- **Form 4 cluster buys (US)**: None: out-of-sample edge Sharpe -2.77 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns. 20-day trades, 2.5% round trip, edge vs IWM. No fitted parameters.
- **Form 4 opportunistic insiders (US)**: None: out-of-sample edge Sharpe -3.54 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns. 20-day trades, liquidity-tiered costs.
- **FCA short rises, shorted (UK)**: None: out-of-sample edge Sharpe -1.64 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns. Short the stock for 20 days after a rise; borrow cost ignored, so this flatters it.
- **Post-earnings drift, top quintile (US)**: None: out-of-sample edge Sharpe -1.29 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns. Out of sample from 2022; 20-day trades, edge vs SPY.

A Sharpe estimated from N years has a standard error of roughly 1/sqrt(N), so 10 years cannot tell 0.3 from 0.9. Several variants were tried in each study, which biases the best one upwards. Built by `python run.py risk`.
