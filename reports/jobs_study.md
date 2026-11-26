# Job postings and earnings (US, liquid stocks)

Companies with a public Greenhouse, Lever or Ashby board today: 62. With at least 12 archived months since 2017: 31. Median archived months per company: 12.

Earnings dates (8-K Item 2.02): 1474; with a fresh postings change before the report: 298; ranked into terciles: 218.

Signal: change in log(1 + open postings) from a snapshot at least 80 days old to the latest snapshot within 45 days before the report. Terciles use breakpoints from the previous 365 days of events. EAR is the stock's move over the report (close before the filing day to first close after) minus SPY. Cells: mean (winsorised 1-99%) and t-statistic of monthly averages.

## By tercile

| tercile | n | median change | EAR | 20d drift | 40d drift | 60d drift |
|---|---|---|---|---|---|---|
| T1 (cutting) | 66 | -35% | +2.09% (t 1.3) | -0.98% (t 0.4) | +0.92% (t 0.8) | +6.03% (t 1.4) |
| T2 | 48 | +0% | +1.93% (t 1.3) | -2.27% (t 0.0) | +1.18% (t 1.0) | +5.03% (t 0.9) |
| T3 (adding) | 104 | +7% | -0.40% (t 0.5) | -1.70% (t -0.8) | -0.98% (t -0.7) | -4.24% (t -0.5) |

Rank correlation of signal with EAR, quarter by quarter: mean -0.039 over 23 quarters (t -0.6).

## Trading it

| rule | mean per event | t |
|---|---|---|
| Long T3 over the report, net of realistic cost | -0.80% | 0.3 |
| Long T3 over the report, net of 2.5% | -2.90% | |
| T3 minus T1 over the report, before costs (monthly) | -0.20% | -0.0 |

## Verdict

Pre-set rule: buy the top tercile at the close before the report, sell after it. No edge: postings growth did not predict the reaction to earnings.

Caveats: the universe is today's boards (survivors, mostly tech and fintech, many listed only since 2020); archive captures are irregular, so 'recent' can be up to 45 days stale; an HTML capture can miss roles on paginated boards; companies move between ATSs, which shows up as missing months. Not financial advice.
