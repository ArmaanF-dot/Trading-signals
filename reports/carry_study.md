# Crypto carry study: perpetual funding and spot-perp basis

Binance public data, 2020-01-01 to 2026-10-31, 10 large coins (BTC, ETH, BNB, XRP, LTC, ADA, DOGE, LINK, SOL, AVAX; each from its own perp launch). Parameters chosen before 2023; 2023 onward is out of sample. Costs: 0.10% spot and 0.05% perp taker fees, slippage 0.02% per leg per side for BTC and ETH and 0.08% for the rest, 25% extra capital held as margin, idle capital earning nothing. Edge is measured against the US 3-month T-bill (what the money earns for doing nothing).

**Verdict:** A real premium that has shrunk to roughly cash, and not tradable by a UK retail account. Always-on BTC+ETH carry made 5.9% a year net out of sample (2023 onward) against 4.5% for a T-bill, so only 1.4% a year of true excess, on capital exposed to exchange and stablecoin risk. The huge Sharpe (3.15) is an artefact of near-zero volatility, not a sign of safety: the risks (exchange failure, liquidation, depeg) are not in daily returns. Funding was 22-34% a year in 2020-21 and has been 2-5% in 2025-26, below the T-bill in 2026. Timing and rotation rules add nothing: the chosen funding filter made 5.9% a year (same as always-on), top-3 rotation lost 1.1% a year after 7.8% of costs, and the directional contrarian book is flat before luck (Sharpe -0.06). No edge worth taking; the perp leg is banned for UK retail clients anyway.

## Funding by year (BTC and ETH, annualised, average of the two)

| year | funding earned by a short |
|---|---|
| 2020 | 22.3% |
| 2021 | 34.1% |
| 2022 | 2.5% |
| 2023 | 8.1% |
| 2024 | 12.4% |
| 2025 | 5.0% |
| 2026 | 2.6% |

## Always-on cash-and-carry

| strategy | sample | days | net return a year | cost a year | T-bill | edge over T-bill: Sharpe | t | max drawdown | capital deployed |
|---|---|---|---|---|---|---|---|---|---|
| BTC | in sample | 1094 | 14.6% | 0.05% | 0.8% | 8.88 | 15.37 | -1.7% | 100% |
| BTC | out of sample | 1400 | 5.9% | 0.00% | 4.5% | 2.95 | 5.78 | -0.3% | 100% |
| ETH | in sample | 1094 | 18.7% | 0.05% | 0.8% | 8.54 | 14.79 | -1.4% | 100% |
| ETH | out of sample | 1400 | 6.0% | 0.00% | 4.5% | 2.79 | 5.47 | -0.5% | 100% |
| BTC+ETH | in sample | 1094 | 16.6% | 0.05% | 0.8% | 9.21 | 15.94 | -1.2% | 100% |
| BTC+ETH | out of sample | 1400 | 5.9% | 0.00% | 4.5% | 3.15 | 6.16 | -0.4% | 100% |
| All 10 coins | in sample | 1094 | 13.0% | 0.45% | 0.8% | 4.59 | 7.95 | -4.6% | 100% |
| All 10 coins | out of sample | 1400 | 4.7% | 0.00% | 4.5% | 0.31 | 0.61 | -0.4% | 100% |

Calendar years, BTC+ETH always-on:

| year | net return on capital | T-bill | funding collected (gross, on capital) | max drawdown |
|---|---|---|---|---|
| 2020 | 18.7% | 0.4% | 17.3% | -1.18% |
| 2021 | 31.1% | 0.0% | 27.1% | -0.14% |
| 2022 | 1.9% | 2.0% | 1.9% | -0.65% |
| 2023 | 6.6% | 5.2% | 6.4% | -0.05% |
| 2024 | 10.5% | 5.1% | 10.0% | -0.07% |
| 2025 | 4.1% | 4.1% | 4.0% | -0.10% |
| 2026 | 1.7% | 3.1% | 1.7% | -0.41% |

