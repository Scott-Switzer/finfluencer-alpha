# News Confound Master Summary

## Status Counts

| news_clean_status | events |
| --- | --- |
| official_confounded | 1102 |
| unknown_news_coverage | 799 |
| media_confounded | 322 |
| market_implied_confounded | 118 |

## Provider Coverage

| provider | events | success_events | hit_events | unknown_or_not_checked_events | top_statuses |
| --- | --- | --- | --- | --- | --- |
| alpha_vantage_news | 2341 | 684 | 586 | 1657 | unknown_or_limited:1657; ok:684 |
| gdelt_news | 2341 | 14 | 14 | 2327 | nan:2291; http_429:34; ok:14; json_parse_failed:2 |
| fnspid_news | 2341 | 0 | 0 | 2341 | not_checked:2341 |
| fmp_news | 2341 | 0 | 0 | 2341 | not_checked:2261; http_403:80 |
| finnhub_news | 2341 | 60 | 0 | 2281 | not_checked:2280; ok:60; rate_limited:1 |
| marketaux_news | 2341 | 0 | 0 | 2341 | not_checked:2341 |
| eodhd_news | 2341 | 0 | 0 | 2341 | not_checked:2341 |
| newsapi_news | 2341 | 0 | 0 | 2341 | not_checked:2341 |
| fmp_press_release | 2341 | 0 | 0 | 2341 | not_checked:2261; http_403:80 |

## Interpretation

- Multi-source clean events: **0**
- Non-top multi-source clean events: **0**
- Unknown provider coverage is not clean.
- Public-news-clean claims require SEC/earnings/press-release checks plus at least two successful external provider checks.
- Rows outside `multi_source_clean` are diagnostic for return interpretation.

## Return Table Preview

| sample | news_clean_status | horizon | return_type | diagnostic_only_flag | n | mean | median | t_stat | p_value | winsorized_mean | warning_flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full_sample | official_confounded | 5D | spy_bhar | True | 1097 | -0.005304 | -0.005518 | -2.494 | 0.012635 | -0.005154 |  |
| full_sample | official_confounded | 21D | spy_bhar | True | 1097 | -0.005865 | -0.012842 | -1.385 | 0.166048 | -0.004154 |  |
| full_sample | official_confounded | 63D | spy_bhar | True | 1097 | 0.049399 | 0.011179 | 6.323 | 0.000000 | 0.050510 |  |
| full_sample | media_confounded | 5D | spy_bhar | True | 322 | 0.006888 | 0.000427 | 2.743 | 0.006085 | 0.006704 |  |
| full_sample | media_confounded | 21D | spy_bhar | True | 322 | 0.021745 | 0.008711 | 3.651 | 0.000261 | 0.021186 |  |
| full_sample | media_confounded | 63D | spy_bhar | True | 322 | 0.040753 | 0.038172 | 3.928 | 0.000086 | 0.040328 |  |
| full_sample | market_implied_confounded | 5D | spy_bhar | True | 118 | 0.046708 | 0.034293 | 7.088 | 0.000000 | 0.046345 |  |
| full_sample | market_implied_confounded | 21D | spy_bhar | True | 118 | 0.083497 | 0.012107 | 4.591 | 0.000004 | 0.083462 |  |
| full_sample | market_implied_confounded | 63D | spy_bhar | True | 118 | 0.150168 | 0.140421 | 6.780 | 0.000000 | 0.147407 |  |
| full_sample | multi_source_clean | 5D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| full_sample | multi_source_clean | 21D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| full_sample | multi_source_clean | 63D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| full_sample | unknown_news_coverage | 5D | spy_bhar | True | 785 | -0.000557 | -0.001325 | -0.323 | 0.746622 | -0.000727 |  |
| full_sample | unknown_news_coverage | 21D | spy_bhar | True | 785 | -0.003889 | 0.000789 | -1.052 | 0.292695 | -0.005072 |  |
| full_sample | unknown_news_coverage | 63D | spy_bhar | True | 785 | 0.018583 | -0.012624 | 2.554 | 0.010657 | 0.017746 |  |
| top5 | official_confounded | 5D | spy_bhar | True | 663 | 0.002621 | -0.000296 | 0.938 | 0.348282 | 0.002806 |  |
| top5 | official_confounded | 21D | spy_bhar | True | 663 | 0.015319 | 0.003907 | 3.077 | 0.002091 | 0.015522 |  |
| top5 | official_confounded | 63D | spy_bhar | True | 663 | 0.111347 | 0.058211 | 10.372 | 0.000000 | 0.110807 |  |
| top5 | media_confounded | 5D | spy_bhar | True | 317 | 0.006263 | 0.000257 | 2.508 | 0.012135 | 0.006062 |  |
| top5 | media_confounded | 21D | spy_bhar | True | 317 | 0.021069 | 0.008711 | 3.505 | 0.000457 | 0.020492 |  |
| top5 | media_confounded | 63D | spy_bhar | True | 317 | 0.042038 | 0.038172 | 3.999 | 0.000064 | 0.041588 |  |
| top5 | market_implied_confounded | 5D | spy_bhar | True | 74 | 0.059506 | 0.076193 | 6.789 | 0.000000 | 0.059358 |  |
| top5 | market_implied_confounded | 21D | spy_bhar | True | 74 | 0.128702 | 0.087231 | 4.785 | 0.000002 | 0.128702 |  |
| top5 | market_implied_confounded | 63D | spy_bhar | True | 74 | 0.233637 | 0.224268 | 8.245 | 0.000000 | 0.230376 |  |
| top5 | multi_source_clean | 5D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| top5 | multi_source_clean | 21D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| top5 | multi_source_clean | 63D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| top5 | unknown_news_coverage | 5D | spy_bhar | True | 308 | -0.006902 | -0.003326 | -2.014 | 0.043974 | -0.007127 |  |
| top5 | unknown_news_coverage | 21D | spy_bhar | True | 308 | -0.009021 | 0.004343 | -1.271 | 0.203701 | -0.009401 |  |
| top5 | unknown_news_coverage | 63D | spy_bhar | True | 308 | 0.070905 | 0.014112 | 4.950 | 0.000001 | 0.067903 |  |
