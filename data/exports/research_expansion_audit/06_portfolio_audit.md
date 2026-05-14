# Portfolio Audit

- Entry date: next ticker trading day after the YouTube publish date.
- Exit date: holding-period trading-day offset from entry.
- Overlapping positions are allowed and averaged daily.
- Equal-weight portfolios average active event positions each day.
- Creator-weighted portfolios average within creator first, then across creators.
- Transaction costs: 10 bps at entry and 10 bps at exit.
- No lookahead: all entries occur after the event date using next-trading-day execution.

| Portfolio | Holding | N events | Total return | Sharpe | Alpha vs SPY |
|---|---:|---:|---:|---:|---:|
| equal_weight_all_recommendations | 5D | 465 | -0.7657 | -1.0833 | -0.656857 |
| equal_weight_all_recommendations | 21D | 430 | 0.7754 | 0.4405 | 0.012734 |
| equal_weight_all_recommendations | 63D | 367 | 0.3504 | 0.1998 | -0.055652 |
| equal_weight_all_recommendations | 126D | 277 | 1.7797 | 0.7705 | 0.079165 |
| equal_weight_all_recommendations | 252D | 196 | 1.5232 | 0.6812 | 0.036676 |
| creator_weighted_all_recommendations | 5D | 465 | -0.7551 | -1.0495 | -0.637479 |
| creator_weighted_all_recommendations | 21D | 430 | 1.3079 | 0.6595 | 0.092453 |
| creator_weighted_all_recommendations | 63D | 367 | 0.2477 | 0.148 | -0.044437 |
| creator_weighted_all_recommendations | 126D | 277 | 1.5823 | 0.7074 | 0.093464 |
| creator_weighted_all_recommendations | 252D | 196 | 1.2703 | 0.6016 | 0.047751 |
| buy_only | 5D | 398 | -0.2448 | -0.2913 | -0.266531 |
| buy_only | 21D | 370 | 2.8833 | 1.1019 | 0.135218 |
| buy_only | 63D | 314 | 5.1886 | 1.1236 | 0.218427 |
| buy_only | 126D | 231 | 8.3153 | 1.2066 | 0.237905 |
| buy_only | 252D | 159 | 8.9603 | 1.0676 | 0.18967 |
| sell_inverse_or_short_proxy | 5D | 66 | -0.8490 | -1.3666 | -1.32688 |
| sell_inverse_or_short_proxy | 21D | 59 | -0.9166 | -1.1565 | -0.689754 |
| sell_inverse_or_short_proxy | 63D | 52 | -0.9630 | -1.3216 | -0.471548 |
| sell_inverse_or_short_proxy | 126D | 45 | -0.9611 | -1.0921 | -0.351152 |
| sell_inverse_or_short_proxy | 252D | 36 | -0.9476 | -0.8492 | -0.174154 |
| long_buy_short_sell | 5D | 465 | -0.7657 | -1.0833 | -0.656857 |
| long_buy_short_sell | 21D | 430 | 0.7754 | 0.4405 | 0.012734 |
| long_buy_short_sell | 63D | 367 | 0.3504 | 0.1998 | -0.055652 |
| long_buy_short_sell | 126D | 277 | 1.7797 | 0.7705 | 0.079165 |
| long_buy_short_sell | 252D | 196 | 1.5232 | 0.6812 | 0.036676 |
| price_target_only | 5D | 57 | -0.2805 | -0.7259 | -0.35849 |
| price_target_only | 21D | 54 | 0.7178 | 0.8861 | 0.069104 |
| price_target_only | 63D | 49 | 5.2161 | 1.7829 | 0.556689 |
| price_target_only | 126D | 40 | 8.4143 | 1.5272 | 0.459225 |
| price_target_only | 252D | 18 | 4.0781 | 0.7236 | 0.155697 |
| portfolio_update_only | 5D | 76 | 0.0918 | 0.2495 | -0.246514 |
| portfolio_update_only | 21D | 72 | 0.5511 | 0.5796 | -0.087665 |
| portfolio_update_only | 63D | 60 | 1.0249 | 0.5771 | 0.005893 |
| portfolio_update_only | 126D | 46 | 1.1831 | 0.6062 | 0.00525 |
| portfolio_update_only | 252D | 35 | 1.8110 | 0.8428 | 0.06478 |
