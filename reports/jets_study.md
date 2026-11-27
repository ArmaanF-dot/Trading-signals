# Corporate jet tracking study

Data: adsb.lol daily archive (ODbL), 905 days scanned from 2024-03-20 to 2026-11-25. Watchlist: 215 turbofan jets registered in the FAA database to 118 SEC-listed companies; 188 of them were seen arriving somewhere (114 companies after dropping operating fleets of more than 6 jets).

**Verdict: novel: no edge (OOS 20d excess +0.04%, t 0.3, best side net of costs -0.53%, in-sample sign flipped); omaha: no edge (OOS 20d excess -0.49%, t -0.3, best side net of costs +0.05%, in-sample sign flipped).**

## Returns after trips (excess over SPY, entry at the close after the data is published)

| Signal | Period | Events | Excess 5d | Excess 20d | Excess 60d | Net 60d (tiered) | Net 60d (2.5%) |
|---|---|---|---|---|---|---|---|
| novel | in sample | 471 | +0.05% (t -0.2, n 463) | -0.83% (t -0.9, n 463) | -2.33% (t -2.4, n 463) | -2.98% (t -3.1, n 463) | -4.83% (t -5.2, n 463) |
| novel | out of sample | 4074 | +0.10% (t 1.0, n 3989) | -0.03% (t 0.3, n 3838) | -0.67% (t 0.1, n 3429) | -1.23% (t -0.4, n 3429) | -3.17% (t -2.1, n 3429) |
| novel | all | 4545 | +0.10% (t 0.9, n 4452) | -0.12% (t 0.0, n 4301) | -0.87% (t -0.3, n 3892) | -1.44% (t -0.9, n 3892) | -3.37% (t -2.8, n 3892) |
| omaha | in sample | 30 | +0.14% (t 0.6, n 30) | +1.94% (t 1.3, n 30) | -0.52% (t -0.2, n 30) | -1.14% (t -0.4, n 30) | -3.02% (t -1.0, n 30) |
| omaha | out of sample | 73 | +0.08% (t 0.6, n 72) | -0.45% (t -0.3, n 71) | -0.64% (t 0.1, n 63) | -1.08% (t -0.1, n 63) | -3.14% (t -0.9, n 63) |
| omaha | all | 103 | +0.09% (t 0.9, n 102) | +0.27% (t 0.3, n 101) | -0.61% (t 0.0, n 93) | -1.11% (t -0.3, n 93) | -3.11% (t -1.3, n 93) |

Costs: tiered by 20-day dollar volume as in the other studies; the last column charges a flat 2.5% round trip. Means are clipped at the 1st/99th percentile when there are at least 20 events.

## Deals within 90 days (Form 425 or 8-K Item 2.01)

| Signal | Events with filings data | Followed by a deal filing | Same companies' base rate |
|---|---|---|---|
| novel | 3920 | 4.7% | 4.9% |
| omaha | 93 | 3.2% | 4.4% |

## Omaha

