# News Confound Master Summary

## Status Counts

| news_clean_status | events |
| --- | --- |
| official_confounded | 1102 |
| unknown_news_coverage | 668 |
| media_confounded | 461 |
| market_implied_confounded | 110 |

## Provider Coverage

| provider | events | success_events | hit_events | unknown_or_not_checked_events | top_statuses |
| --- | --- | --- | --- | --- | --- |
| alpha_vantage_news | 2341 | 684 | 586 | 1657 | unknown_or_limited:1657; ok:684 |
| gdelt_news | 2341 | 14 | 14 | 2327 | nan:2291; http_429:34; ok:14; json_parse_failed:2 |
| fnspid_news | 2341 | 2341 | 340 | 0 | ok:2341 |
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
| full_sample | media_confounded | 5D | spy_bhar | True | 461 | 0.000529 | 0.000257 | 0.198 | 0.842908 | 0.000054 |  |
| full_sample | media_confounded | 21D | spy_bhar | True | 461 | 0.015147 | 0.008711 | 2.709 | 0.006757 | 0.014921 |  |
| full_sample | media_confounded | 63D | spy_bhar | True | 461 | 0.070006 | 0.039961 | 6.348 | 0.000000 | 0.069346 |  |
| full_sample | market_implied_confounded | 5D | spy_bhar | True | 110 | 0.049625 | 0.048170 | 7.185 | 0.000000 | 0.049250 |  |
| full_sample | market_implied_confounded | 21D | spy_bhar | True | 110 | 0.082909 | 0.009991 | 4.282 | 0.000019 | 0.082888 |  |
| full_sample | market_implied_confounded | 63D | spy_bhar | True | 110 | 0.137977 | 0.120165 | 6.391 | 0.000000 | 0.138865 |  |
| full_sample | multi_source_clean | 5D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| full_sample | multi_source_clean | 21D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| full_sample | multi_source_clean | 63D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| full_sample | unknown_news_coverage | 5D | spy_bhar | True | 654 | 0.002431 | -0.001339 | 1.596 | 0.110511 | 0.002551 |  |
| full_sample | unknown_news_coverage | 21D | spy_bhar | True | 654 | -0.003518 | 0.000412 | -0.969 | 0.332518 | -0.003957 |  |
| full_sample | unknown_news_coverage | 63D | spy_bhar | True | 654 | -0.003090 | -0.024567 | -0.473 | 0.636126 | -0.005110 |  |
| top5 | official_confounded | 5D | spy_bhar | True | 663 | 0.002621 | -0.000296 | 0.938 | 0.348282 | 0.002806 |  |
| top5 | official_confounded | 21D | spy_bhar | True | 663 | 0.015319 | 0.003907 | 3.077 | 0.002091 | 0.015522 |  |
| top5 | official_confounded | 63D | spy_bhar | True | 663 | 0.111347 | 0.058211 | 10.372 | 0.000000 | 0.110807 |  |
| top5 | media_confounded | 5D | spy_bhar | True | 427 | -0.000452 | 0.000031 | -0.159 | 0.873408 | -0.000957 |  |
| top5 | media_confounded | 21D | spy_bhar | True | 427 | 0.014724 | 0.008444 | 2.463 | 0.013768 | 0.014606 |  |
| top5 | media_confounded | 63D | spy_bhar | True | 427 | 0.072472 | 0.041921 | 6.138 | 0.000000 | 0.071781 |  |
| top5 | market_implied_confounded | 5D | spy_bhar | True | 66 | 0.065918 | 0.079306 | 7.038 | 0.000000 | 0.065770 |  |
| top5 | market_implied_confounded | 21D | spy_bhar | True | 66 | 0.133200 | 0.101781 | 4.461 | 0.000008 | 0.133200 |  |
| top5 | market_implied_confounded | 63D | spy_bhar | True | 66 | 0.223436 | 0.224268 | 8.019 | 0.000000 | 0.224395 |  |
| top5 | multi_source_clean | 5D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| top5 | multi_source_clean | 21D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| top5 | multi_source_clean | 63D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| top5 | unknown_news_coverage | 5D | spy_bhar | True | 206 | 0.000513 | -0.001339 | 0.189 | 0.849889 | 0.000617 |  |
| top5 | unknown_news_coverage | 21D | spy_bhar | True | 206 | -0.008027 | 0.005748 | -1.143 | 0.252895 | -0.009337 |  |
| top5 | unknown_news_coverage | 63D | spy_bhar | True | 206 | 0.032823 | 0.000086 | 2.644 | 0.008189 | 0.030243 |  |
