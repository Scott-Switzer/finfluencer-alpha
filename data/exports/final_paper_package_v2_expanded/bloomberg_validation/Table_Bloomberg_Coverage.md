# Bloomberg Coverage

Bloomberg data are used here as an institutional validation and mechanism layer. They do not support causal claims, public-news-clean alpha claims, creator-skill claims, or tradability claims.

## Parsed Field Coverage

| sheet_name | field | frequency | ticker_count | source_observations | valid_observations | valid_value_pct |
| --- | --- | --- | --- | --- | --- | --- |
| BDX_PX_LAST_DAILY | PX_LAST | Per=D | 41 | 82663 | 82345 | 99.62% |
| BDH_VOLUME_LAST_DAILY | VOLUME | Per=D | 42 | 82663 | 80205 | 97.03% |
| BDH_MKTCAP_Daily | CUR_MKT_CAP | Per=D | 42 | 82663 | 80486 | 97.37% |
| BDH_ANALYST_REC_Wkly | EQY_REC_CONS | Per=W | 35 | 13089 | 13035 | 99.59% |
| BDH_TARGET_PRICE_Wkly | BEST_TARGET_PRICE | Per=W | 35 | 13089 | 12856 | 98.22% |
| BDH_EPS_EST_Wkly | BEST_EPS | Per=W | 35 | 15295 | 13966 | 91.31% |
| BDH_SALES_EST_Wkly | BEST_SALES | Per=W | 35 | 15295 | 13963 | 91.29% |
| BDH_IVOL_DAILY | 30DAY_IMPVOL_100.0%MNY_DF | Per=D | 15 | 27942 | 27931 | 99.96% |
| Total_return_index | TOT_RETURN_INDEX_GROSS_DVDS | D | 42 | 85326 | 80241 | 94.04% |
| Daily_total_return | DAY_TO_DAY_TOT_RETURN_GROSS_DVDS | D | 42 | 85326 | 80232 | 94.03% |
| News_heat | NEWS_HEAT_PUB_DAVG | D | 35 | 70569 | 69812 | 98.93% |
| News_sentiment | NEWS_SENTIMENT_DAILY_AVG | D | 35 | 70569 | 66150 | 93.74% |
| bid | PX_BID | D | 38 | 76881 | 71788 | 93.38% |
| ask | PX_ASK | D | 38 | 76881 | 71788 | 93.38% |
| volume_avg_30d | VOLUME_AVG_30D | D | 38 | 76881 | 71528 | 93.04% |
| Short_int | SHORT_INT | W | 35 | 13491 | 6226 | 46.15% |
| short_int_ratio | SHORT_INT_RATIO | W | 35 | 13491 | 6224 | 46.13% |
| Sheet1 | TOT_ANALYST_REC | W | 35 | 13491 | 13035 | 96.62% |

## Event Coverage

| feature | events | covered_events | coverage_pct |
| --- | --- | --- | --- |
| event_px_last | 2341 | 2328 | 99.4% |
| event_volume | 2341 | 2332 | 99.6% |
| event_mkt_cap | 2341 | 2332 | 99.6% |
| event_dollar_volume | 2341 | 2328 | 99.4% |
| event_total_return_available | 2341 | 2328 | 99.4% |
| event_news_heat | 2341 | 2328 | 99.4% |
| event_news_sentiment | 2341 | 2316 | 98.9% |
| event_bid_ask_spread_pct | 2341 | 2328 | 99.4% |
| event_volume_avg_30d | 2341 | 2328 | 99.4% |
| event_short_int | 2341 | 1064 | 45.5% |
| event_short_int_ratio | 2341 | 1064 | 45.5% |
| event_eqy_rec_cons | 2341 | 2326 | 99.4% |
| event_tot_analyst_rec | 2341 | 2326 | 99.4% |
| event_best_target_price | 2341 | 2325 | 99.3% |
| event_best_eps | 2341 | 2332 | 99.6% |
| event_best_sales | 2341 | 2332 | 99.6% |
| analyst_consensus_available | 2341 | 2326 | 99.4% |
| analyst_coverage_count_available | 2341 | 2326 | 99.4% |
| estimates_available | 2341 | 2332 | 99.6% |
| news_proxy_available | 2341 | 2328 | 99.4% |
| liquidity_proxy_available | 2341 | 2328 | 99.4% |
| short_interest_available | 2341 | 1064 | 45.5% |
