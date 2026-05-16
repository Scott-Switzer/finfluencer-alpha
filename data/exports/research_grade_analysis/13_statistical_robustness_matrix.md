# Statistical Robustness Matrix

## Headline Summary

Two parallel calculations are reported. The **canonical baseline** restricts the
ticker universe to the 16-ticker `yfinance_market_data.csv` file that was used
to derive the locked-spec abnormal returns (`n=1,516 (1D)`,
`mean_1D=0.002728`, `p_1D=0.001174`; `n=1,503 (5D)`, `mean_5D=0.005236`,
`p_5D=0.001425`). The **expanded sample** uses
`yfinance_expanded_market_data.csv`, which covers all 23 locked event tickers
plus benchmarks/sector ETFs and adds 6 smaller-cap event tickers (AMC, COIN,
GME, HOOD, SHOP, SMCI). The shift between the two rows is itself a robustness
finding: the headline result is sensitive to small-cap inclusion.

### Canonical baseline (16-ticker file, matches locked spec)

| Window | n | mean | median | t | p (normal approx) |
| --- | --- | --- | --- | --- | --- |
| AR_0_1 (1D) | 1516 | 0.002728 | 0.000773 | 3.251 | 0.0011 |
| AR_0_5 (5D) | 1503 | 0.005236 | 0.000421 | 3.195 | 0.0014 |

### Expanded sample (35-ticker file, all locked events with market coverage)

| Window | n | mean | median | t | p (normal approx) | bootstrap 95% CI |
| --- | --- | --- | --- | --- | --- | --- |
| AR_0_1 (1D) | 1549 | 0.000016 | 0.000513 | 0.015 | 0.9882 | [-0.002119, 0.002147] |
| AR_0_5 (5D) | 1536 | 0.003269 | -0.000162 | 1.868 | 0.0618 | [-0.000186, 0.006692] |

All numbers above use SPY-adjusted abnormal returns on the locked sample. The
canonical mean/p values match the locked yfinance provisional values to
displayed precision. The return windows use adjusted-close-to-adjusted-close
price relatives; they are event-study windows, not executable open/close
trading rules.

## Timing and Core Robustness Cuts

| Cut | 1D n | 1D mean | 1D t | 1D p | 5D n | 5D mean | 5D t | 5D p | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Canonical baseline | 1516 | 0.002728 | 3.251 | 0.0011 | 1503 | 0.005236 | 3.195 | 0.0014 | 16-ticker locked yfinance file |
| Expanded all events | 1549 | 0.000016 | 0.015 | 0.9882 | 1536 | 0.003269 | 1.868 | 0.0618 | All locked events with expanded market coverage |
| Low-lookahead-risk | 510 | 0.001987 | 2.098 | 0.0359 | 505 | 0.007133 | 2.961 | 0.0031 | before_open/weekend_or_holiday only; fixed UTC-to-ET approximation |
| Duplicate-collapsed | 1112 | 0.001345 | 1.387 | 0.1655 | 1104 | 0.004058 | 2.183 | 0.0290 | First event per creator+ticker+weekday-adjusted-date cluster |
| Non-top-ticker | 574 | -0.006835 | -3.070 | 0.0021 | 565 | -0.004901 | -1.871 | 0.0613 | Excludes NVDA/TSLA/AAPL/AMD/AMZN |
| High-quality tier A/B | 922 | -0.002039 | -1.391 | 0.1642 | 916 | 0.000677 | 0.307 | 0.7585 | Automated event-quality score >= 65 |

## Sign Test (Wilcoxon Approximation via Binomial Sign)

| Window | n_nonzero | n_positive | two-sided p |
| --- | --- | --- | --- |
| AR_0_1 (1D) | 1549 | 809 | 0.0796 |
| AR_0_5 (5D) | 1536 | 766 | 0.9187 |

## Multiple-Testing Adjustment

Benjamini-Hochberg FDR is computed across the headline timing/core-cut
p-values plus the buy, sell, and winsorized 5D cuts reported below.

| Test | raw p | BH q |
| --- | --- | --- |
| Canonical baseline AR_0_1 | 0.0011 | 0.0105 |
| Canonical baseline AR_0_5 | 0.0014 | 0.0105 |
| Expanded all events AR_0_1 | 0.9882 | 0.9882 |
| Expanded all events AR_0_5 | 0.0618 | 0.1030 |
| Low-lookahead-risk AR_0_1 | 0.0359 | 0.0770 |
| Low-lookahead-risk AR_0_5 | 0.0031 | 0.0115 |
| Duplicate-collapsed AR_0_1 | 0.1655 | 0.2069 |
| Duplicate-collapsed AR_0_5 | 0.0290 | 0.0726 |
| Non-top-ticker AR_0_1 | 0.0021 | 0.0107 |
| Non-top-ticker AR_0_5 | 0.0613 | 0.1030 |
| High-quality tier A/B AR_0_1 | 0.1642 | 0.2069 |
| High-quality tier A/B AR_0_5 | 0.7585 | 0.8127 |
| Buy-only AR_0_5 | 0.0049 | 0.0148 |
| Sell-only AR_0_5 | 0.3255 | 0.3756 |
| Winsorized 1%/99% AR_0_5 | 0.0714 | 0.1071 |