| Date | Company | Jet | Airport | 20d excess |
|---|---|---|---|---|
| 2024-03-20 | Core Natural Resources, Inc. (CNR) | N56BA | KOMA | +3.5% |
| 2024-03-21 | ASTEC INDUSTRIES INC (ASTE) | N842A | KOMA | +6.4% |
| 2024-04-16 | COSTCO WHOLESALE CORP /NEW (COST) | N83CW | KOMA | +4.4% |
| 2024-04-26 | StoneX Group Inc. (SNEX) | N855A | KOMA | -1.4% |
| 2024-05-15 | MARTIN MARIETTA MATERIALS INC (MLM) | N404MM | KOMA | -5.1% |
| 2024-05-16 | GENUINE PARTS CO (GPC) | N28GP | KOMA | -11.2% |
| 2024-05-30 | Walmart Inc. (WMT) | N986BL | KOMA | -1.1% |
| 2024-06-05 | CUMMINS INC (CMI) | N281CE | KOMA | -5.9% |
| 2024-06-05 | COSTCO WHOLESALE CORP /NEW (COST) | N82CW | KOMA | +0.3% |
| 2024-06-14 | Core Natural Resources, Inc. (CNR) | N56BA | KOMA | +4.6% |
| 2024-06-20 | ASTEC INDUSTRIES INC (ASTE) | N842A | KOMA | +10.7% |
| 2024-06-20 | Schneider National, Inc. (SNDR) | N935GB | KOMA | +6.4% |
| 2024-06-23 | TUTOR PERINI CORP (TPC) | N314TP | KOMA | +18.5% |
| 2024-06-27 | GENERAL DYNAMICS CORP (GD) | N585G | KOMA | +0.2% |
| 2024-06-29 | Walmart Inc. (WMT) | N15DP | KOMA | +3.1% |
| 2024-07-08 | COSTCO WHOLESALE CORP /NEW (COST) | N91CW | KOMA | -1.7% |
| 2024-07-23 | Schneider National, Inc. (SNDR) | N935GB | KOMA | +5.2% |
| 2024-08-26 | CUMMINS INC (CMI) | N282CE | KOMA | +1.8% |
| 2024-09-10 | DOLLAR GENERAL CORP (DG) | N855DG | KOMA | -0.9% |
| 2024-09-18 | NUCOR CORP (NUE) | N750JT | KOMA | +4.2% |
| 2024-09-24 | DILLARD'S, INC. (DDS) | N917BD | KOMA | -1.1% |
| 2024-09-26 | PACCAR INC (PCAR) | N706P | KOMA | +6.6% |
| 2024-09-30 | QUANTA SERVICES, INC. (PWR) | N282QA | KOMA | +3.6% |
| 2024-10-09 | ASTEC INDUSTRIES INC (ASTE) | N842A | KOMA | +18.2% |
| 2024-11-05 | MARTIN MARIETTA MATERIALS INC (MLM) | N404MM | KOMA | -8.2% |
| 2024-11-11 | LAS VEGAS SANDS CORP (LVS) | N339LS | KOMA | +8.8% |
| 2024-11-21 | Motorola Solutions, Inc. (MSI) | N513FX | KOMA | -6.2% |
| 2024-11-30 | Walmart Inc. (WMT) | N986BL | KOMA | +0.3% |
| 2024-12-17 | Schneider National, Inc. (SNDR) | N935GB | KOMA | -2.3% |
| 2024-12-19 | COSTCO WHOLESALE CORP /NEW (COST) | N84CW | KOMA | -4.4% |
| 2025-01-09 | UFP INDUSTRIES INC (UFPI) | N255FP | KOMA | +2.6% |
| 2025-01-09 | GENERAL DYNAMICS CORP (GD) | N586G | KOMA | -4.8% |
| 2025-02-11 | EASTMAN CHEMICAL CO (EMN) | N494EC | KOMA | -2.0% |
| 2025-02-19 | Walmart Inc. (WMT) | N45GH | KOMA | -4.4% |
| 2025-02-21 | COSTCO WHOLESALE CORP /NEW (COST) | N86CW | KOMA | -7.0% |
| 2025-02-21 | Motorola Solutions, Inc. (MSI) | N513FX | KOMA | +5.9% |
| 2025-03-18 | DILLARD'S, INC. (DDS) | N917BD | KOMA | -8.3% |
| 2025-04-08 | COSTCO WHOLESALE CORP /NEW (COST) | N86CW | KOMA | +1.5% |
| 2025-04-22 | PACCAR INC (PCAR) | N706P | KOMA | -2.6% |
| 2025-05-14 | MARTIN MARIETTA MATERIALS INC (MLM) | N404MM | KOMA | -2.8% |
| 2025-06-16 | DILLARD'S, INC. (DDS) | N917BD | KOMA | +7.0% |
| 2025-06-27 | MARTIN MARIETTA MATERIALS INC (MLM) | N404MM | KOMA | +2.8% |
| 2025-07-02 | AFLAC INC (AFL) | N285AF | KOMA | -5.6% |
| 2025-07-08 | MORGAN GROUP HOLDING CO (MGHL) | N926TP | KOMA | +18.4% |
| 2025-07-15 | COSTCO WHOLESALE CORP /NEW (COST) | N83CW | KOMA | -0.3% |
| 2025-08-12 | Walmart Inc. (WMT) | N45GH | KOMA | -0.1% |
| 2025-08-13 | MARTIN MARIETTA MATERIALS INC (MLM) | N404MM | KOMA | -1.2% |
| 2025-08-20 | DOLLAR GENERAL CORP (DG) | N855DG | KOMA | -13.9% |
| 2025-09-25 | COSTCO WHOLESALE CORP /NEW (COST) | N91CW | KOMA | -0.6% |
| 2025-10-08 | CUMMINS INC (CMI) | N282CE | KOMA | +8.6% |
| 2025-11-19 | AFLAC INC (AFL) | N280AF | KOMA | -4.8% |
| 2025-11-21 | ONEOK INC /NEW/ (OKE) | N300KE | KOMA | +1.4% |
| 2025-11-24 | Motorola Solutions, Inc. (MSI) | N513FX | KOMA | -0.4% |
| 2025-12-02 | Walmart Inc. (WMT) | N45GH | KOMA | -1.4% |
| 2025-12-04 | BELDEN INC. (BDC) | N363AP | KOMA | -5.6% |
| 2025-12-04 | HUMANA INC (HUM) | N733K | KOMA | +7.7% |
| 2025-12-09 | GENERAL DYNAMICS CORP (GD) | N587G | KOMA | +2.2% |
| 2025-12-10 | COSTCO WHOLESALE CORP /NEW (COST) | N84CW | KOMA | +5.5% |
| 2025-12-18 | DOLLAR GENERAL CORP (DG) | N855DG | KOMA | +6.9% |
| 2026-01-05 | PACCAR INC (PCAR) | N701P | KOMA | +10.8% |
| 2026-01-08 | JACK HENRY & ASSOCIATES INC (JKHY) | N895JH | KOMA | -9.3% |
| 2026-01-13 | Walmart Inc. (WMT) | N986BL | KOMA | +12.6% |
| 2026-01-16 | COSTCO WHOLESALE CORP /NEW (COST) | N91CW | KOMA | +2.2% |
| 2026-01-21 | CUMMINS INC (CMI) | N282CE | KOMA | +2.0% |
| 2026-01-26 | GENERAL DYNAMICS CORP (GD) | N586G | KOMA | -6.1% |
| 2026-01-27 | BJ's Wholesale Club Holdings, Inc. (BJ) | N496QS | KOMA | +6.7% |
| 2026-02-11 | ASTEC INDUSTRIES INC (ASTE) | N12JK | KOMA | -4.6% |
| 2026-02-15 | Air Products & Chemicals, Inc. (APD) | N987QS | KOMA | +4.8% |
| 2026-02-25 | Walmart Inc. (WMT) | N986BL | KOMA | +4.6% |
| 2026-03-18 | AFLAC INC (AFL) | N285AF | KOMA | -1.1% |
| 2026-03-19 | KROGER CO (KR) | N304KC | KOMA | -16.5% |
| 2026-03-25 | GENERAL DYNAMICS CORP (GD) | N585G | KOMA | -22.1% |
| 2026-04-01 | PACCAR INC (PCAR) | nan | KOMA | -11.8% |
| 2026-04-08 | DILLARD'S, INC. (DDS) | N917BD | KOMA | -16.4% |
| 2026-04-13 | COSTCO WHOLESALE CORP /NEW (COST) | N84CW | KOMA | -1.3% |
| 2026-04-15 | LOWES COMPANIES INC (LOW) | N44LC | KOMA | -13.9% |
| 2026-05-13 | MARTIN MARIETTA MATERIALS INC (MLM) | N404MM | KOMA | +1.4% |
| 2026-05-13 | DILLARD'S, INC. (DDS) | N917BD | KOMA | +14.9% |
| 2026-05-26 | STRYKER CORP (SYK) | N421SC | KOMA | +5.2% |
| 2026-06-09 | GENERAL DYNAMICS CORP (GD) | N587G | KOMA | +6.1% |
| 2026-06-10 | Life Time Group Holdings, Inc. (LTH) | N560LT | KOMA | +17.1% |
| 2026-06-12 | Air Products & Chemicals, Inc. (APD) | N987QS | KOMA | +4.2% |
| 2026-06-14 | BJ's Wholesale Club Holdings, Inc. (BJ) | N496QS | KOMA | -0.2% |
| 2026-06-15 | Motorola Solutions, Inc. (MSI) | N513FX | KOMA | +2.3% |
| 2026-06-16 | NUCOR CORP (NUE) | N750JT | KOMA | -6.7% |
| 2026-06-20 | TUTOR PERINI CORP (TPC) | N314TP | KOMA | +6.0% |
| 2026-06-23 | DILLARD'S, INC. (DDS) | N917BD | KOMA | -4.2% |
| 2026-07-10 | DOLLAR GENERAL CORP (DG) | N855DG | KOMA | -4.0% |
| 2026-07-21 | Walmart Inc. (WMT) | N15DP | KOMA | +1.6% |
| 2026-07-23 | PACCAR INC (PCAR) | N706P | KOMA | -4.3% |
| 2026-08-06 | BELDEN INC. (BDC) | N363AP | KOMA | -7.5% |
| 2026-08-15 | KROGER CO (KR) | N304KC | KOMA | +13.0% |
| 2026-08-17 | Life Time Group Holdings, Inc. (LTH) | N890LT | KOMA | -8.5% |
| 2026-09-06 | Air Products & Chemicals, Inc. (APD) | N987QS | KOMA | -7.0% |
| 2026-09-08 | ASTEC INDUSTRIES INC (ASTE) | N12JK | KOMA | -9.5% |
| 2026-09-12 | Walmart Inc. (WMT) | N17ZP | KOMA | +1.1% |
| 2026-09-14 | PACCAR INC (PCAR) | nan | KOMA | -14.8% |
| 2026-09-14 | ROCKWELL AUTOMATION, INC (ROK) | N57AB | KOMA | +0.7% |
| 2026-09-15 | GENERAL DYNAMICS CORP (GD) | N586G | KOMA | -8.9% |
| 2026-10-15 | COSTCO WHOLESALE CORP /NEW (COST) | N84CW | KOMA | +13.2% |
| 2026-10-26 | PACCAR INC (PCAR) | nan | KOMA | +8.5% |
| 2026-10-29 | DILLARD'S, INC. (DDS) | N917BD | KOMA |  |
| 2026-11-25 | CUMMINS INC (CMI) | N283CE | KOMA |  |

