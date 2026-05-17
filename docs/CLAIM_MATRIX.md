# Claim matrix

Use with `final_defense_package/CLAIM_DISCIPLINE_TABLE.md` for allowed vs prohibited paper wording.

## Summary table

| Claim | Status | Confidence |
| --- | --- | --- |
| Broad YouTube alpha | **Rejected** | High |
| Short-window top-5 raw effect | **Supported / mixed** | Medium–high |
| Non-top underperformance | **Supported / mixed** | Medium–high |
| Public-news-clean robustness | **Rejected / diagnostic only** | High |
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
| public-news-clean | rejected / diagnostic only | `news_confound_master/`; current multi_source_clean n = 0 |
| GDELT news-clean | rejected (diagnostic) | `news_gdelt_retry/` |
| factor alpha | mixed | `calendar_time_factor_regressions/` |
| causal effect | rejected | `research_frontier/placebo_matched_controls/` |
| tradable strategy | rejected | `portfolio_execution_realism/` |
| v2 primary sample | supported | `locked_sample_v2/` |
| analyst / narrative relay | supported/mixed | `information_environment/` — FMP/Finnhub preferred; yfinance diagnostic gap-fill; event-time only with dated pre-event rows; grade normalization improves classification only |
| analyst-news-clean | rejected | unknown analyst ≠ clean; unknown news ≠ clean; current yfinance snapshots are diagnostic only; Bloomberg validation remains planned |
| incremental YouTube signal | rejected/weak | `information_environment/incremental_predictive_value/` |

## Rules

1. **Unknown news is never clean.**
2. **Unknown analyst coverage is never clean.**
3. **Current yfinance snapshots are not event-time evidence.**
4. **Improved grade mapping does not establish causality.**
5. **Bloomberg remains the planned higher-quality validation layer.**
6. **Public-news-clean n = 0 in the multi-provider master layer** — do not claim public-news-clean non-top robustness.
7. **504D** — diagnostic only with censoring caveats.
8. Top-5 raw positives are concentration / consensus / attention patterns, not creator skill.
9. Non-top weakness is not automatically public-news-clean.
