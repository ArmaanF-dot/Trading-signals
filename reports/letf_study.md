# Leveraged ETF structural arbitrage (3x bull/bear pairs)

**Verdict:** the volatility decay is real but almost all of it is paid away. Out of sample (2018 on), the best book (pair, reset every 1 days) earns 0.7% a year over cash at institutional costs (Sharpe 0.54, worst day -0.4%, max drawdown -1.1%), and -3.1% a year (Sharpe -2.60) on a UK CFD account. No close-of-day or mispricing effect survives costs either (sections 2 and 3). UK retail cannot short the US funds directly, and the UK-listed 3x ETPs are unborrowable. **No edge worth trading.**

## What was tested

11 US 3x bull/bear pairs with their unlevered index ETF, daily adjusted closes from Yahoo (each pair from its common start, earliest 2008-11-19). Reset intervals [1, 5, 21] trading days chosen before 2018-01-01 at institutional costs; 2018 onward is out of sample. Returns are over the 3-month T-bill. Each book is 1.0 of capital: pair = short 0.5 bull + 0.5 bear; bullh = short 0.5 bull, long 1.5 index ETF; bearh = short 0.5 bear, short 1.5 index ETF. Pairs are equal-weighted.

Cost scenarios (borrow fees are assumptions: no free borrow history exists; IBorrowDesk now needs a paid key. Recent public quotes put SQQQ around 3-4% and SOXS around 1-2%, with spikes far higher):

- **institutional**: borrow 0.5% bull / 3.0% bear; prime broker: rebate = cash rate - 0.25%, long financed at the cash rate
- **inst_hard**: borrow 2.0% bull / 10.0% bear; same, but hard-to-borrow fees (2% bull, 10% bear)
- **retail_broker**: borrow 1.0% bull / 4.0% bear; retail margin account (US-style): no rebate on proceeds, longs at cash + 1.5%
- **uk_cfd**: borrow 1.0% bull / 4.0% bear; UK CFD/spread bet: cash +/- 2.5% admin fee, borrow passed on, 10bp extra per side

## 1. Volatility decay harvesting

Equal-weight basket of pairs, chosen reset interval, out of sample. 'gross' = price P&L only (no borrow, no financing, no spreads).

| book | reset (days) | scenario | ann. over cash | vol | Sharpe | t | max drawdown | worst day |
|---|---|---|---|---|---|---|---|---|
| pair | 1 | gross | 0.2% | 1.2% | 0.21 | 0.6 | -8.6% | -0.4% |
| pair | 1 | institutional | 0.7% | 1.2% | 0.54 | 1.6 | -1.1% | -0.4% |
| pair | 1 | inst_hard | -3.5% | 1.2% | -2.93 | -8.7 | -27.4% | -0.4% |
| pair | 1 | retail_broker | -2.5% | 1.2% | -2.04 | -6.1 | -20.2% | -0.4% |
| pair | 1 | uk_cfd | -3.1% | 1.2% | -2.60 | -7.7 | -24.5% | -0.4% |
| bullh | 21 | gross | 5.6% | 4.7% | 1.17 | 3.5 | -5.9% | -5.5% |
| bullh | 21 | institutional | 2.4% | 4.7% | 0.52 | 1.5 | -6.2% | -5.5% |
| bullh | 21 | inst_hard | 1.6% | 4.7% | 0.36 | 1.1 | -6.7% | -5.5% |
| bullh | 21 | retail_broker | -1.4% | 4.7% | -0.27 | -0.8 | -13.4% | -5.5% |
| bullh | 21 | uk_cfd | -2.9% | 4.7% | -0.61 | -1.8 | -24.5% | -5.5% |
| bearh | 5 | gross | -1.9% | 3.4% | -0.55 | -1.6 | -27.4% | -2.5% |
| bearh | 5 | institutional | 0.9% | 3.4% | 0.28 | 0.8 | -5.9% | -2.5% |
| bearh | 5 | inst_hard | -2.5% | 3.4% | -0.74 | -2.2 | -23.5% | -2.5% |
| bearh | 5 | retail_broker | -4.4% | 3.4% | -1.29 | -3.8 | -35.2% | -2.5% |
| bearh | 5 | uk_cfd | -4.4% | 3.4% | -1.30 | -3.9 | -33.9% | -2.6% |

All reset intervals, institutional costs (in sample / out of sample Sharpe):

| book | H=1 | H=5 | H=21 |
|---|---|---|---|
| pair | 1.26 / 0.54 | 1.00 / 0.69 | 0.68 / 0.55 |
| bullh | 0.24 / 0.69 | 0.62 / 0.73 | 0.75 / 0.52 |
| bearh | 0.20 / -1.21 | 0.72 / 0.28 | 0.42 / 0.40 |

Per pair, out of sample, best book (pair, H=1): gross vs net at institutional and UK CFD costs (annual, over cash):

