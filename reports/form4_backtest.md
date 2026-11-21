# Form 4 cluster backtest

Rule: >= 2 distinct buyers, officer/director required, 10-day window, >= $100,000. Entry at first close after the last filing date. Round-trip cost assumed 2.5%.

Clusters found: 3156. With usable prices: 2595 (82%); the rest (often delisted names) are excluded, so **results are flattered by survivorship bias**.

## All priced clusters

| horizon | n | mean net | median net | hit rate (net>0) | mean excess vs IWM (net) |
|---|---|---|---|---|---|
| 5d | 2569 | -0.96% | -2.50% | 30% | -1.36% |
| 20d | 2563 | 0.12% | -2.23% | 41% | -1.38% |
| 60d | 2562 | 2.18% | -0.61% | 48% | -2.33% |

## Last buy price under $20 (small-cap proxy)

| horizon | n | mean net | median net | hit rate (net>0) | mean excess vs IWM (net) |
|---|---|---|---|---|---|
| 5d | 1713 | -0.39% | -2.50% | 32% | -0.79% |
| 20d | 1712 | 0.66% | -2.52% | 40% | -0.82% |
| 60d | 1711 | 2.82% | -0.81% | 47% | -1.73% |

## Year 2023

| horizon | n | mean net | median net | hit rate (net>0) | mean excess vs IWM (net) |
|---|---|---|---|---|---|
| 5d | 878 | -2.07% | -2.51% | 32% | -2.47% |
| 20d | 874 | -0.55% | -1.52% | 45% | -2.66% |
| 60d | 874 | 2.39% | -0.20% | 49% | -2.68% |

## Year 2024

| horizon | n | mean net | median net | hit rate (net>0) | mean excess vs IWM (net) |
|---|---|---|---|---|---|
| 5d | 740 | 1.48% | -2.33% | 30% | 1.11% |
| 20d | 739 | 2.30% | -2.50% | 37% | 1.69% |
| 60d | 738 | 1.78% | -0.81% | 47% | -0.11% |

## Year 2025

| horizon | n | mean net | median net | hit rate (net>0) | mean excess vs IWM (net) |
|---|---|---|---|---|---|
| 5d | 951 | -1.84% | -2.50% | 29% | -2.26% |
| 20d | 950 | -0.97% | -2.33% | 40% | -2.60% |
| 60d | 950 | 2.30% | -0.81% | 47% | -3.74% |

Caveats: no point-in-time market-cap filter; clusters overlap in time (not independent); returns use daily closes (no intraday slippage); small samples are noisy. Not financial advice.