## Direction and Sample Cuts (AR_0_5)

| Cut | n | mean | t | p |
| --- | --- | --- | --- | --- |
| Buy only | 1193 | 0.005375 | 2.810 | 0.0049 |
| Sell only | 343 | -0.004057 | -0.983 | 0.3255 |
| Duplicate-collapsed | 1104 | 0.004058 | 2.183 | 0.0290 |
| High-quality only (tier A/B) | 916 | 0.000677 | 0.307 | 0.7585 |
| Winsorized 1%/99% | 1536 | 0.002941 | 1.803 | 0.0714 |
| Non-top-ticker (exclude NVDA/TSLA/AAPL/AMD/AMZN) | 565 | -0.004901 | -1.871 | 0.0613 |

## Leave-One-Creator-Out (AR_0_5, top 5 creators)

| Excluded creator | n_remaining | mean | t | p |
| --- | --- | --- | --- | --- |
| Jose Najarro Stocks | 1250 | 0.002615 | 1.303 | 0.1926 |
| Mark Roussin, CPA | 1309 | 0.002822 | 1.421 | 0.1555 |
| The Investor Channel | 1412 | 0.002636 | 1.440 | 0.1499 |
| Couch Investor | 1426 | 0.004090 | 2.246 | 0.0247 |
| HyperChange | 1460 | 0.003859 | 2.256 | 0.0241 |

## Leave-One-Ticker-Out (AR_0_5, top 5 tickers)

| Excluded ticker | n_remaining | mean | t | p |
| --- | --- | --- | --- | --- |
| NVDA | 1257 | 0.002317 | 1.168 | 0.2430 |
| TSLA | 1292 | 0.002730 | 1.631 | 0.1029 |
| AAPL | 1379 | 0.003252 | 1.684 | 0.0922 |
| AMD | 1389 | 0.001369 | 0.768 | 0.4428 |
| AMZN | 1392 | 0.003224 | 1.696 | 0.0900 |

## Placebo (Permute Event Dates Within Ticker, 500 Reps)

- Average placebo mean AR_0_5 across 500 permutations: `0.003316`
- Empirical p-value (share of placebos with mean >= observed): `0.5020`
- Interpretation: a low share here means the observed mean sits in the upper
  tail of the within-ticker reshuffle distribution and is not a mechanical
  artifact of which tickers happen to be in the sample.

## Planned Additional Tests (Bloomberg-Day Rerun)

| Test | Status | Required data |
| --- | --- | --- |
| Permutation test on actual event-date shifts +/-{15,30,60} trading days | Plan | Pre-event return panel extending 60 trading days before each event |
| Low-lookahead-risk cut | Computed | Uses `before_open` and `weekend_or_holiday` timing buckets from upload timestamp |
| Pre-trend test: mean and t on AR_-20_-1 (must be ~0 under no-pre-leak) | Plan | Computed in `08_momentum_decomposition_results.csv` (column `pre_event_abnormal_return_20_1`) |
| Newey-West SE (lag 5) | Plan | Daily AR panel; `statsmodels.regression.linear_model.OLS.fit(cov_type="HAC", cov_kwds=dict(maxlags=5))` |
| Cluster-robust SE by ticker | Computed for Model 2/5 | See `07_momentum_decomposition_analysis.md` |
| Cluster-robust SE by creator | Computed for Model 2/5 | See `07_momentum_decomposition_analysis.md` |
| Cluster-robust SE by event date | Plan | Same with `groups=df["effective_trading_event_date"]` |
| Two-way clustering (ticker x event date) | Plan | `linearmodels.PanelOLS` or hand-implemented Cameron-Gelbach-Miller |
| Benjamini-Hochberg FDR across subsample cuts | Computed | See "Multiple-Testing Adjustment" above |
| News-confounded-excluded cut | Plan | After news_overlap_flags.csv is populated |
| Momentum-controlled cut | Plan | Residualize AR_0_5 on AR_-20_-1 before re-testing |

## Notes

- p-values reported here use a normal approximation. For the headline sample
  size (n~1,500) the deviation from a t distribution is < 0.001 in p; final
  paper tables should still report exact t p-values via `scipy.stats`.
- The duplicate-collapsed cut deliberately keeps the first event per
  `(creator, ticker, weekday_adjusted_date)` cluster; alternative collapsing
  rules (mean within cluster, max-quality within cluster) should be reported as
  sensitivity rows in the final paper.
- The non-top-ticker cut removes more than half of the sample by construction
  and is the most demanding placebo of the "headline is just NVDA + TSLA"
  hypothesis.
