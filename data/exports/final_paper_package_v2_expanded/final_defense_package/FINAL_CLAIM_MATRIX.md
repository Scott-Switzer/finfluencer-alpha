# Final claim matrix

| claim | status | strongest_evidence | weakest_evidence | exact_caveat | paper_wording_allowed | paper_wording_prohibited | table_figure_to_cite | confidence_level |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| broad YouTube alpha | rejected | Full sample 5D SPY-adjusted BHAR is small and insignificant. | Long-horizon drift is broken by matched controls and concentration. | Do not cite long horizons as causal YouTube alpha. | No broad short-window abnormal return in the expanded sample. | YouTube recommendations generate alpha. | long_horizon/03_v2_long_horizon_summary_by_spec.csv | high |
| short-window top-5 effect | supported/mixed | Top-5 5D and 21D returns are positive in v2. | Factor and matched-control diagnostics weaken causal interpretation. | Mega-cap momentum synchronization, not proof of stock-picking skill. | Top-name recommendations are followed by positive abnormal returns. | Top-name recommendations are independently tradable alpha. | long_horizon/04_v2_long_horizon_top5_vs_non_top.csv | medium-high |
| non-top underperformance | supported/mixed | Non-top recommendations are negative through medium horizons. | Very long BHAR windows weaken as coverage changes. | Interpret as underperformance/fade risk, not a shortable strategy. | Recommendations outside top names underperform over medium horizons. | Short all non-top recommendations for profit. | long_horizon/04_v2_long_horizon_top5_vs_non_top.csv | medium-high |
| Alpha Vantage news-clean robustness | partial | Real AV metadata mapped events (probe: 173/511/1657; expanded panel when run: 98/586/1657). | Coverage remains partial and request-budget constrained. | Not a full-sample public-news control. | A partial real-news metadata layer was added and unknown events are not clean. | The results survive complete public-news controls. | news_alpha_vantage_expanded/ | medium |
| GDELT news-clean robustness | rejected for main use | Retry success rate was 0.280. | Provider coverage below 50% threshold. | Diagnostic only. | GDELT was attempted but unreliable for main robustness. | GDELT-clean sample validates the finding. | news_gdelt_retry/ | high |
| beta-estimated factor alpha | mixed | Rolling beta-estimated factor alpha table is now available. | Event-level betas and calendar-time portfolios are still imperfect proxies for a full issuer panel. | Do not overstate factor-model proof. | Factor adjustment weakens broad alpha claims. | Factor models prove causal alpha. | factor_alpha_beta_estimated/;calendar_time_factor_regressions/ | medium |
| causal effect | rejected | Matched controls and placebo diagnostics break event-date treatment story. | No random assignment or credible exogenous shock. | Use falsification/selection framing. | Evidence is consistent with attention and selection, not causal alpha. | YouTube caused these returns. | long_horizon_falsification/ | high |
| tradable strategy | rejected | Execution realism tables show drawdown/concentration/cost constraints are severe. | Top-5 diagnostic trades can look strong before full execution realism. | No investment advice or tradable-alpha claim. | Portfolio diagnostics do not support a robust executable strategy. | This strategy is tradable. | portfolio_execution_realism/ | high |
| v2 as primary sample | supported | v2 uses the complete validated RunPod DB sample of 2,341 accepted recommendation events. | v1 remains a historical benchmark; v2 still has confound limitations. | Use v2 for primary empirical claims and v1 only as historical benchmark. | The expanded v2 sample is the primary empirical sample. | v1 is the current primary sample. | locked_sample_v2/ | high |

Unknown news or SEC states are **not** clean. GDELT is diagnostic. 504D windows are downgrade/diagnostic if thin.


## Research-frontier robustness extensions

