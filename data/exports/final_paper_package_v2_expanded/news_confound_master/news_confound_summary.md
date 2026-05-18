# News Confound Master Summary

## Status Counts

| news_clean_status | events |
| --- | --- |
| official_confounded | 1102 |
| unknown_news_coverage | 710 |
| media_confounded | 419 |
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
| full_sample | media_confounded | 5D | spy_bhar | True | 419 | -0.001087 | -0.000049 | -0.396 | 0.692463 | -0.001601 |  |
| full_sample | media_confounded | 21D | spy_bhar | True | 419 | 0.016608 | 0.008711 | 2.852 | 0.004339 | 0.016135 |  |
| full_sample | media_confounded | 63D | spy_bhar | True | 419 | 0.068924 | 0.041921 | 5.871 | 0.000000 | 0.068225 |  |
| full_sample | market_implied_confounded | 5D | spy_bhar | True | 110 | 0.049625 | 0.048170 | 7.185 | 0.000000 | 0.049250 |  |
| full_sample | market_implied_confounded | 21D | spy_bhar | True | 110 | 0.082909 | 0.009991 | 4.282 | 0.000019 | 0.082888 |  |
| full_sample | market_implied_confounded | 63D | spy_bhar | True | 110 | 0.137977 | 0.120165 | 6.391 | 0.000000 | 0.138865 |  |
| full_sample | multi_source_clean | 5D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| full_sample | multi_source_clean | 21D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| full_sample | multi_source_clean | 63D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| full_sample | unknown_news_coverage | 5D | spy_bhar | True | 696 | 0.003289 | -0.001179 | 2.107 | 0.035085 | 0.003449 |  |
| full_sample | unknown_news_coverage | 21D | spy_bhar | True | 696 | -0.003271 | 0.000789 | -0.905 | 0.365247 | -0.004013 |  |
| full_sample | unknown_news_coverage | 63D | spy_bhar | True | 696 | 0.001973 | -0.020833 | 0.306 | 0.759810 | -0.000304 |  |
| top5 | official_confounded | 5D | spy_bhar | True | 663 | 0.002621 | -0.000296 | 0.938 | 0.348282 | 0.002806 |  |
| top5 | official_confounded | 21D | spy_bhar | True | 663 | 0.015319 | 0.003907 | 3.077 | 0.002091 | 0.015522 |  |
| top5 | official_confounded | 63D | spy_bhar | True | 663 | 0.111347 | 0.058211 | 10.372 | 0.000000 | 0.110807 |  |
| top5 | media_confounded | 5D | spy_bhar | True | 385 | -0.002318 | -0.000600 | -0.790 | 0.429431 | -0.002878 |  |
| top5 | media_confounded | 21D | spy_bhar | True | 385 | 0.016267 | 0.008444 | 2.596 | 0.009432 | 0.015845 |  |
| top5 | media_confounded | 63D | spy_bhar | True | 385 | 0.071563 | 0.046090 | 5.651 | 0.000000 | 0.070839 |  |
| top5 | market_implied_confounded | 5D | spy_bhar | True | 66 | 0.065918 | 0.079306 | 7.038 | 0.000000 | 0.065770 |  |
| top5 | market_implied_confounded | 21D | spy_bhar | True | 66 | 0.133200 | 0.101781 | 4.461 | 0.000008 | 0.133200 |  |
| top5 | market_implied_confounded | 63D | spy_bhar | True | 66 | 0.223436 | 0.224268 | 8.019 | 0.000000 | 0.224395 |  |
| top5 | multi_source_clean | 5D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| top5 | multi_source_clean | 21D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| top5 | multi_source_clean | 63D | spy_bhar | False | 0 |  |  |  |  |  | n_lt_50 |
| top5 | unknown_news_coverage | 5D | spy_bhar | True | 248 | 0.003246 | -0.000841 | 1.138 | 0.255293 | 0.003214 |  |
| top5 | unknown_news_coverage | 21D | spy_bhar | True | 248 | -0.006571 | 0.007260 | -0.977 | 0.328421 | -0.008127 |  |
| top5 | unknown_news_coverage | 63D | spy_bhar | True | 248 | 0.040949 | 0.008422 | 3.531 | 0.000414 | 0.039197 |  |
