# Cross-asset trend following (ETFs, volatility targeted)

**Verdict:** NO EDGE: out of sample the trend book earns +5.4% a year (Sharpe 0.51) at 0.1% costs, -0.0% a year versus the always-long book at the same risk (t -0.00); -18.2% a year at the house 2.5% round trip.

Rule: each month-end, per asset, a trend signal from past prices only (12-month return sign, 10-month moving average, or a 1/3/12-month blend); positions sized by inverse trailing volatility and the whole book scaled to 10% ex-ante volatility (leverage cap 3x), held one month. 22 liquid ETFs across equities, bonds, commodities and currencies. Costs: turnover x half the round trip. The comparison that matters is the always-long book with identical sizing: it says whether the trend filter adds anything beyond owning the assets.

Chosen in sample (best net Sharpe at 0.10%, formations before 2017-01): **sma10 signal, long/short**.

## All variants (net Sharpe at each cost; excess = trend minus always-long, annualised)

| variant | sample | Sharpe, realistic cost | Sharpe, house cost | excess vs always-long (t) | monthly turnover |
|---|---|---|---|---|---|
| 12m, ls | in sample | 0.44 | -0.72 | +4.3% (0.81) | 94% |
| 12m, ls | out of sample | 0.46 | -1.21 | -0.4% (-0.07) | 127% |
| 12m, lo | in sample | 0.48 | -0.36 | +4.8% (1.72) | 69% |
| 12m, lo | out of sample | 0.46 | -0.46 | -0.1% (-0.02) | 75% |
| sma10, ls | in sample | 0.54 | -0.94 | +5.4% (0.94) | 118% |
| sma10, ls | out of sample | 0.51 | -1.55 | -0.0% (-0.00) | 164% |
| sma10, lo | in sample | 0.50 | -0.61 | +4.7% (1.57) | 87% |
| sma10, lo | out of sample | 0.59 | -0.74 | +0.5% (0.22) | 96% |
| blend, ls | in sample | 0.54 | -1.94 | +5.2% (0.91) | 195% |
| blend, ls | out of sample | 0.24 | -2.53 | -2.7% (-0.47) | 235% |
| blend, lo | in sample | 0.51 | -1.36 | +4.9% (1.37) | 147% |
| blend, lo | out of sample | 0.63 | -1.57 | +0.9% (0.30) | 156% |

## In sample: 2008-02 to 2017-01 (108 months)

| series | ann. return | vol | Sharpe (+/- s.e.) | max drawdown | t-stat |
|---|---|---|---|---|---|
| trend, gross | 6.5% | 11.7% | 0.60 (+/- 0.36) | -18% | 1.80 |
| trend, net at 0.10% round trip | 5.8% | 11.6% | 0.54 (+/- 0.36) | -19% | 1.63 |
| trend, net at 0.25% round trip | 4.7% | 11.6% | 0.45 (+/- 0.35) | -20% | 1.36 |
| trend, net at 2.50% round trip | -10.8% | 11.4% | -0.94 (+/- 0.40) | -67% | -2.82 |
| always-long, net at 0.10% | 0.1% | 12.4% | 0.07 (+/- 0.33) | -29% | 0.21 |
| 60/40 SPY/IEF | 7.0% | 9.0% | 0.80 (+/- 0.38) | -28% | 2.39 |

Break-even round-trip cost (where the net return reaches zero): 0.99%.
Average gross leverage 2.38x, average net long share +23%.

## Out of sample: 2017-02 to 2026-11 (118 months)

