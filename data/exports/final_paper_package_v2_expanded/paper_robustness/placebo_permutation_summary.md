# Placebo / permutation diagnostics

Label shuffles destroy pairing between `top5_flag` and realized returns; large observed gaps vs permutations would suggest mechanical alignment in data.

| placebo_type | horizon_days | observed_top5_minus_nontop | permutation_p_upper_tail | n_events |
| --- | --- | --- | --- | --- |
| label_shuffle_spy_bhar_within_sample | 5D | 0.009121 | 0.0 | 2322 |
| year_stratified_random_draw_per_event | 5D | 0.003954 |  | 2322 |
| label_shuffle_spy_bhar_within_sample | 21D | 0.034202 | 0.0 | 2322 |
| year_stratified_random_draw_per_event | 21D | 0.010842 |  | 2322 |
| label_shuffle_spy_bhar_within_sample | 63D | 0.120482 | 0.0 | 2322 |
| year_stratified_random_draw_per_event | 63D | -0.00454 |  | 2322 |