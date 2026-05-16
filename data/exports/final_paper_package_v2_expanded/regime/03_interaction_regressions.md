# Interaction Regressions

| horizon | coefficient | estimate | standard_error | t_stat | p_value | fixed_effects | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5D | top5 | 0.004569 | 0.007131 | 0.641 | 0.521719 | ticker and event-month | OLS diagnostic, not causal identification |
| 5D | pre_momentum | -0.039034 | 0.017397 | -2.244 | 0.024854 | ticker and event-month | OLS diagnostic, not causal identification |
| 5D | sec_confounded | -0.010293 | 0.002535 | -4.060 | 0.000049 | ticker and event-month | OLS diagnostic, not causal identification |
| 5D | low_lookahead | -0.002638 | 0.002638 | -1.000 | 0.317315 | ticker and event-month | OLS diagnostic, not causal identification |
| 5D | duplicate | 0.001573 | 0.002677 | 0.588 | 0.556792 | ticker and event-month | OLS diagnostic, not causal identification |
| 5D | buy | 0.000798 | 0.002884 | 0.277 | 0.781906 | ticker and event-month | OLS diagnostic, not causal identification |
| 5D | top5_x_pre_momentum | 0.043433 | 0.020790 | 2.089 | 0.036696 | ticker and event-month | OLS diagnostic, not causal identification |
| 21D | top5 | 0.028318 | 0.013848 | 2.045 | 0.040861 | ticker and event-month | OLS diagnostic, not causal identification |
| 21D | pre_momentum | -0.170745 | 0.033784 | -5.054 | 0.000000 | ticker and event-month | OLS diagnostic, not causal identification |
| 21D | sec_confounded | -0.014059 | 0.004923 | -2.856 | 0.004294 | ticker and event-month | OLS diagnostic, not causal identification |
| 21D | low_lookahead | -0.004780 | 0.005122 | -0.933 | 0.350686 | ticker and event-month | OLS diagnostic, not causal identification |
| 21D | duplicate | -0.012000 | 0.005198 | -2.308 | 0.020977 | ticker and event-month | OLS diagnostic, not causal identification |
| 21D | buy | 0.000808 | 0.005600 | 0.144 | 0.885340 | ticker and event-month | OLS diagnostic, not causal identification |
| 21D | top5_x_pre_momentum | 0.207445 | 0.040372 | 5.138 | 0.000000 | ticker and event-month | OLS diagnostic, not causal identification |
| 63D | top5 | 0.084007 | 0.023100 | 3.637 | 0.000276 | ticker and event-month | OLS diagnostic, not causal identification |
| 63D | pre_momentum | 0.042839 | 0.056357 | 0.760 | 0.447165 | ticker and event-month | OLS diagnostic, not causal identification |
| 63D | sec_confounded | 0.017760 | 0.008213 | 2.162 | 0.030583 | ticker and event-month | OLS diagnostic, not causal identification |
| 63D | low_lookahead | -0.000689 | 0.008544 | -0.081 | 0.935698 | ticker and event-month | OLS diagnostic, not causal identification |
| 63D | duplicate | -0.005088 | 0.008672 | -0.587 | 0.557396 | ticker and event-month | OLS diagnostic, not causal identification |
| 63D | buy | 0.009622 | 0.009342 | 1.030 | 0.303020 | ticker and event-month | OLS diagnostic, not causal identification |
| 63D | top5_x_pre_momentum | -0.223739 | 0.067346 | -3.322 | 0.000893 | ticker and event-month | OLS diagnostic, not causal identification |
| 126D | top5 | 0.181023 | 0.031613 | 5.726 | 0.000000 | ticker and event-month | OLS diagnostic, not causal identification |
| 126D | pre_momentum | 0.120922 | 0.077124 | 1.568 | 0.116908 | ticker and event-month | OLS diagnostic, not causal identification |
| 126D | sec_confounded | 0.018950 | 0.011239 | 1.686 | 0.091791 | ticker and event-month | OLS diagnostic, not causal identification |
| 126D | low_lookahead | 0.005454 | 0.011693 | 0.466 | 0.640918 | ticker and event-month | OLS diagnostic, not causal identification |
| 126D | duplicate | 0.002887 | 0.011867 | 0.243 | 0.807758 | ticker and event-month | OLS diagnostic, not causal identification |
| 126D | buy | 0.020194 | 0.012784 | 1.580 | 0.114200 | ticker and event-month | OLS diagnostic, not causal identification |
| 126D | top5_x_pre_momentum | -0.283939 | 0.092164 | -3.081 | 0.002064 | ticker and event-month | OLS diagnostic, not causal identification |
| 252D | top5 | 0.293358 | 0.041753 | 7.026 | 0.000000 | ticker and event-month | OLS diagnostic, not causal identification |
| 252D | pre_momentum | -0.293477 | 0.101862 | -2.881 | 0.003963 | ticker and event-month | OLS diagnostic, not causal identification |
| 252D | sec_confounded | 0.025110 | 0.014844 | 1.692 | 0.090732 | ticker and event-month | OLS diagnostic, not causal identification |
| 252D | low_lookahead | 0.015079 | 0.015444 | 0.976 | 0.328883 | ticker and event-month | OLS diagnostic, not causal identification |
| 252D | duplicate | 0.018649 | 0.015674 | 1.190 | 0.234116 | ticker and event-month | OLS diagnostic, not causal identification |
| 252D | buy | 0.038192 | 0.016885 | 2.262 | 0.023704 | ticker and event-month | OLS diagnostic, not causal identification |
| 252D | top5_x_pre_momentum | -0.131622 | 0.121726 | -1.081 | 0.279565 | ticker and event-month | OLS diagnostic, not causal identification |
