# Market Implied Confound Summary

# Market-implied confound screen

**Not public-news-clean.** This layer flags pre-event market activity using return/volume z-scores.

| Flag | N events |
| --- | --- |
| market_quiet | 1679 |
| market_active_pre_event | 436 |
| unknown_news_market_quiet | 1197 |
| unknown_news_market_active | 284 |

Use `non_top_market_quiet` return slices as a **sensitivity** check only. Unknown news remains **not clean**.