| series | ann. return | vol | Sharpe (+/- s.e.) | max drawdown | t-stat |
|---|---|---|---|---|---|
| trend, gross | 6.0% | 10.4% | 0.61 (+/- 0.35) | -21% | 1.91 |
| trend, net at 0.10% round trip | 4.9% | 10.5% | 0.51 (+/- 0.34) | -22% | 1.61 |
| trend, net at 0.25% round trip | 3.4% | 10.5% | 0.37 (+/- 0.33) | -23% | 1.16 |
| trend, net at 2.50% round trip | -17.4% | 11.7% | -1.55 (+/- 0.47) | -85% | -4.87 |
| always-long, net at 0.10% | 4.7% | 12.6% | 0.43 (+/- 0.33) | -26% | 1.34 |
| 60/40 SPY/IEF | 9.0% | 10.1% | 0.91 (+/- 0.38) | -21% | 2.84 |

Break-even round-trip cost (where the net return reaches zero): 0.65%.
Average gross leverage 3.07x, average net long share +25%.

## Out-of-sample years (chosen variant)

| year | trend (net) | always-long | 60/40 |
|---|---|---|---|
| 2017 | +12.4% | +17.8% | +12.4% |
| 2018 | -0.4% | -11.7% | -2.0% |
| 2019 | +9.4% | +29.9% | +21.8% |
| 2020 | +11.7% | -10.9% | +16.0% |
| 2021 | +5.5% | +7.1% | +15.1% |
| 2022 | +13.9% | -18.0% | -16.7% |
| 2023 | -14.7% | +9.5% | +16.8% |
| 2024 | +7.6% | +8.4% | +14.1% |
| 2025 | +5.9% | +19.8% | +13.9% |
| 2026 | +0.6% | +4.0% | +3.4% |

## Data, biases and caveats

- ETFs priced: SPY (1998-01-02), IWM (2000-05-26), EFA (2001-08-27), EEM (2003-04-14), EWJ (1998-01-02), VNQ (2004-09-29), TLT (2002-07-30), IEF (2002-07-30), LQD (2002-07-30), HYG (2007-04-11), TIP (2003-12-05), GLD (2004-11-18), SLV (2006-04-28), USO (2006-04-10), DBC (2006-02-06), DBA (2007-01-05), UUP (2007-03-01), FXE (2005-12-12), FXY (2007-02-13), FXB (2006-06-26), FXA (2006-06-26), FXC (2006-06-26).
- Sample is short for a trend study: about 226 months from 2008-02. Classic results cover 1985 onwards with futures; the 2010s were a hard decade for trend (bond and equity whipsaws), so a low Sharpe here is partly the decade. Sharpe standard errors above show how little 118 months can say.
- Variant selection used in-sample months only, but with 6 variants and heavily overlapping signals the in-sample winner is mildly optimistic; all variants are shown, including out of sample, for transparency.
- ETFs only: no futures, so no direct short exposure beyond shorting the ETF (borrow and CFD financing not modelled; cash earns 0, so long-only and leveraged results ignore interest and leverage financing).
- Commodity ETFs (USO, DBC, DBA) lose to contango; that is in the prices, and it is why a long-only commodity sleeve looks poor.
- Survivorship: all chosen ETFs still exist; liquid dead ETFs are rare in this set, so the bias is small but not zero.
- Realistic ETF costs are well under 0.1% round trip; the house 2.5% figure is deliberately punitive for monthly rebalancing of a book with average turnover 142% of equity a month.

Monthly series: `reports/trend_following_monthly.csv`.

<!-- risk-sizing:start -->
## Risk and sizing

Period 2017-02 to 2026-11 (118 months), realistic costs. Net book: Sharpe 0.51, volatility 10.5%, max drawdown -22%. Edge (net excess over the benchmark): Sharpe -0.00, volatility 16.5%, max drawdown -46%.

**Suggested leverage:** None: out-of-sample edge Sharpe -0.00 net of costs is below 1.0. No edge to size up; leverage would only magnify costs and drawdowns.

Leverage is suggested only when the out-of-sample edge Sharpe, net of costs, is at least 1.0 over 36+ months; it then targets 10% volatility, capped by half-Kelly and 2x. Not financial advice.

All studies side by side: `reports/risk_summary.md`.
<!-- risk-sizing:end -->
