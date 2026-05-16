# Momentum Decomposition Analysis

## Inputs

- Locked sample: 1,554 accepted YouTube recommendation events.
- Market data: local yfinance prices (expanded + base), SPY benchmark.
- Window conventions match `06_event_timeline_methodology.md`.

## Variable Definitions

- `pre_AR_20_1`: SPY-adjusted abnormal return over trading days [-20, -1].
- `pre_AR_5_1`: SPY-adjusted abnormal return over trading days [-5, -1].
- `event_AR_0_1`: SPY-adjusted abnormal return over trading days [0, +1].
- `post_AR_0_5`, `post_AR_5_20`, `post_AR_0_20`: as above for post-event windows.
- `momentum_decile`: decile rank of `pre_AR_20_1` across the sample (1 = most negative).
- `short_momentum_decile`: decile rank of `pre_AR_5_1`.
- `reversal_flag`: True iff sign(`pre_AR_20_1`) != sign(`post_AR_0_5`) and both are non-trivial.
- `continuation_flag`: True iff signs agree and both are non-trivial.

## Models

### Model 1: post_AR_0_5 ~ pre_AR_20_1

- n = 1535, adj R^2 = 0.0069, df = 1533

| Variable | Coefficient | SE | t | p |
| --- | --- | --- | --- | --- |
| Intercept | 0.002850 | 0.001720 | 1.657 | 0.0975 |
| pre_AR_20_1 | 0.043640 | 0.012798 | 3.410 | 0.0006 |

### Model 2: post_AR_0_5 ~ pre_AR_20_1 + pre_AR_5_1 + buy_dummy

- n = 1535, adj R^2 = 0.0126, df = 1531

| Variable | Coefficient | SE | t | p |
| --- | --- | --- | --- | --- |
| Intercept | -0.002720 | 0.003652 | -0.745 | 0.4563 |
| pre_AR_20_1 | 0.015627 | 0.016535 | 0.945 | 0.3446 |
| pre_AR_5_1 | 0.082402 | 0.032018 | 2.574 | 0.0101 |
| buy_dummy | 0.007841 | 0.004128 | 1.899 | 0.0575 |

### Model 3: Model 2 + top-creator FE (top 8, first as reference)

- n = 1535, adj R^2 = 0.0203, df = 1524

| Variable | Coefficient | SE | t | p |
| --- | --- | --- | --- | --- |
| Intercept | -0.003564 | 0.003889 | -0.916 | 0.3594 |
| pre_AR_20_1 | 0.012710 | 0.016800 | 0.757 | 0.4493 |
| pre_AR_5_1 | 0.082583 | 0.031999 | 2.581 | 0.0099 |
| buy_dummy | 0.007637 | 0.004152 | 1.839 | 0.0659 |
| creator[Mark Roussin, CPA] | 0.002888 | 0.005059 | 0.571 | 0.5681 |
| creator[The Investor Channel] | 0.007615 | 0.006477 | 1.176 | 0.2397 |
| creator[Couch Investor] | -0.009386 | 0.006846 | -1.371 | 0.1704 |
| creator[HyperChange] | -0.006402 | 0.008228 | -0.778 | 0.4365 |
| creator[Daniel Pronk] | -0.003071 | 0.008305 | -0.370 | 0.7116 |
| creator[Ticker Symbol: YOU] | -0.004328 | 0.008534 | -0.507 | 0.6120 |
| creator[Financial Education] | 0.031934 | 0.008839 | 3.613 | 0.0003 |

### Model 4: Model 3 + top-ticker FE (top 8, first as reference)

- n = 1535, adj R^2 = 0.0248, df = 1517

