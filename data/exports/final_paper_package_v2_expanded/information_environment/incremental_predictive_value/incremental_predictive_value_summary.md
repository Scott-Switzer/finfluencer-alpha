# Incremental Predictive Value

# Incremental predictive value

Tests whether YouTube/transcript features add signal **over** market and analyst baselines.
**Not a trading strategy.**

## Broad positive 21D (representative AUCs)
| feature_set | target | status | n_train | n_test | accuracy | auc |
| --- | --- | --- | --- | --- | --- | --- |
| market_only | positive_21d_bhar | computed | 1625 | 697 | 0.5064562410329986 | 0.5346923647146034 |
| market_only_time | positive_21d_bhar | computed | 1625 | 697 | 0.5294117647058824 | 0.551231364796969 |
| market_only_creator_out | positive_21d_bhar | computed | 1268 | 1054 | 0.484819734345351 | 0.5147063059948722 |
| market_only_ticker_out | positive_21d_bhar | computed | 907 | 1415 | 0.4318021201413428 | 0.488249266339154 |
| transcript_only | positive_21d_bhar | computed | 1625 | 697 | 0.5007173601147776 | 0.5113870356642781 |
| transcript_only_time | positive_21d_bhar | computed | 1625 | 697 | 0.5150645624103299 | 0.5076188122889385 |
| transcript_only_creator_out | positive_21d_bhar | computed | 1268 | 1054 | 0.5199240986717267 | 0.5211286117592833 |
| transcript_only_ticker_out | positive_21d_bhar | computed | 907 | 1415 | 0.4402826855123675 | 0.503107925158487 |
| market_plus_analyst | positive_21d_bhar | computed | 1625 | 697 | 0.5064562410329986 | 0.5346923647146034 |
| market_plus_analyst_time | positive_21d_bhar | computed | 1625 | 697 | 0.5294117647058824 | 0.551231364796969 |
| market_plus_analyst_creator_out | positive_21d_bhar | computed | 1268 | 1054 | 0.484819734345351 | 0.5147063059948722 |
| market_plus_analyst_ticker_out | positive_21d_bhar | computed | 907 | 1415 | 0.4318021201413428 | 0.488249266339154 |

## Interpretation
- If **transcript_only** ≈ **market_only** AUC → speech mainly repackages public/market signals.
- If transcript adds value only for **non_top_underperform** → language helps flag weak calls, not broad alpha.
- Holdout note: non-top underperformance AUC can be high under random/time but **fail ticker-out** (see holdout module).

Cross-ticker placebo 5D ≈ **+0.19%** (near zero) — finfluencer-specific component economically small.