Per coin (always-on, one coin):

| coin | perp from | mean funding a year, all | mean funding a year, out of sample | net return a year, all | net return a year, OOS | OOS edge Sharpe | OOS max drawdown |
|---|---|---|---|---|---|---|---|
| ADA | 2020-02-01 | 13.4% | 6.9% | 11.0% | 5.5% | 1.08 | -0.53% |
| AVAX | 2020-09-24 | 6.8% | 5.0% | 5.3% | 3.9% | -0.62 | -2.28% |
| BNB | 2020-02-11 | -0.0% | -3.0% | -0.3% | -2.4% | -5.94 | -11.03% |
| BTC | 2020-01-02 | 11.6% | 7.2% | 9.7% | 5.9% | 2.95 | -0.33% |
| DOGE | 2020-07-11 | 12.3% | 8.1% | 10.4% | 6.5% | 2.90 | -0.37% |
| ETH | 2020-01-02 | 13.7% | 7.3% | 11.4% | 6.0% | 2.79 | -0.51% |
| LINK | 2020-01-18 | 13.6% | 8.5% | 11.3% | 7.0% | 2.53 | -0.28% |
| LTC | 2020-01-10 | 14.7% | 8.3% | 12.0% | 6.8% | 3.46 | -0.19% |
| SOL | 2020-09-15 | 0.3% | 3.9% | -1.9% | 3.1% | -1.24 | -3.16% |
| XRP | 2020-01-07 | 14.5% | 6.8% | 11.6% | 5.5% | 1.27 | -1.02% |

## Timing and selection rules

Funding filter grid (trailing window days, threshold a year), in-sample edge Sharpe on BTC+ETH: 7d>0%: 8.24; 7d>5%: 7.68; 7d>10%: 7.69; 14d>0%: 9.04; 14d>5%: 8.10; 14d>10%: 7.87; 30d>0%: 9.11; 30d>5%: 8.33; 30d>10%: 7.94. Chosen in sample: **30d > 0%**.

| strategy | sample | days | net return a year | cost a year | T-bill | edge over T-bill: Sharpe | t | max drawdown | capital deployed |
|---|---|---|---|---|---|---|---|---|---|
| Funding filter 30d > 0% (BTC+ETH) | in sample | 1066 | 16.4% | 0.42% | 0.8% | 9.11 | 15.56 | -1.2% | 91% |
| Funding filter 30d > 0% (BTC+ETH) | out of sample | 1400 | 5.9% | 0.12% | 4.5% | 2.91 | 5.70 | -0.4% | 93% |
| Top 3 of 10 by 14d funding, weekly | in sample | 1081 | 15.4% | 6.42% | 0.8% | 5.08 | 8.75 | -1.7% | 98% |
| Top 3 of 10 by 14d funding, weekly | out of sample | 1400 | -1.1% | 7.79% | 4.5% | -4.20 | -8.22 | -7.3% | 100% |
| Funding filter 7d > 0% (BTC+ETH) | in sample | 1089 | 15.3% | 1.73% | 0.8% | 8.24 | 14.23 | -1.4% | 89% |
| Funding filter 7d > 0% (BTC+ETH) | out of sample | 1400 | 5.0% | 0.95% | 4.5% | 0.81 | 1.60 | -1.4% | 92% |
| Funding filter 7d > 5% (BTC+ETH) | in sample | 1089 | 14.3% | 2.24% | 0.8% | 7.68 | 13.27 | -2.6% | 72% |
| Funding filter 7d > 5% (BTC+ETH) | out of sample | 1400 | 2.2% | 2.91% | 4.5% | -3.60 | -7.04 | -3.1% | 61% |

## Sensitivities (BTC+ETH, out of sample)

Margin held per 1.0 of notional (always-on): 0%: 7.5% a year, edge Sharpe 5.33; 10%: 6.8% a year, edge Sharpe 4.46; 25%: 5.9% a year, edge Sharpe 3.15; 50%: 4.9% a year, edge Sharpe 0.95.