All aircraft arriving in Omaha over the scanned days: 7121 distinct airframes, 20069 business-jet arrivals. Owner names, where adsb.lol's database has them, are mostly trustees, LLCs, fractional operators and charter firms, so most visits cannot be tied to a company.

| Owner/operator (as broadcast database lists it) | Business-jet arrivals |
|---|---|
| KIEWIT ENGINEERING GROUP INC | 1153 |
| CONAGRA BRANDS INC | 714 |
| SILVERHAWK AVIATION INC | 482 |
| FLEXJET LLC | 345 |
| NETJETS SALES INC | 297 |
| UNION PACIFIC RAILROAD CO | 269 |
| (unknown) | 267 |
| 1212012 LLC | 243 |
| CONGRA BRANDS INC | 238 |
| TACOCAT LLC | 222 |
| NEARY DANIEL P, LITTLE GEORGE, SCHMID JEFFREY R, BELL RICHARD, A | 203 |
| TVPX AIRCRAFT SOLUTIONS INC TRUSTEE | 196 |

## Berkshire Hathaway new 13F positions

| Quarter | New issuer | Its jet on the watchlist? | Visited Omaha before filing? |
|---|---|---|---|
| 2023-03-31 | CAPITAL ONE FINL | no | no |
| 2023-03-31 | DIAGEO P L C | no | no |
| 2023-03-31 | VITESSE ENERGY | no | no |
| 2023-06-30 | D R HORTON | no | no |
| 2023-06-30 | LENNAR | no | no |
| 2023-06-30 | NVR | no | no |
| 2023-09-30 | ATLANTA BRAVES HLDGS | no | no |
| 2023-09-30 | SIRIUS XM | no | no |
| 2024-03-31 | CHUBB | no | no |
| 2024-06-30 | HEICO | no | no |
| 2024-06-30 | ULTA BEAUTY | no | no |
| 2024-09-30 | DOMINOS PIZZA | no | no |
| 2024-09-30 | POOL | no | no |
| 2024-12-31 | CONSTELLATION BRANDS | no | no |
| 2025-06-30 | ALLEGION | no | no |
| 2025-06-30 | D R HORTON | no | no |
| 2025-06-30 | LAMAR ADVERTISING | no | no |
| 2025-06-30 | NUCOR | NUE | yes |
| 2025-06-30 | UNITEDHEALTH | no | no |
| 2025-09-30 | ALPHABET | no | no |
| 2025-12-31 | BANK AMERICA | no | no |
| 2025-12-31 | DIAGEO | no | no |
| 2025-12-31 | LIBERTY LIVE | no | no |
| 2025-12-31 | YORK TIMES | no | no |
| 2026-03-31 | CHUBB SWITZ | no | no |
| 2026-03-31 | DELTA AIR LINES | no | no |
| 2026-03-31 | JEFFERIES FINANCIAL IN | no | no |
| 2026-03-31 | MACYS | no | no |
| 2026-03-31 | SIRIUSXM | no | no |
| 2026-03-31 | YORK TIMES MTN BE | no | no |
| 2026-06-30 | BANK AMER | no | no |
| 2026-06-30 | CHUBB | no | no |
| 2026-06-30 | D R HORTON | no | no |
| 2026-09-30 | BENDING SPOONS SPA | no | no |