| pair | gross | institutional | inst_hard | retail_broker | uk_cfd | worst day (inst) |
|---|---|---|---|---|---|---|
| TQQQ/SQQQ | 0.2% | 0.7% | -3.5% | -2.5% | -3.1% | -0.5% |
| UPRO/SPXU | -0.7% | -0.2% | -4.3% | -3.3% | -3.7% | -1.7% |
| SPXL/SPXS | -0.8% | -0.2% | -4.3% | -3.3% | -3.7% | -0.4% |
| SOXL/SOXS | 2.2% | 2.6% | -1.7% | -0.6% | -1.7% | -3.8% |
| TNA/TZA | 0.3% | 0.9% | -3.3% | -2.3% | -2.9% | -2.2% |
| FAS/FAZ | -0.1% | 0.3% | -3.9% | -2.8% | -3.3% | -1.3% |
| TECL/TECS | 0.6% | 0.8% | -3.4% | -2.4% | -3.0% | -1.8% |
| UDOW/SDOW | -0.5% | -0.1% | -4.3% | -3.3% | -3.6% | -1.1% |
| LABU/LABD | 2.0% | 2.1% | -2.1% | -1.1% | -2.1% | -2.3% |
| TMF/TMV | -0.9% | -0.4% | -4.5% | -3.5% | -3.8% | -1.5% |
| YINN/YANG | 0.3% | 0.5% | -3.7% | -2.6% | -3.4% | -2.8% |

By year, pair at institutional costs: 2008 +6.1%, 2009 +8.2%, 2010 +1.0%, 2011 +1.9%, 2012 +0.6%, 2013 +0.4%, 2014 +0.2%, 2015 +0.4%, 2016 +0.3%, 2017 -0.1%, 2018 +0.1%, 2019 -0.5%, 2020 +5.3%, 2021 -0.0%, 2022 +1.2%, 2023 +0.4%, 2024 -0.3%, 2025 -0.1%, 2026 -0.1%.

Why the gross number shrinks: the funds already charge ~0.9-1% a year and pay their own financing, so a short collects the decay plus fees but owes borrow; a retail short receives no interest on the proceeds while the bear fund it is short earns T-bills on 4x its assets, a drag of roughly the cash rate (4-5% a year in 2023-26). Results are also very sensitive to trading exactly at the close: Quantpedia's version of the TQQQ/SQQQ pair (Oct 2026) went from +2.1% a year to about -1% a year when rebalanced 10 minutes before the close, because the funds' own rebalancing moves prices into the close.

## 2. Close-of-day rebalancing flows

Last half hour (15:30 to close) regressed on the day's move to 15:30, Yahoo hourly bars. Trade = follow the day's sign for the last half hour.

| ETF | days | beta | t | gross bp/trade | net bp (1bp/side) | net bp (5bp/side) | hit rate |
|---|---|---|---|---|---|---|---|
| IWM | 722 (2023-12-29 to 2026-11-25) | -0.024 | -2.9 | -2.32 | -4.32 | -12.32 | 48% |
| QQQ | 724 (2023-12-29 to 2026-11-25) | 0.002 | 0.2 | -1.98 | -3.98 | -11.98 | 47% |
| SOXX | 722 (2023-12-29 to 2026-11-25) | -0.005 | -0.5 | -3.45 | -5.45 | -13.45 | 49% |
| SPY | 722 (2023-12-29 to 2026-11-25) | 0.001 | 0.1 | -1.95 | -3.95 | -11.95 | 44% |

Close to next open regressed on the day's close-to-close move (from 2008). Trade = fade the day into the next open.

| ETF | days | beta | t | beta 2008-16 | beta 2017-26 | gross bp/trade | net bp (1bp/side) | net bp (5bp/side) |
|---|---|---|---|---|---|---|---|---|
| SPY | 4755 | -0.045 | -5.1 | -0.014 | -0.083 | 1.77 | -0.23 | -8.23 |
| QQQ | 4755 | -0.038 | -4.4 | -0.010 | -0.061 | 0.92 | -1.08 | -9.08 |
| IWM | 4755 | -0.016 | -1.9 | -0.009 | -0.024 | 0.85 | -1.15 | -9.15 |
| SOXX | 4755 | -0.028 | -3.2 | 0.010 | -0.050 | -1.13 | -3.13 | -11.13 |