Fee tier (chosen filter): Standard taker fees: 5.86% a year; With BNB discount (spot 0.075%): 5.87% a year; Maker both legs (0.1% / 0.02%): 5.88% a year.

## Liquidation check

Worst intraday high against the previous close for a short perp, with 25% margin per 1.0 notional (a day above the margin would risk liquidation unless topped up from the spot side or cash).

| coin | days | worst intraday spike | days > margin | days > half margin |
|---|---|---|---|---|
| ADA | 2465 | 74.7% | 13 | 104 |
| AVAX | 2229 | 90.1% | 19 | 133 |
| BNB | 2455 | 79.0% | 7 | 41 |
| BTC | 2495 | 36.2% | 2 | 19 |
| DOGE | 2304 | 412.4% | 40 | 130 |
| ETH | 2495 | 202.7% | 3 | 44 |
| LINK | 2479 | 45.3% | 7 | 104 |
| LTC | 2480 | 33.5% | 4 | 57 |
| SOL | 2231 | 62.7% | 21 | 136 |
| XRP | 2483 | 105.0% | 21 | 95 |

## Directional test: does high funding predict falling prices?

Non-overlapping weeks, all coins pooled, Spearman rank correlation of trailing-7d funding with the next 7-day perp return (t-stat treats weeks as independent, and coins within a week are correlated, so it flatters):

| sample | weeks x coins | rank correlation | t |
|---|---|---|---|
| in sample | 1432 | 0.038 | 1.42 |
| out of sample | 1990 | -0.004 | -0.19 |

Contrarian book (short the perp when funding is in its own top quintile, long in the bottom quintile; expanding quantiles, weekly, net of perp fees): in sample Sharpe -0.58, annual -26.0%; out of sample Sharpe -0.06, annual -5.4%, max drawdown -46.6%.

## Practical access (UK retail)

- Binance returned HTTP 451 and Bybit 403 from this container; the study used Binance's static historical dump, which is public.
- The FCA has banned the sale of crypto derivatives (perpetuals, futures, options) to UK retail clients since 6 January 2021. The short perp leg is therefore not legitimately available to a UK retail account on a regulated venue; using an offshore exchange through a VPN breaches its terms and leaves no UK protection. Professional-client status needs wealth and experience tests a student will not meet.
- Spot alone is allowed, but spot alone is just directional crypto, not carry. Spot plus a hedge through a UK-available product (for example a short ETN) is not possible: UK retail may now buy crypto ETNs (since 8 October 2025) but cannot short them.
- Stablecoin lending or staking is the nearest legal yield; it carries platform and depeg risk and is not what this study tests.
- Counterparty risk is the real tail: capital sits on an exchange (FTX-type loss) and a perp short can liquidate on a spike or when the exchange auto-deleverages. None of that is in the backtest.

## Caveats

- Survivorship: the ten coins are today's large coins; coins that fell away (and their funding) are not here. This flatters the alt rows.
- Daily closes only: intraday basis swings, funding-rate timing, and margin top-ups on spikes are not simulated. The liquidation table bounds the worst case (its largest spikes, e.g. DOGE 412% and ETH 203%, may be bad prints in the dump rather than real moves).
- USDT is treated as a dollar; a depeg of the stablecoin or of the exchange is not modelled. Idle capital earns nothing here (exchanges often pay a little, which would help slightly).
- Sample: about 6.8 years, effectively one-and-a-half crypto cycles. 2023 onward is 1400 days, and a Sharpe from that span has a standard error near 0.6, so differences between variants are not significant. Several variants were tried; the chosen one is biased upwards.
- Dated (quarterly) futures basis is not tested: the perp funding rate is the same trade in the form most people use. Spot-perp basis enters as the basis P&L and is included.
- Fees assume Binance taker rates, no VIP tier, no tax. UK tax on short-term gains and on each leg would reduce what is kept.

