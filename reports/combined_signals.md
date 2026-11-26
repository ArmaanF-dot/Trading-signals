# Combining job postings and filing-text signals

Job-postings earnings reports: 687. With a text score from a filing in the previous 120 days as well: 187 (liquid: 186). Rank correlation (IC) within each quarter, averaged, t across quarters. Rule fixed in advance (see module note); no weights were fitted.

## In sample (2017-21): 21 reports

| signal | EAR | Drift 20d | Drift 60d | Drift 120d |
|---|---|---|---|---|
| Job postings only | n/a | n/a | n/a | n/a |
| Text only | n/a | n/a | n/a | n/a |
| Combined | n/a | n/a | n/a | n/a |

Liquid reports, top third minus bottom third by signal, excess over SPY (stress cost 2.5% once per trade):

| signal | 60d | 120d |
|---|---|---|
| Job postings only | n/a | n/a |
| Text only | n/a | n/a |
| Combined | n/a | n/a |

## Out of sample (2022 onward): 166 reports

| signal | EAR | Drift 20d | Drift 60d | Drift 120d |
|---|---|---|---|---|
| Job postings only | +0.110 (t 1.5) | +0.018 (t 0.2) | -0.102 (t -1.0) | +0.057 (t 0.6) |
| Text only | -0.063 (t -0.8) | +0.077 (t 0.7) | +0.036 (t 0.3) | +0.083 (t 1.0) |
| Combined | -0.035 (t -0.3) | +0.076 (t 1.0) | +0.034 (t 0.3) | +0.167 (t 1.7) |

Liquid reports, top third minus bottom third by signal, excess over SPY (stress cost 2.5% once per trade):

| signal | 60d | 120d |
|---|---|---|
| Job postings only | -9.92% gross; top net -4.91% (n 58) | -5.41% gross; top net -5.39% (n 54) |
| Text only | -7.84% gross; top net -1.18% (n 58) | -6.18% gross; top net -3.36% (n 54) |
| Combined | -3.04% gross; top net +1.68% (n 58) | +2.67% gross; top net +4.92% (n 54) |

## Product pages (forward only)

Product-page collector: 15 sites, 1 daily snapshots so far (2026-11-26 to 2026-11-26). Features need about 90 days of history before an earnings date, so earnings reports testable today: 0.

## Verdict

No edge: the combined score is no better out of sample than either signal alone, and nothing clears t >= 2 on the main outcomes after allowing for the number of tests.

Caveats: the overlap is small and tech-heavy (only companies with a public job board); many ICs are shown, so a few will pass |t| >= 2 by chance; the text score is word lists, not a language model. Not financial advice.
