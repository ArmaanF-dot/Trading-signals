# 10-K and 10-Q text changes (Lazy Prices style)

Companies: 700 (most liquid on NYSE/Nasdaq, today's SEC list). Filings compared with the same company's filing a year earlier: 23601; with a price outcome: 22854. Wording is scored by similarity and short word lists, not by a language model (see the module note).

## In sample (2017-21): 10943 filings

Rank correlation (IC) within each quarter, averaged; t across quarters. Positive = higher feature goes with a better outcome.

| feature | Next earnings-day reaction | Drift 20d | Drift 60d |
|---|---|---|---|
| Similarity to last year's filing | +0.004 (t 0.4) | -0.021 (t -1.8) | +0.001 (t 0.1) |
| Tone change (positive minus negative) | -0.012 (t -1.1) | -0.032 (t -1.9) | -0.019 (t -1.3) |
| Uncertainty-word change | -0.005 (t -0.6) | -0.009 (t -1.0) | -0.002 (t -0.2) |
| Length change | -0.011 (t -1.1) | +0.042 (t 4.2) | +0.016 (t 1.3) |
| Combined text score (pre-set) | -0.000 (t -0.0) | -0.020 (t -1.4) | -0.007 (t -0.6) |

Liquid filings by combined text score quintile (Q5 = least change and best tone), excess over SPY, net of 2.5% (monthly-average t):

| quintile | n | 20d | 60d |
|---|---|---|---|
| Q1 | 2116 | -1.94% (t -5.5) | -1.69% (t -1.5) |
| Q2 | 2124 | -2.08% (t -4.8) | -1.77% (t -2.7) |
| Q3 | 2122 | -2.47% (t -8.3) | -2.12% (t -3.5) |
| Q4 | 2124 | -2.34% (t -6.1) | -1.90% (t -3.0) |
| Q5 | 2131 | -2.64% (t -8.5) | -1.99% (t -3.8) |

Q5 minus Q1 before costs: 20d -0.81%, 60d -0.16%.

## Out of sample (2022 onward): 12658 filings

Rank correlation (IC) within each quarter, averaged; t across quarters. Positive = higher feature goes with a better outcome.

| feature | Next earnings-day reaction | Drift 20d | Drift 60d |
|---|---|---|---|
| Similarity to last year's filing | +0.008 (t 0.9) | +0.013 (t 0.9) | +0.020 (t 1.1) |
| Tone change (positive minus negative) | -0.014 (t -1.3) | +0.002 (t 0.2) | -0.006 (t -0.4) |
| Uncertainty-word change | +0.014 (t 1.5) | +0.005 (t 0.5) | +0.007 (t 1.0) |
| Length change | -0.019 (t -2.6) | +0.012 (t 1.0) | +0.004 (t 0.4) |
| Combined text score (pre-set) | -0.011 (t -1.3) | +0.006 (t 0.5) | +0.001 (t 0.1) |

Liquid filings by combined text score quintile (Q5 = least change and best tone), excess over SPY, net of 2.5% (monthly-average t):

| quintile | n | 20d | 60d |
|---|---|---|---|
| Q1 | 2481 | -2.95% (t -8.4) | -3.74% (t -4.4) |
| Q2 | 2489 | -2.57% (t -6.8) | -2.94% (t -4.6) |
| Q3 | 2487 | -2.56% (t -7.4) | -3.18% (t -6.4) |
| Q4 | 2489 | -2.68% (t -7.6) | -3.21% (t -3.4) |
| Q5 | 2498 | -2.77% (t -9.6) | -3.75% (t -4.0) |

Q5 minus Q1 before costs: 20d +0.06%, 60d -0.14%.

## Verdict

No edge: out of sample, filings with more rewriting and a worse tone did not lag, and the least-changed ones did not beat SPY after costs.

Caveats: survivorship (today's ticker list); word lists are a crude stand-in for a language model; 10-Qs often come out the same day as the earnings 8-K, so part of any move is the earnings news itself, which the entry lag only partly removes; overlapping returns make the t-statistics too generous. Not financial advice.
