# Job postings and earnings, second pass

Companies with a public Greenhouse, Lever or Ashby board today: 208; with at least 12 archived months since 2017: 84. Earnings reports with a postings change measured before the report: 687 (liquid: 488). Workday-hosted companies (most non-tech) cannot be rebuilt from the archive: their boards load through a POST request the archive does not keep.

Every cell below is a rank correlation (IC) between a feature measured before the report and an outcome, computed within each calendar quarter and averaged; t is across quarters. Positive means more of the feature goes with a better outcome. |t| below 2 is noise.

| feature | Earnings-day reaction (EAR) | Revenue acceleration (quarter reported) | Drift 20d after report | Drift 60d after report | Drift 120d after report | Drift 250d after report |
|---|---|---|---|---|---|---|
| Total postings, change | +0.019 (t 0.5, n 675) | +0.055 (t 1.6, n 611) | -0.042 (t -0.9, n 648) | -0.060 (t -1.2, n 643) | -0.094 (t -2.2, n 617) | -0.069 (t -1.3, n 550) |
| Engineering postings, change | +0.021 (t 0.4, n 362) | +0.075 (t 1.4, n 331) | -0.080 (t -1.3, n 357) | -0.029 (t -0.4, n 357) | -0.080 (t -1.6, n 355) | -0.080 (t -1.3, n 347) |
| Sales and go-to-market postings, change | +0.008 (t 0.1, n 362) | +0.062 (t 1.4, n 331) | +0.024 (t 0.4, n 357) | +0.037 (t 0.6, n 357) | +0.018 (t 0.3, n 355) | -0.051 (t -0.8, n 347) |
| New postings (adds) / older count | +0.002 (t 0.0, n 675) | -0.002 (t -0.0, n 611) | -0.061 (t -1.3, n 648) | -0.074 (t -1.4, n 643) | -0.096 (t -2.3, n 617) | -0.058 (t -1.1, n 550) |
| Postings taken down / older count | -0.015 (t -0.3, n 675) | -0.014 (t -0.2, n 611) | -0.042 (t -0.9, n 648) | -0.044 (t -1.0, n 643) | -0.076 (t -1.8, n 617) | -0.067 (t -1.3, n 550) |
| Adds minus removals / older count | +0.018 (t 0.5, n 675) | +0.051 (t 1.5, n 611) | -0.042 (t -0.9, n 648) | -0.064 (t -1.2, n 643) | -0.092 (t -2.1, n 617) | -0.065 (t -1.2, n 550) |

Cells with |t| >= 2: 3 of 36. With this many tests, about 2 would pass by chance alone.

## Total postings change, by tercile, longer holds

Liquid events only; each trade pays 2.5% once (the project's cost rule). Mean excess over SPY (winsorised 1-99%) and t of monthly averages.

| tercile | n | 20d net of 2.5% | 60d net of 2.5% | 120d net of 2.5% | 250d net of 2.5% |
|---|---|---|---|---|---|
| T1 (cutting) | 145 | -2.49% (t -0.4) | +2.77% (t 0.4) | +3.91% (t 0.8) | +15.57% (t 1.1) |
| T2 | 144 | -2.21% (t -0.3) | -2.08% (t -0.2) | -0.47% (t -0.6) | -4.09% (t -2.1) |
| T3 (adding) | 162 | -4.84% (t -3.7) | -8.92% (t -3.1) | -3.91% (t -1.8) | -3.56% (t -0.5) |

## How big a sample would settle it

With 687 events the smallest rank correlation this test can reliably detect is about 0.11 (5% significance, 80% power, treating events as independent; overlapping events make it worse). Signals that quant funds trade, job postings included, typically have rank correlations of roughly 0.02 to 0.05 with later returns or surprises (a rule of thumb, not a measured figure for this data). Detecting 0.05 needs about 3,136 events; 0.03 needs about 8,712. The earnings-day move has a standard deviation of 16.0% here, so a long-short tercile gap of 1% per report would need about 6,031 events in total.

## Verdict

No feature predicts the reaction, the revenue surprise or the drift beyond what chance gives. The sample is far too small to rule out the small effects quant funds trade, but nothing here is large enough to trade on our costs.

Caveats: survivors only (today's boards); job titles classified by keywords; archive captures are irregular and an HTML capture can miss roles on paginated boards; revenue acceleration is a stand-in for the consensus surprise, which is not free. Not financial advice.
