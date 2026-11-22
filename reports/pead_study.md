# Post-earnings announcement drift (US, liquid stocks)

Companies: 3754 (NYSE/Nasdaq, today's SEC list). Earnings 8-Ks (Item 2.02): 88409; priced with a reaction: 87950; liquid (20-day ADV >= $20m, price >= $5) and ranked: 44900.

Surprise = earnings announcement return (close before the filing day to the first close after, minus SPY). Entry 1 close(s) after that, so no lookahead. Quintile breakpoints come from the previous 91 days of announcements. Cells: mean excess return over SPY (winsorised 1-99%) and t-statistic of monthly averages. Realistic cost uses the liquidity tiers in config.py (0.4% round trip for these names); stress cost is the project's 2.5% rule.

## In sample (2017 to 2021): 18283 events

| quintile | n | 20d excess | 40d excess | 60d excess |
|---|---|---|---|---|
| Q1 (worst reaction) | 3757 | -0.48% (t -0.2) | -1.04% (t -0.2) | -0.83% (t 0.5) |
| Q2 | 3574 | -0.02% (t -0.3) | -0.34% (t 0.4) | -0.32% (t -0.2) |
| Q3 | 3626 | -0.09% (t -0.8) | -0.62% (t -1.3) | -0.86% (t -1.5) |
| Q4 | 3591 | -0.13% (t -0.6) | -0.57% (t -1.2) | -0.88% (t -0.9) |
| Q5 (best reaction) | 3735 | -0.09% (t -0.2) | -0.49% (t -0.2) | -0.63% (t -0.0) |

| rule | 20d | 40d | 60d |
|---|---|---|---|
| Q5 long, net of realistic cost | -0.49% (t -1.1) | -0.89% (t -0.8) | -1.03% (t -0.4) |
| Q5 long, net of 2.5% | -2.59% | -2.99% | -3.13% |
| Q5 minus Q1, before costs (monthly) | +0.05% (t 0.1) | +0.03% (t 0.0) | -0.70% (t -0.9) |

## Out of sample (2022 onward): 26617 events

| quintile | n | 20d excess | 40d excess | 60d excess |
|---|---|---|---|---|
| Q1 (worst reaction) | 5362 | -0.74% (t -2.1) | -1.50% (t -2.3) | -1.60% (t -2.5) |
| Q2 | 5266 | -0.49% (t -1.3) | -1.20% (t -2.1) | -1.48% (t -2.8) |
| Q3 | 5243 | -0.55% (t -1.8) | -1.79% (t -3.0) | -1.85% (t -4.2) |
| Q4 | 5316 | -0.19% (t -0.8) | -1.23% (t -2.1) | -1.56% (t -3.3) |
| Q5 (best reaction) | 5430 | -0.41% (t -0.8) | -0.97% (t -2.3) | -1.71% (t -2.9) |

| rule | 20d | 40d | 60d |
|---|---|---|---|
| Q5 long, net of realistic cost | -0.81% (t -2.1) | -1.37% (t -3.0) | -2.11% (t -3.6) |
| Q5 long, net of 2.5% | -2.91% | -3.47% | -4.21% |
| Q5 minus Q1, before costs (monthly) | +0.55% (t 1.6) | +0.19% (t 0.4) | -0.10% (t -0.1) |

## Verdict

Pre-set rule: buy the top quintile, hold 60 days, judged out of sample. No edge: the top quintile did not beat SPY out of sample.

Caveats: survivorship (delisted and acquired companies are missing, which flatters long returns); Item 2.02 also covers some pre-announcements and restatements; the long-short line ignores borrow costs and needs two round trips; trades overlap in time, which the monthly t-statistic only partly allows for. Not financial advice.