| Variable | Coefficient | SE | t | p |
| --- | --- | --- | --- | --- |
| Intercept | -0.008012 | 0.004599 | -1.742 | 0.0815 |
| pre_AR_20_1 | 0.006679 | 0.017145 | 0.390 | 0.6969 |
| pre_AR_5_1 | 0.083604 | 0.032211 | 2.595 | 0.0094 |
| buy_dummy | 0.008131 | 0.004183 | 1.944 | 0.0520 |
| creator[Mark Roussin, CPA] | 0.003776 | 0.005108 | 0.739 | 0.4597 |
| creator[The Investor Channel] | 0.008614 | 0.006501 | 1.325 | 0.1852 |
| creator[Couch Investor] | -0.007431 | 0.006966 | -1.067 | 0.2861 |
| creator[HyperChange] | -0.012233 | 0.008794 | -1.391 | 0.1642 |
| creator[Daniel Pronk] | -0.002762 | 0.008487 | -0.325 | 0.7449 |
| creator[Ticker Symbol: YOU] | -0.005874 | 0.008576 | -0.685 | 0.4934 |
| creator[Financial Education] | 0.027920 | 0.009061 | 3.081 | 0.0021 |
| ticker[TSLA] | 0.011235 | 0.005681 | 1.978 | 0.0480 |
| ticker[AAPL] | 0.005037 | 0.006221 | 0.810 | 0.4182 |
| ticker[AMD] | 0.016439 | 0.006487 | 2.534 | 0.0113 |
| ticker[AMZN] | 0.004752 | 0.006485 | 0.733 | 0.4638 |
| ticker[GOOGL] | 0.008012 | 0.006537 | 1.226 | 0.2203 |
| ticker[MSFT] | -0.007261 | 0.006578 | -1.104 | 0.2697 |
| ticker[META] | -0.003955 | 0.009089 | -0.435 | 0.6635 |

### Model 5: Model 4 + event_quality_score_scaled (news_overlap_flag omitted in this pass; will be added Bloomberg-day)

- n = 1535, adj R^2 = 0.0242, df = 1516

| Variable | Coefficient | SE | t | p |
| --- | --- | --- | --- | --- |
| Intercept | -0.002954 | 0.016229 | -0.182 | 0.8556 |
| pre_AR_20_1 | 0.006566 | 0.017154 | 0.383 | 0.7019 |
| pre_AR_5_1 | 0.083788 | 0.032226 | 2.600 | 0.0093 |
| buy_dummy | 0.008221 | 0.004194 | 1.960 | 0.0500 |
| creator[Mark Roussin, CPA] | 0.003778 | 0.005109 | 0.739 | 0.4596 |
| creator[The Investor Channel] | 0.008428 | 0.006528 | 1.291 | 0.1967 |
| creator[Couch Investor] | -0.007467 | 0.006969 | -1.071 | 0.2840 |
| creator[HyperChange] | -0.012382 | 0.008809 | -1.406 | 0.1598 |
| creator[Daniel Pronk] | -0.002775 | 0.008490 | -0.327 | 0.7438 |
| creator[Ticker Symbol: YOU] | -0.005960 | 0.008583 | -0.694 | 0.4874 |
| creator[Financial Education] | 0.027835 | 0.009067 | 3.070 | 0.0021 |
| ticker[TSLA] | 0.011178 | 0.005685 | 1.966 | 0.0493 |
| ticker[AAPL] | 0.004951 | 0.006229 | 0.795 | 0.4267 |
| ticker[AMD] | 0.016064 | 0.006591 | 2.437 | 0.0148 |
| ticker[AMZN] | 0.004787 | 0.006488 | 0.738 | 0.4607 |
| ticker[GOOGL] | 0.008131 | 0.006549 | 1.242 | 0.2144 |
| ticker[MSFT] | -0.007164 | 0.006586 | -1.088 | 0.2767 |
| ticker[META] | -0.004227 | 0.009130 | -0.463 | 0.6434 |
| event_quality_score_scaled | -0.007538 | 0.023193 | -0.325 | 0.7452 |

## Cluster-Robust SE Diagnostics

Computed with `statsmodels.OLS(...).fit(cov_type="cluster")` for Model 2
and Model 5. These are diagnostic robustness checks on the same expanded
yfinance event panel; they do not address news confounding or factor alphas.