Hourly history is only ~2 years (Yahoo's limit), so the intraday test is short. A UK spread bet on the US 500 or US Tech 100 costs about 0.5-1bp a side in the cash session but the overnight leg spans the wider out-of-hours spread.

## 3. Mispricing against the index (premium proxy)

Daily residual e = r(fund) - (+/-3) x r(index ETF), both at the 4 pm close, from 2010. Trade next day against yesterday's residual when |e| exceeds the round-trip cost of both legs (fund + 3x index ETF), assuming you can trade at the close you just observed (optimistic).

| fund | index | days | residual sd (bp) | lag-1 autocorr | trades | gross bp | cost bp | net bp |
|---|---|---|---|---|---|---|---|---|
| TQQQ | QQQ | 4223 | 13.3 | -0.46 | 1364 | 8.4 | 10.0 | -1.6 |
| SQQQ | QQQ | 4223 | 14.3 | -0.42 | 1604 | 7.8 | 10.0 | -2.2 |
| UPRO | SPY | 4251 | 11.3 | -0.44 | 1173 | 7.2 | 10.0 | -2.8 |
| SPXU | SPY | 4251 | 12.7 | -0.41 | 1659 | 6.6 | 10.0 | -3.4 |
| SPXL | SPY | 4251 | 12.4 | -0.37 | 1361 | 6.4 | 10.0 | -3.6 |
| SPXS | SPY | 4251 | 14.0 | -0.30 | 1762 | 5.2 | 10.0 | -4.8 |
| SOXL | SOXX | 4204 | 31.9 | -0.42 | 2717 | 14.0 | 10.0 | 4.0 |
| SOXS | SOXX | 4204 | 32.9 | -0.41 | 2836 | 13.2 | 10.0 | 3.2 |
| TNA | IWM | 4251 | 14.0 | -0.46 | 1746 | 8.4 | 10.0 | -1.6 |
| TZA | IWM | 4251 | 15.5 | -0.37 | 1994 | 7.4 | 10.0 | -2.6 |
| FAS | XLF | 4251 | 62.6 | -0.10 | 3251 | 7.1 | 10.0 | -2.9 |
| FAZ | XLF | 4251 | 62.8 | -0.10 | 2853 | 8.2 | 16.0 | -7.8 |
| TECL | XLK | 4251 | 26.6 | -0.20 | 1563 | 9.0 | 16.0 | -7.0 |
| TECS | XLK | 4251 | 29.0 | -0.26 | 1879 | 10.9 | 16.0 | -5.1 |
| UDOW | DIA | 4223 | 12.1 | -0.43 | 582 | 11.4 | 16.0 | -4.6 |
| SDOW | DIA | 4223 | 12.5 | -0.38 | 717 | 9.2 | 16.0 | -6.8 |
| LABU | XBI | 2892 | 30.3 | -0.49 | 1499 | 17.5 | 16.0 | 1.5 |
| LABD | XBI | 2892 | 33.1 | -0.48 | 1576 | 17.5 | 16.0 | 1.5 |
| TMF | TLT | 4251 | 17.0 | -0.47 | 2057 | 9.4 | 10.0 | -0.6 |
| TMV | TLT | 4251 | 15.1 | -0.40 | 1040 | 9.6 | 16.0 | -6.4 |
| YINN | FXI | 4251 | 101.6 | -0.06 | 2479 | 9.8 | 16.0 | -6.2 |
| YANG | FXI | 4251 | 101.1 | -0.05 | 2525 | 9.9 | 16.0 | -6.1 |

Residuals do mean-revert (negative autocorrelation), as expected from closing-print noise and the funds' swap resets, but the reversal is mostly smaller than the cost of trading both legs. Positive net cells with 200+ trades: SOXL, SOXS, LABU, LABD; these rely on trading at the very close you are measuring, and include the index ETF tracking gap (e.g. SOXX and the funds' benchmark differ), so they are not tradable as shown.

## UK retail feasibility

- **US-listed funds (TQQQ, SQQQ, SOXL...)**: UK retail brokers block them for want of a PRIIPs KID (Interactive Brokers says so explicitly). The FCA's Consumer Composite Investments regime replaced PRIIPs from 6 April 2026 with full go-live on 8 June 2027; it may eventually widen access, but no broker has unblocked US ETFs for UK retail on that basis yet. Elective professional status unblocks them but removes FCA retail protections.
- **UK-listed 3x ETPs (QQQ3, QQQS, 3USL, 3USS on the LSE)**: buyable in an ISA, but cannot be shorted: IG lists the 3x Short US Tech 100 ETP as 'Unborrowable'. Long-only, they are the wrong side of the decay trade.
- **CFDs/spread bets on US ETFs**: IG and IBKR UK offer CFDs on large US ETFs; shorts receive the cash rate minus an admin fee (about 2.5%) and pay any borrow charge, which is what the uk_cfd scenario models. Spread bets are tax-free, but the economics are the same.
- **Tail risk**: a short bear fund can lose 30%+ in a day (e.g. SQQQ/SOXS in crashes); with CFD margin of 20-25% a few such days wipe the account.

## Caveats

- Survivorship: only funds alive today are on Yahoo. Closed products (3x oil, 3x gold miners, VelocityShares notes, XIV) are missing, and several of their deaths were exactly the blow-ups a decay-short would have suffered or profited from.
- Borrow fees and rebates are flat assumptions; real fees are highest exactly when the trade looks most attractive (high vol, crowded shorts), and borrow can be recalled.
- Trades at the official close; real fills before the close did much worse in independent tests.
- Three reset intervals and three books were tried; the best is reported, which flatters it.

Sources: Quantpedia, 'Shorting Leveraged ETFs: The Role of Borrowing Costs and Rebalancing in Volatility-Decay Strategies' (Oct 2026); Interactive Brokers FAQ on UK/EEA retail and US ETFs; FCA PS25/20 (CCI regime); IG market page for the Leverage Shares 3x Short US Tech 100 ETP.

Built by `python run.py letf [--refresh]`; panel in `reports/letf_panel.csv.gz`, daily returns of the best book in `reports/letf_daily.csv`.
