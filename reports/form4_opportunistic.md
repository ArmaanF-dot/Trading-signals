# Opportunistic insiders and cross-sectional ranking

Events: 11511; with prices: 8806. Entry at the first close after the filing date. Cost per trade depends on average dollar volume (assumed, not measured): >= $20m: 0.4%, >= $5m: 1.0%, below: 2.5% round trip. Cells are 1%-winsorised mean net return (median) / share of trades positive after cost / winsorised mean net excess over IWM. Events whose price history does not start within a week of the filing are dropped as unpriced. Survivorship bias flatters everything (delisted names have no prices).

### Opportunistic vs routine (all priced)

| group | n | 20d net / hit / excess | 40d net / hit / excess | 60d net / hit / excess |
|---|---|---|---|---|
| opportunistic | 8665 | 0.1% (med -1.2%) / 45% / -1.3% | 1.2% (med -0.5%) / 48% / -1.6% | 2.7% (med 0.3%) / 51% / -1.4% |
| routine | 141 | -1.4% (med -1.9%) / 41% / -2.5% | -1.0% (med -1.4%) / 45% / -3.1% | 1.7% (med 1.2%) / 53% / -2.0% |

### Opportunistic vs routine (liquid: ADV >= $5m)

| group | n | 20d net / hit / excess | 40d net / hit / excess | 60d net / hit / excess |
|---|---|---|---|---|
| opportunistic | 3725 | 0.9% (med 0.3%) / 51% / -0.5% | 2.0% (med 1.1%) / 53% / -0.8% | 3.3% (med 2.0%) / 54% / -1.1% |
| routine | 71 | -0.2% (med -1.3%) / 48% / -1.1% | 0.7% (med -0.1%) / 49% / -1.1% | 3.9% (med 0.2%) / 51% / 0.8% |

### opportunistic buys, ranked quintiles (all priced)

| group | n | 20d net / hit / excess | 40d net / hit / excess | 60d net / hit / excess |
|---|---|---|---|---|
| Q1 | 1721 | -0.2% (med -0.8%) / 44% / -1.5% | 0.8% (med 0.3%) / 51% / -1.9% | 2.7% (med 1.7%) / 57% / -1.4% |
| Q2 | 1732 | 0.0% (med -1.1%) / 45% / -1.5% | 1.1% (med -0.1%) / 49% / -1.7% | 3.4% (med 0.7%) / 52% / -0.8% |
| Q3 | 1735 | 0.6% (med -1.3%) / 45% / -1.0% | 1.2% (med -0.8%) / 47% / -1.7% | 2.5% (med 0.2%) / 51% / -1.6% |
| Q4 | 1732 | -0.2% (med -1.5%) / 44% / -1.8% | 1.3% (med -0.9%) / 48% / -1.5% | 3.4% (med -1.0%) / 48% / -0.7% |
| Q5 | 1745 | 0.7% (med -1.6%) / 45% / -0.8% | 1.7% (med -1.4%) / 47% / -1.2% | 2.5% (med -2.2%) / 46% / -1.7% |

Q5 minus Q1 mean net return, opportunistic (all priced): 20d: 0.9%, 40d: 1.0%, 60d: -0.2%

### opportunistic buys, ranked quintiles (liquid)

| group | n | 20d net / hit / excess | 40d net / hit / excess | 60d net / hit / excess |
|---|---|---|---|---|
| Q1 | 731 | 0.4% (med 0.4%) / 52% / -0.8% | 1.5% (med 1.0%) / 55% / -1.0% | 3.1% (med 3.0%) / 59% / -0.9% |
| Q2 | 746 | 1.9% (med 0.9%) / 54% / 0.5% | 3.0% (med 2.5%) / 58% / 0.2% | 3.6% (med 3.5%) / 57% / -0.8% |
| Q3 | 742 | 1.3% (med 0.7%) / 53% / -0.3% | 1.4% (med 0.5%) / 51% / -1.6% | 3.0% (med 1.3%) / 54% / -1.4% |
| Q4 | 746 | 0.5% (med -0.6%) / 48% / -1.0% | 1.9% (med 0.8%) / 52% / -0.9% | 3.5% (med 0.3%) / 50% / -0.9% |
| Q5 | 760 | 0.4% (med -0.1%) / 50% / -1.1% | 2.0% (med 0.5%) / 51% / -1.0% | 2.9% (med 0.9%) / 52% / -1.6% |

Q5 minus Q1 mean net return, opportunistic (liquid): 20d: 0.1%, 40d: 0.5%, 60d: -0.2%

Caveats: events overlap in time and across names (not independent); fixed equal-weight score with four features, nothing fitted, but several tables were examined so a single good-looking cell can be luck; costs are assumptions; daily closes only. Not financial advice.

<!-- risk-sizing:start -->
## Risk and sizing

Period 2023-01 to 2026-01 (37 months), realistic costs. Net book: Sharpe -0.10, volatility 14.3%, max drawdown -30%. Edge (net excess over the benchmark): Sharpe -3.54, volatility 5.3%, max drawdown -44%.

**Suggested leverage:** None: out-of-sample edge Sharpe -3.54 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns.

Leverage is suggested only when the out-of-sample edge Sharpe, net of costs, is at least 1.0 over 36+ months; it then targets 10% volatility, capped by half-Kelly and 2x. Not financial advice.

All studies side by side: `reports/risk_summary.md`.
<!-- risk-sizing:end -->