| Model | Cluster | Variable | Coefficient | Cluster SE | t | p | n | clusters |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Model 2 | ticker | pre_AR_20_1 | 0.015627 | 0.053228 | 0.294 | 0.7691 | 1535 | 21 |
| Model 2 | ticker | pre_AR_5_1 | 0.082402 | 0.088840 | 0.928 | 0.3536 | 1535 | 21 |
| Model 2 | ticker | buy_dummy | 0.007841 | 0.006963 | 1.126 | 0.2602 | 1535 | 21 |
| Model 2 | creator | pre_AR_20_1 | 0.015627 | 0.028077 | 0.557 | 0.5778 | 1535 | 35 |
| Model 2 | creator | pre_AR_5_1 | 0.082402 | 0.090145 | 0.914 | 0.3607 | 1535 | 35 |
| Model 2 | creator | buy_dummy | 0.007841 | 0.007774 | 1.009 | 0.3132 | 1535 | 35 |
| Model 5 | ticker | pre_AR_20_1 | 0.006566 | 0.054115 | 0.121 | 0.9034 | 1535 | 21 |
| Model 5 | ticker | pre_AR_5_1 | 0.083788 | 0.085084 | 0.985 | 0.3247 | 1535 | 21 |
| Model 5 | ticker | buy_dummy | 0.008221 | 0.006655 | 1.235 | 0.2167 | 1535 | 21 |
| Model 5 | ticker | event_quality_score_scaled | -0.007538 | 0.016278 | -0.463 | 0.6433 | 1535 | 21 |
| Model 5 | creator | pre_AR_20_1 | 0.006566 | 0.028739 | 0.228 | 0.8193 | 1535 | 35 |
| Model 5 | creator | pre_AR_5_1 | 0.083788 | 0.085960 | 0.975 | 0.3297 | 1535 | 35 |
| Model 5 | creator | buy_dummy | 0.008221 | 0.007840 | 1.049 | 0.2943 | 1535 | 35 |
| Model 5 | creator | event_quality_score_scaled | -0.007538 | 0.022392 | -0.337 | 0.7364 | 1535 | 35 |

## Pre-Event Momentum Decile Diagnostics

| Decile | n | n_post | mean post_AR_0_5 | median post_AR_0_5 | t | p | hit_rate | reversal_prob |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 155 | 154 | -0.013125 | -0.010132 | -1.522 | 0.1281 | 0.4221 | 0.4194 |
| 2 | 155 | 149 | 0.013164 | -0.007802 | 2.139 | 0.0324 | 0.4832 | 0.4645 |
| 3 | 155 | 154 | 0.009759 | 0.002102 | 2.277 | 0.0228 | 0.5325 | 0.5290 |
| 4 | 155 | 154 | 0.005272 | 0.002757 | 1.328 | 0.1840 | 0.5195 | 0.5161 |
| 5 | 154 | 154 | -0.000316 | 0.003733 | -0.089 | 0.9288 | 0.5455 | 0.5455 |
| 6 | 155 | 155 | 0.004221 | -0.003880 | 1.021 | 0.3072 | 0.4387 | 0.5097 |
| 7 | 155 | 155 | -0.006199 | -0.004074 | -1.847 | 0.0647 | 0.4323 | 0.5677 |
| 8 | 155 | 154 | -0.003214 | -0.000432 | -0.718 | 0.4730 | 0.4805 | 0.5161 |
| 9 | 155 | 155 | 0.015661 | 0.008910 | 2.683 | 0.0073 | 0.5806 | 0.4194 |
| 10 | 154 | 151 | 0.004814 | 0.007464 | 0.647 | 0.5177 | 0.5497 | 0.4416 |

## Interpretation Guardrails

- `news_overlap_flag` is omitted from Model 5 because the current news flags
  are protocol placeholders. After Bloomberg or SEC EDGAR news flagging runs,
  Model 5 should include the populated flag and report any coefficient changes.
- Fixed-effect implementation uses top-creator and top-ticker dummies (first level dropped as
  reference). With ~1,500 observations and 14-15 dummies this is well-identified; absorbing
  full FE (35 creators, 23 tickers) is recommended in any future statsmodels rerun.
- p-values use a normal approximation; for n in this range the deviation from a t distribution
  is negligible, but final paper tables should use the statsmodels cluster/HAC covariance
  estimators shown above.
