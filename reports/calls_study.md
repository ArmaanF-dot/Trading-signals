# Earnings-call language and delivery as a signal (US large caps)

Source: free Hugging Face transcript set of S&P 500 calls, text only. Companies: 630; calls 2017 onward with a score and a price history: 15815; liquid (20-day ADV >= $20m, price >= $5) and scored: 14542.

Features are changes against the company's own previous four calls. The pre-set score averages quarterly ranks of: Q&A tone (+), Q&A uncertainty (-), Q&A hedging (-), Q&A disfluency (-), Q&A-minus-prepared tone gap (+), analyst question tone (+). Outcomes are excess returns over SPY from entry two closes after the first close following the call date. IC = quarterly Spearman rank correlation of the feature with the outcome, t-statistic across quarters; the second column removes what the call-day reaction (EAR) explains.

## In sample (2017-21): 8008 calls

| quintile of score | n | 5d excess | 20d excess | 60d excess |
|---|---|---|---|---|
| Q1 (most hedged, flat) | 1594 | -0.00% (t -0.5) | +0.17% (t -0.3) | -0.13% (t -1.0) |
| Q2 | 1601 | -0.07% (t -1.6) | +0.03% (t -1.0) | -0.14% (t 0.6) |
| Q3 | 1602 | +0.03% (t 0.5) | +0.13% (t -0.5) | -0.27% (t 0.3) |
| Q4 | 1601 | +0.09% (t -0.0) | +0.43% (t 0.3) | +0.06% (t 0.4) |
| Q5 (calmest, most upbeat) | 1610 | +0.05% (t -0.1) | +0.41% (t 0.7) | -0.49% (t -0.8) |

| rule | 5d | 20d | 60d |
|---|---|---|---|
| Q5 long, net of realistic cost | -0.35% (t -2.4) | +0.01% (t -0.3) | -0.89% (t -1.7) |
| Q5 long, net of 2.5% | -2.45% | -2.09% | -2.99% |
| Q5 minus Q1, before costs (monthly) | +0.09% (t 0.4) | +0.44% (t 0.9) | +0.29% (t 0.5) |

## Out of sample (2022 onward): 6534 calls

| quintile of score | n | 5d excess | 20d excess | 60d excess |
|---|---|---|---|---|
| Q1 (most hedged, flat) | 1301 | +0.07% (t 0.9) | +0.19% (t 0.3) | -0.82% (t -0.3) |
| Q2 | 1306 | -0.04% (t -0.4) | +0.06% (t -0.2) | -0.92% (t -1.2) |
| Q3 | 1309 | -0.03% (t -0.4) | -0.28% (t -0.2) | -0.55% (t -1.6) |
| Q4 | 1306 | -0.11% (t -1.0) | -0.22% (t -1.2) | -1.09% (t -2.0) |
| Q5 (calmest, most upbeat) | 1312 | +0.11% (t 1.5) | -0.27% (t -0.0) | -1.06% (t -0.3) |

| rule | 5d | 20d | 60d |
|---|---|---|---|
| Q5 long, net of realistic cost | -0.29% (t -0.5) | -0.67% (t -1.1) | -1.46% (t -0.8) |
| Q5 long, net of 2.5% | -2.39% | -2.77% | -3.56% |
| Q5 minus Q1, before costs (monthly) | +0.15% (t 0.6) | -0.16% (t -0.4) | +0.01% (t 0.0) |

## Each feature on its own (exploratory; six features and three horizons, so expect one or two |t| above 2 by luck)

**In sample**, IC with 20d / 60d excess return, raw | after removing EAR

| feature | 20d raw | 20d after EAR | 60d raw | 60d after EAR |
|---|---|---|---|---|
| d_ans_tone | +0.024 (t 2.1) | +0.023 (t 2.1) | +0.014 (t 1.3) | +0.015 (t 1.4) |
| d_ans_unc | -0.014 (t -1.5) | -0.013 (t -1.4) | -0.005 (t -0.5) | -0.005 (t -0.5) |
| d_ans_hedge | +0.003 (t 0.2) | +0.003 (t 0.2) | +0.006 (t 0.5) | +0.006 (t 0.5) |
| d_ans_disfl | +0.005 (t 0.3) | +0.004 (t 0.3) | +0.023 (t 1.7) | +0.022 (t 1.6) |
| d_gap_tone | +0.014 (t 0.8) | +0.014 (t 0.8) | -0.008 (t -0.5) | -0.009 (t -0.6) |
| d_q_tone | +0.021 (t 2.1) | +0.021 (t 2.3) | +0.009 (t 1.1) | +0.010 (t 1.2) |
| call_score | +0.023 (t 2.2) | +0.022 (t 2.2) | -0.004 (t -0.5) | -0.003 (t -0.3) |

**Out of sample**, IC with 20d / 60d excess return, raw | after removing EAR

| feature | 20d raw | 20d after EAR | 60d raw | 60d after EAR |
|---|---|---|---|---|
| d_ans_tone | -0.016 (t -1.0) | -0.018 (t -1.2) | -0.007 (t -0.4) | -0.009 (t -0.5) |
| d_ans_unc | +0.004 (t 0.2) | +0.003 (t 0.2) | +0.000 (t 0.0) | +0.000 (t 0.0) |
| d_ans_hedge | +0.010 (t 0.8) | +0.010 (t 0.9) | -0.004 (t -0.3) | -0.004 (t -0.3) |
| d_ans_disfl | +0.020 (t 1.6) | +0.023 (t 1.8) | +0.002 (t 0.2) | +0.003 (t 0.4) |
| d_gap_tone | -0.014 (t -0.9) | -0.012 (t -0.8) | -0.017 (t -1.0) | -0.015 (t -0.9) |
| d_q_tone | -0.004 (t -0.2) | -0.007 (t -0.5) | +0.013 (t 0.7) | +0.009 (t 0.5) |
| call_score | -0.022 (t -1.3) | -0.025 (t -1.4) | -0.007 (t -0.4) | -0.009 (t -0.6) |

## What about pauses, pitch and tone of voice?

Not testable for free at scale. What exists: the Hugging Face "EarningsCallVoice" set has only 100 short clips with no company or date, so it cannot be linked to returns; a larger audio set (soundai2016/pimm_nasdaq_earningscall) is gated; the academic MAEC set (about 3,400 calls, 2015-18, with acoustic features) lives on a GitHub repository this project cannot reach; company webcast archives are mostly behind registration and expire. The transcripts carry no timestamps, so pauses cannot be recovered either; the "disfluency" feature above (fillers, "--" and "...") is only a weak proxy, because vendors clean transcripts. If audio is ever worth pursuing, the realistic route is to download MAEC by hand, extract pitch and pause features, and run the same quintile test, but about 3,400 calls over four years is small and the text result suggests little to find.

## Verdict

Pre-set rule: buy the top score quintile, hold 60 days, judged out of sample. No edge: the top quintile did not beat SPY out of sample.

Caveats: text only (no pauses or pitch); survivorship (today's S&P 500 members, so failures and deletions are missing); transcripts are polished by the vendor, so fillers are mostly stripped; call dates carry no reliable timezone so entry is deliberately late (two closes after the first close following the call day); overlapping trades make the t-statistics optimistic. Not financial advice.
