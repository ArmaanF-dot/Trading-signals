# FCA aggregate short changes: event study

Events (aggregate net short moved by >= 0.5pp): 12041; with prices: 6724. Public 2 business days after the position date; entry at the next close. Cells: long-only net return (winsorised mean, median) / net excess vs the UK index ETF / cost-free excess (information content; for a rise, a negative value means shorts were right). Costs are assumed: >= GBP 10m a day: 0.9%, >= GBP 2m a day: 1.7%, below: 3.5% round trip including stamp duty. Survivorship: delisted names have no prices.

### all priced

| event | n | 20d | 40d | 60d |
|---|---|---|---|---|
| fall | 3513 | -0.2% (med -0.5%) / -1.6% / 0.3% | 0.9% (med -0.4%) / -1.7% / 0.2% | 1.5% (med 0.0%) / -1.7% / 0.2% |
| rise | 3211 | -0.9% (med -1.2%) / -1.9% / -0.1% | -0.5% (med -1.4%) / -2.2% / -0.5% | -0.4% (med -1.3%) / -3.0% / -1.2% |
| rise to >= 3% aggregate | 1349 | -0.7% (med -1.4%) / -1.8% / -0.3% | -0.3% (med -1.1%) / -2.0% / -0.5% | -0.3% (med -1.3%) / -3.0% / -1.5% |

### liquid (>= GBP 2m a day)

| event | n | 20d | 40d | 60d |
|---|---|---|---|---|
| fall | 2545 | 0.4% (med 0.2%) / -1.0% / 0.3% | 1.5% (med 0.5%) / -1.1% / 0.2% | 1.9% (med 0.7%) / -1.4% / -0.1% |
| rise | 2499 | -0.5% (med -0.8%) / -1.5% / -0.2% | -0.1% (med -0.8%) / -1.8% / -0.5% | -0.0% (med -0.6%) / -2.7% / -1.3% |
| rise to >= 3% aggregate | 1201 | -0.3% (med -1.2%) / -1.3% / -0.1% | 0.1% (med -0.8%) / -1.6% / -0.3% | 0.2% (med -0.7%) / -2.5% / -1.3% |

Caveats: events cluster in time (market-wide moves); aggregate rebuilt from holder disclosures so closures that were never recorded would inflate it; ISIN-to-ticker mapping can miss delisted names; several cuts examined, so a lone good-looking cell may be luck. Not financial advice.
