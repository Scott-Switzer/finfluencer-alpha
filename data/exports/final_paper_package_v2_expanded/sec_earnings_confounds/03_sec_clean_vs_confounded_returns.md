# SEC Clean Vs Confounded Returns

| sample | horizon | return_type | n | mean | mean_pct | standard_error | median | t_stat | p_value | win_rate | right_censored |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sec_clean_expanded | 5D | spy_bhar | 1234 | 0.005821 | 0.582% | 0.001477 | 0.000625 | 3.941 | 0.000081 | 0.513776 | 5 |
| sec_clean_expanded | 21D | spy_bhar | 1234 | 0.011129 | 1.113% | 0.003397 | 0.004337 | 3.276 | 0.001053 | 0.525932 | 33 |
| sec_clean_expanded | 63D | spy_bhar | 1234 | 0.037525 | 3.752% | 0.005873 | 0.007977 | 6.390 | 0.000000 | 0.521070 | 159 |
| sec_clean_expanded | 126D | spy_bhar | 1234 | 0.076740 | 7.674% | 0.009412 | 0.016838 | 8.153 | 0.000000 | 0.537277 | 361 |
| sec_clean_expanded | 252D | spy_bhar | 1234 | 0.145735 | 14.574% | 0.012592 | 0.077144 | 11.573 | 0.000000 | 0.608590 | 568 |
| sec_confounded_expanded | 5D | spy_bhar | 1088 | -0.005247 | -0.525% | 0.002142 | -0.005534 | -2.449 | 0.014319 | 0.450368 | 18 |
| sec_confounded_expanded | 21D | spy_bhar | 1088 | -0.005850 | -0.585% | 0.004262 | -0.012813 | -1.373 | 0.169807 | 0.460478 | 116 |
| sec_confounded_expanded | 63D | spy_bhar | 1088 | 0.049002 | 4.900% | 0.007867 | 0.010947 | 6.229 | 0.000000 | 0.521140 | 203 |
| sec_confounded_expanded | 126D | spy_bhar | 1088 | 0.093429 | 9.343% | 0.010760 | 0.046767 | 8.683 | 0.000000 | 0.590993 | 369 |
| sec_confounded_expanded | 252D | spy_bhar | 1088 | 0.170755 | 17.076% | 0.015339 | 0.056951 | 11.132 | 0.000000 | 0.593750 | 516 |