| Finding | Status |
| --- | --- |
| Broad short-window alpha | **Rejected** (unchanged) |
| Pre-event momentum / volume selection | **Supported** — recommendations tilt toward prior winners & elevated volume |
| Attention amplification (vol/volatility post-event) | **Supported / diagnostic** — attention proxies rise; alpha not durable |
| Medium-horizon reversal after 5D pop | **Supported / mixed** — stronger fade outside top-5 |
| Creator skill homogeneity | **Rejected** — taxonomy shows momentum-riders & antiskilled-like creators |
| Transcript hype/disclosure gradients | **Diagnostic** — language scores tested on evidence snippets only |
| Placebo date falsification | **Supported** — event-date effects shrink vs shifted same-ticker controls |
| OOS predictability of broad alpha | **Weakened / limited** — time-split models do not support easy exploitation |
| Non-top underperformance predictability | **Mixed** — check predictive_validity_results.csv |
| Public-news-clean non-top robustness | **Unresolved** — non-top master-clean n=0 |
| Tradable strategy | **Rejected** |
| Causal creator skill | **Rejected** |

### Selection excerpt
# Recommendation Selection Summary

# Recommendation selection / momentum chasing

## Key comparisons (event vs same-ticker placebo dates)

| Metric | Event mean | Placebo mean | Event−placebo |
| --- | --- | --- | --- |
| prior_return_21d | 0.0032 | 0.0204 | -0.0171 |
| prior_return_63d | 0.0230 | 0.0455 | -0.0225 |
| prior_abnormal_volume | 0.1159 | 0.0199 | 0.0960 |

## Top-5 vs non-top (events only)

| Metric | Top-5 | Non-top |
| --- | --- | --- |
| prior_return_21d | 0.0192 | -0.0194 |
| prior_return_63d | 0.0639 | -0.0349 |

## Interpretation (conservative)

- Positive pre-event momentum supports **selection into trending names**, not information revelation.
- Top-5 recommendations show stronger prior momentum than non-top names in raw means.
- This **weakens** causal skill claims a

### Attention / reversal / creator excerpts
# Attention Amplification Summary

# Attention amplification

## Post-event patterns (means)

- Post 5D SPY BHAR (all events): **0.0006** if available
- Post 21D SPY BHAR (all events): **0.0013** if available
- Post 5D realized volatility: **0.0247** if available

## Mechanism read

If abnormal volume/volatility rise around events **without** persistent risk-adjusted alpha, the pattern is consiste
# Reversal Overreaction Summary

# Reversal / overreaction

## Design
Events with **positive 5D** abnormal returns are tracked for subsequent **21D/63D** SPY BHAR.

## Headline counts
- Events with 5D pop: **1110**
- Pop then negative 21D: **348**

## Non-top vs top-5 (after 5D pop)
- Non-top mean subsequent 21D BHAR: **0.0326**
- Top-5 mean subsequent 21D BHAR: **0.0651**

## Interpretation
Short
# Creator Skill Taxonomy

# Creator taxonomy (non-causal labels)

Counts: {'noisy_neutral': 15, 'momentum_rider': 14, 'antiskilled_like': 3, 'insufficient_sample': 3}

**Hard rule:** labels are **skill-like** / **antiskilled-like**, never definitive skill.

- **momentum_rider:** positive raw returns concentrated in top-5 / prior momentum.
- **antiskilled_like:** negative medium-horizon returns wit

### Predictive validity excerpt
              target                    model   status  n_train  n_test  accuracy      auc
         positive_5d        majority_baseline computed     1625     697  0.507891      NaN
         positive_5d      logistic_time_split computed     1625     697  0.489240 0.526214
         positive_5d random_forest_time_split computed     1625     697  0.539455 0.528179
        positive_21d        majority_baseline computed     1625     697  0.509326      NaN
        positive_21d      logistic_time_split computed     1625     697  0.545194 0.557244
        positive_21d random_forest_time_split computed     1625     697  0.545194 0.564418
 bottom_quartile_21d        majority_baseline computed     1625     697  0.728838      NaN
 bottom_quartile_21d      logistic_time_split computed     1625     697  0.728838 0.448746
 bottom_quartile_21d random_forest_time_split computed     1625     697  0.727403 0.559326
non_top_underperform        majority_baseline computed     1625     697  0.682927      NaN
non_top_underperform      logistic_time_split computed     1625     697  0.786227 0.872039
non_top_underperform random_forest_time_split computed     1625     697  0.718795 0.872177