## What can and cannot be inferred

- A landing shows where a plane went, not who was on it or who they met. Omaha also hosts Union Pacific, Kiewit, Mutual of Omaha, TD Ameritrade's old base and others, so an Omaha visit is not a Berkshire meeting.
- Warren Buffett and Berkshire's managers fly NetJets (fractional, shared tail numbers), so their own travel cannot be followed; visitors could only be seen if they fly their own registered jet.
- Most large-company jets are registered through bank trustees (Bank of Utah, Wilmington Trust, TVPX: about 4,100 US jets) or anonymous LLCs, and many fly with the FAA's PIA privacy hex. The watchlist only holds jets registered openly in a listed company's name, so coverage is a small, biased slice.
- The watchlist is today's FAA registry plus aircraft deregistered since 2023; jets bought by a company after a trip, or held under a name we cannot match, are missed.
- Licences: adsb.lol history is ODbL 1.0 (open, attribution and share-alike for derived databases); the FAA registry and EDGAR are US public records. OpenSky's API was unreachable from this environment and its historical database needs an approved research account; ADS-B Exchange's free samples are one day a month. No paid data used. Tracking aircraft broadcasts is legal in the US and UK; trading on it is not insider dealing since it uses public information, but publishing a named individual's movements raises privacy issues, so the repo stores company jets only.

