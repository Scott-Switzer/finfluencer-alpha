# News Confound Master Summary

## Status Counts

| news_clean_status | events |
| --- | --- |
| official_confounded | 1102 |
| unknown_news_coverage | 791 |
| media_confounded | 334 |
| market_implied_confounded | 114 |

## Provider Coverage

| provider | events | success_events | hit_events | unknown_or_not_checked_events | top_statuses |
| --- | --- | --- | --- | --- | --- |
| alpha_vantage_news | 2341 | 684 | 586 | 1657 | unknown_or_limited:1657; ok:684 |
| gdelt_news | 2341 | 14 | 14 | 2327 | nan:2291; http_429:34; ok:14; json_parse_failed:2 |
| fnspid_news | 2341 | 2341 | 1 | 0 | ok:2341 |
| fmp_news | 2341 | 0 | 0 | 2341 | not_checked:2341 |
| finnhub_news | 2341 | 0 | 0 | 2341 | not_checked:2341 |
| marketaux_news | 2341 | 0 | 0 | 2341 | not_checked:2341 |
| eodhd_news | 2341 | 0 | 0 | 2341 | not_checked:2341 |
| newsapi_news | 2341 | 0 | 0 | 2341 | not_checked:2341 |
| massive_news | 2341 | 0 | 0 | 2341 | not_checked:2341 |
| alpaca_news | 2341 | 0 | 0 | 2341 | not_checked:2341 |
| fmp_press_release | 2341 | 0 | 0 | 2341 | not_checked:2341 |
| fmp_press_release | 2341 | 0 | 0 | 2341 | not_checked:2341 |

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
| full_sample | media_confounded | 5D | spy_bhar | True | 334 | 0.006992 | 0.000843 | 2.806 | 0.005012 | 0.006627 |  |
| full_sample | media_confounded | 21D | spy_bhar | True | 334 | 0.023644 | 0.009554 | 4.004 | 0.000062 | 0.023092 |  |
| full_sample | media_confounded | 63D | spy_bhar | True | 334 | 0.049508 | 0.039697 | 4.685 | 0.000003 | 0.049141 |  |
| full_sample | market_implied_confounded | 5D | spy_bhar | True | 114 | 0.047203 | 0.034293 | 6.955 | 0.000000 | 0.046834 |  |
| full_sample | market_implied_confounded | 21D | spy_bhar | True | 114 | 0.082750 | 0.012107 | 4.423 | 0.000010 | 0.082722 |  |
| full_sample | market_implied_confounded | 63D | spy_bhar | True | 114 | 0.147841 | 0.120165 | 6.475 | 0.000000 | 0.144973 |  |
| full_sample | multi_source_clean | 5D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| full_sample | multi_source_clean | 21D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| full_sample | multi_source_clean | 63D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| full_sample | unknown_news_coverage | 5D | spy_bhar | True | 777 | -0.000546 | -0.001325 | -0.316 | 0.751936 | -0.000711 |  |
| full_sample | unknown_news_coverage | 21D | spy_bhar | True | 777 | -0.004542 | 0.000632 | -1.227 | 0.219692 | -0.005725 |  |
| full_sample | unknown_news_coverage | 63D | spy_bhar | True | 777 | 0.015495 | -0.013163 | 2.150 | 0.031559 | 0.014661 |  |
| top5 | official_confounded | 5D | spy_bhar | True | 663 | 0.002621 | -0.000296 | 0.938 | 0.348282 | 0.002806 |  |
| top5 | official_confounded | 21D | spy_bhar | True | 663 | 0.015319 | 0.003907 | 3.077 | 0.002091 | 0.015522 |  |
| top5 | official_confounded | 63D | spy_bhar | True | 663 | 0.111347 | 0.058211 | 10.372 | 0.000000 | 0.110807 |  |
| top5 | media_confounded | 5D | spy_bhar | True | 329 | 0.006392 | 0.000598 | 2.578 | 0.009944 | 0.006005 |  |
| top5 | media_confounded | 21D | spy_bhar | True | 329 | 0.023022 | 0.008711 | 3.863 | 0.000112 | 0.022458 |  |
| top5 | media_confounded | 63D | spy_bhar | True | 329 | 0.050880 | 0.039838 | 4.755 | 0.000002 | 0.050489 |  |
| top5 | market_implied_confounded | 5D | spy_bhar | True | 70 | 0.061042 | 0.076425 | 6.653 | 0.000000 | 0.060894 |  |
| top5 | market_implied_confounded | 21D | spy_bhar | True | 70 | 0.130068 | 0.087231 | 4.608 | 0.000004 | 0.130068 |  |
| top5 | market_implied_confounded | 63D | spy_bhar | True | 70 | 0.234617 | 0.224268 | 7.867 | 0.000000 | 0.231358 |  |
| top5 | multi_source_clean | 5D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| top5 | multi_source_clean | 21D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| top5 | multi_source_clean | 63D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| top5 | unknown_news_coverage | 5D | spy_bhar | True | 300 | -0.007043 | -0.003326 | -2.030 | 0.042363 | -0.007268 |  |
| top5 | unknown_news_coverage | 21D | spy_bhar | True | 300 | -0.010849 | 0.004337 | -1.514 | 0.130061 | -0.011238 |  |
| top5 | unknown_news_coverage | 63D | spy_bhar | True | 300 | 0.064304 | 0.013125 | 4.495 | 0.000007 | 0.061302 |  |
