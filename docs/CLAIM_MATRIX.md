# Claim matrix

Use with `final_defense_package/CLAIM_DISCIPLINE_TABLE.md` for allowed vs prohibited paper wording.

## Summary table

| Claim | Status | Confidence |
| --- | --- | --- |
| Broad YouTube alpha | **Rejected** | High |
| Short-window top-5 raw effect | **Supported / mixed** | Medium–high |
| Non-top underperformance | **Supported / mixed** | Medium–high |
| Alpha Vantage news-clean robustness | **Partial** | Medium |
| GDELT news-clean robustness | **Rejected** (diagnostic only) | High |
| Beta-estimated / calendar-time factor alpha | **Mixed** | Medium |
| Causal effect | **Rejected** | High |
| Tradable strategy | **Rejected** | High |
| v2 as primary sample | **Supported** | High |
| Creator skill (uniform) | **Not supported** | High |
| 504D long-horizon alpha | **Diagnostic only** | High |
| Analyst / narrative relay mechanism | **Supported / mixed** (exploratory) | Medium |
| YouTube incremental alpha over market baselines | **Rejected / weak** | Medium |

## Detail (evidence pointers)

| claim | status | table / folder |
| --- | --- | --- |
| broad YouTube alpha | rejected | `long_horizon/03_v2_long_horizon_summary_by_spec.csv` |
| short-window top-5 effect | supported/mixed | `long_horizon/04_v2_long_horizon_top5_vs_non_top.csv` |
| non-top underperformance | supported/mixed | `long_horizon/04_v2_long_horizon_top5_vs_non_top.csv`; `market_implied_confounds/` |
| Alpha Vantage news-clean | partial | `news_alpha_vantage_expanded/` |
| GDELT news-clean | rejected (diagnostic) | `news_gdelt_retry/` |
| factor alpha | mixed | `calendar_time_factor_regressions/` |
| causal effect | rejected | `research_frontier/placebo_matched_controls/` |
| tradable strategy | rejected | `portfolio_execution_realism/` |
| v2 primary sample | supported | `locked_sample_v2/` |
| analyst / narrative relay | supported/mixed | `information_environment/` |
| incremental YouTube signal | rejected/weak | `information_environment/incremental_predictive_value/` |

## Rules

1. **Unknown news is never clean.**
2. **Non-top master-clean n = 0** — do not claim public-news-clean non-top robustness.
3. **504D** — diagnostic only with censoring caveats.
