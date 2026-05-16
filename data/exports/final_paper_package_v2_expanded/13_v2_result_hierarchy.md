# V2 Result Hierarchy

| level | specification | n_1d | mean_1d_ar | t_1d | p_1d | n_5d | mean_5d_ar | t_5d | p_5d | median_5d_ar | win_rate_5d | notes | evidence_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | v2 all accepted events | 2322 | -0.000024 | -0.029 | 0.976636 | 2299 | 0.000556 | 0.431 | 0.666561 | -0.001417 | 0.482819 | all accepted/extracted live DB events | not_statistically_detectable_5d |
| 2 | v2 low-lookahead | 796 | 0.000066 | 0.084 | 0.932807 | 785 | 0.001880 | 1.022 | 0.306900 | -0.002504 | 0.466242 | before_open and weekend_or_holiday upload buckets | not_statistically_detectable_5d |
| 3 | v2 SEC-clean known subset | 716 | 0.002109 | 2.008 | 0.044670 | 713 | 0.003092 | 1.623 | 0.104494 | 0.001467 | 0.518934 | partial SEC join; 1554 events have v1 SEC flags | not_statistically_detectable_5d |
| 4 | v2 duplicate-collapsed | 1693 | 0.001147 | 1.551 | 0.120814 | 1678 | 0.001620 | 1.172 | 0.241189 | -0.001179 | 0.484505 | first event per creator+ticker+date cluster | not_statistically_detectable_5d |
| 5 | v2 top-5 tickers | 1362 | 0.003050 | 3.263 | 0.001104 | 1356 | 0.004234 | 2.377 | 0.017462 | 0.000421 | 0.506637 |  | statistically_detectable_5d |
| 6 | v2 non-top tickers | 960 | -0.004384 | -3.113 | 0.001850 | 943 | -0.004733 | -2.615 | 0.008921 | -0.004526 | 0.448568 |  | statistically_detectable_5d |
| 7 | v2 buy-only | 1808 | 0.001255 | 1.631 | 0.102800 | 1787 | 0.001712 | 1.206 | 0.227842 | -0.001803 | 0.479015 |  | not_statistically_detectable_5d |
| 8 | v2 sell-only | 514 | -0.004520 | -1.876 | 0.060611 | 512 | -0.003482 | -1.164 | 0.244296 | -0.000415 | 0.496094 |  | not_statistically_detectable_5d |

This hierarchy is keyed to v2, not the historical v1 package.
