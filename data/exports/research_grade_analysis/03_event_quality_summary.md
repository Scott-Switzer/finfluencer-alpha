# Event Quality Score Summary

- Total scored events: `1554`
- Exclusion candidates: `5`
- Mean score: `66.95`
- Median score: `66.00`

## Distribution by Tier

| Tier | Count | Share |
| --- | --- | --- |
| A | 68 | 4.38% |
| B | 854 | 54.95% |
| C | 623 | 40.09% |
| D | 9 | 0.58% |

## Tier Share by Top 10 Creators

| Creator | Total | A | B | C | D |
| --- | --- | --- | --- | --- | --- |
| Jose Najarro Stocks | 287 | 11 | 137 | 136 | 3 |
| Mark Roussin, CPA | 229 | 12 | 130 | 86 | 1 |
| The Investor Channel | 124 | 2 | 62 | 60 | 0 |
| Couch Investor | 116 | 6 | 63 | 47 | 0 |
| HyperChange | 76 | 2 | 42 | 31 | 1 |
| Daniel Pronk | 71 | 3 | 42 | 26 | 0 |
| Ticker Symbol: YOU | 67 | 1 | 35 | 31 | 0 |
| Financial Education | 64 | 0 | 31 | 33 | 0 |
| Value Investing with Sven Carlin, Ph.D. | 51 | 4 | 25 | 22 | 0 |
| Sasha Yanshin | 49 | 3 | 26 | 18 | 2 |

## Tier Share by Top 10 Tickers

| Ticker | Total | A | B | C | D |
| --- | --- | --- | --- | --- | --- |
| NVDA | 280 | 11 | 138 | 131 | 0 |
| TSLA | 244 | 11 | 132 | 98 | 3 |
| AAPL | 157 | 7 | 84 | 66 | 0 |
| AMD | 150 | 0 | 56 | 91 | 3 |
| AMZN | 144 | 7 | 92 | 45 | 0 |
| GOOGL | 137 | 8 | 92 | 37 | 0 |
| MSFT | 135 | 13 | 83 | 39 | 0 |
| META | 68 | 0 | 30 | 38 | 0 |
| PYPL | 47 | 1 | 27 | 19 | 0 |
| SOFI | 43 | 3 | 27 | 13 | 0 |

## Top Reason Codes

| Reason | Count | Meaning |
| --- | --- | --- |
| EVIDENCE_QUOTE_AVAILABLE | 1553 | Evidence window present in transcript event. |
| TICKER_COMPANY_MATCH | 1374 | Ticker and company name both populated. |
| TOP_TICKER_CONCENTRATION | 975 | Ticker is in top-5 by event count. |
| WEAK_DIRECTIONAL_SIGNAL | 876 | Directional language is implicit or weak. |
| TOP_CREATOR_CONCENTRATION | 832 | Creator is in top-5 by event count. |
| DUPLICATE_CLUSTER | 690 | Same creator+ticker+adjusted date as another event. |
| STRONG_DIRECT_LANGUAGE | 678 | Explicit buy/sell phrasing in evidence. |
| CONDITIONALITY_PRESENT | 278 | Conditional language detected ('if', 'might'). |
| TRADING_DAY_ADJUSTED | 226 | Event date adjusted from weekend to next trading day. |
| RECAP_RISK | 203 | Recap/past-call language detected. |
| HIGH_IMPACT_EVENT | 159 | 1D abnormal return in top/bottom 5% of sample. |
| POSITION_DISCLOSURE_OK | 96 | Creator disclosed position context. |
| EXTREME_ABS_AR_5D | 83 | |5D abnormal return| > 15%. |
| AMBIGUOUS_TICKER | 68 | Ticker is on common-word ambiguity watchlist. |
| EXTREME_ABS_AR_1D | 62 | |1D abnormal return| > 10%. |

## Top Validation Flags

| Flag | Count |
| --- | --- |
| top_ticker_concentration | 975 |
| weak_directional_signal | 876 |
| top_creator_concentration | 832 |
| duplicate_cluster_small | 475 |
| conditionality | 278 |
| duplicate_cluster_large | 215 |
| recap_risk | 203 |
| high_impact_event | 159 |
| extreme_abs_ar_5d | 83 |
| ambiguous_ticker | 68 |
| extreme_abs_ar_1d | 62 |
| news_only_risk | 21 |
| market_data_missing | 5 |
| evidence_short | 1 |
