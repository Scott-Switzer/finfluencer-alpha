# Incremental Predictive Value

# Incremental predictive value

Tests whether YouTube/transcript features add signal **over** market and analyst baselines.
**Not a trading strategy.**

## Broad positive 21D (representative AUCs)
| feature_set | target | status | n_train | n_test | accuracy | auc |
| --- | --- | --- | --- | --- | --- | --- |
| market_only | positive_21d_bhar | computed | 1056 | 453 | 0.5408388520971302 | 0.521196204014684 |
| market_only_time | positive_21d_bhar | computed | 1056 | 453 | 0.5033112582781457 | 0.5255450255450256 |
| market_only_creator_out | positive_21d_bhar | computed | 875 | 634 | 0.4794952681388013 | 0.5024664906074044 |
| market_only_ticker_out | positive_21d_bhar | computed | 538 | 971 | 0.5066941297631308 | 0.5115546218487395 |
| transcript_only | positive_21d_bhar | computed | 1625 | 697 | 0.5222381635581061 | 0.5284544810660342 |
| transcript_only_time | positive_21d_bhar | computed | 1625 | 697 | 0.48206599713055953 | 0.5189164848965562 |
| transcript_only_creator_out | positive_21d_bhar | computed | 1552 | 770 | 0.45324675324675323 | 0.5132166221696863 |
| transcript_only_ticker_out | positive_21d_bhar | computed | 810 | 1512 | 0.49007936507936506 | 0.5169006195960373 |
| market_plus_analyst | positive_21d_bhar | computed | 1056 | 453 | 0.5320088300220751 | 0.5267905959540733 |
| market_plus_analyst_time | positive_21d_bhar | computed | 1056 | 453 | 0.5143487858719646 | 0.5253987753987754 |
| market_plus_analyst_creator_out | positive_21d_bhar | computed | 875 | 634 | 0.48738170347003157 | 0.5099606358064677 |
| market_plus_analyst_ticker_out | positive_21d_bhar | computed | 538 | 971 | 0.513903192584964 | 0.5242381801205331 |

## Interpretation
- If **transcript_only** ≈ **market_only** AUC → speech mainly repackages public/market signals.
- If transcript adds value only for **non_top_underperform** → language helps flag weak calls, not broad alpha.
- Holdout note: non-top underperformance AUC can be high under random/time but **fail ticker-out** (see holdout module).

Cross-ticker placebo 5D ≈ **+0.19%** (near zero) — finfluencer-specific component economically small.
