# Form 4 cluster backtest

Rule: >= 2 distinct buyers, officer/director required, 10-day window, >= $100,000. Entry at first close after the last filing date. Round-trip cost assumed 2.5%.

Clusters found: 3156. With usable prices: 2595 (82%); the rest (often delisted names) are excluded, so **results are flattered by survivorship bias**.

## All priced clusters

| horizon | n | mean net | median net | hit rate (net>0) | mean excess vs IWM (net) |
|---|---|---|---|---|---|
| 5d | 2541 | -1.80% | -2.50% | 30% | -2.20% |
| 20d | 2541 | -0.66% | -2.24% | 41% | -2.17% |
| 60d | 2541 | 2.36% | -0.53% | 48% | -2.17% |

## Last buy price under $20 (small-cap proxy)

| horizon | n | mean net | median net | hit rate (net>0) | mean excess vs IWM (net) |
|---|---|---|---|---|---|
| 5d | 1694 | -1.62% | -2.50% | 32% | -2.04% |
| 20d | 1694 | -0.46% | -2.55% | 40% | -1.95% |
| 60d | 1694 | 3.07% | -0.74% | 47% | -1.51% |

## Year 2023

| horizon | n | mean net | median net | hit rate (net>0) | mean excess vs IWM (net) |
|---|---|---|---|---|---|
| 5d | 866 | -1.97% | -2.50% | 32% | -2.38% |
| 20d | 866 | -0.51% | -1.52% | 45% | -2.63% |
| 60d | 866 | 2.65% | -0.06% | 50% | -2.45% |

## Year 2024

| horizon | n | mean net | median net | hit rate (net>0) | mean excess vs IWM (net) |
|---|---|---|---|---|---|
| 5d | 731 | -1.60% | -2.32% | 30% | -1.97% |
| 20d | 731 | -0.56% | -2.53% | 36% | -1.16% |
| 60d | 731 | 1.93% | -0.74% | 48% | 0.05% |

## Year 2025

| horizon | n | mean net | median net | hit rate (net>0) | mean excess vs IWM (net) |
|---|---|---|---|---|---|
| 5d | 944 | -1.79% | -2.50% | 29% | -2.21% |
| 20d | 944 | -0.88% | -2.33% | 40% | -2.54% |
| 60d | 944 | 2.42% | -0.79% | 47% | -3.64% |

Caveats: no point-in-time market-cap filter; clusters overlap in time (not independent); returns use daily closes (no intraday slippage); small samples are noisy. Not financial advice.
