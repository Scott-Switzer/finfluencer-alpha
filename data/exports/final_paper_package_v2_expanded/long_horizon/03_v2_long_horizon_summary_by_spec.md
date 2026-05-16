# V2 Long-Horizon Summary by Spec

| specification | horizon | requested_horizon_days | n_events | n_full_window | n_right_censored | mean_raw_return | mean_spy_bhar | t_spy_bhar | p_spy_bhar | median_spy_bhar | win_rate_spy_bhar | mean_spy_car | t_spy_car | p_spy_car | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 1D | 1 | 2322 | 2322 | 0 | 0.001093 | -0.000024 | -0.029 | 0.976636 | 0.000046 | 0.5026 | -0.000024 | -0.029 | 0.976636 | right-censored rows retained and counted |
| all | 2D | 2 | 2322 | 2316 | 6 | 0.002528 | 0.000899 | 0.937 | 0.348900 | -0.000417 | 0.4944 | 0.000901 | 0.945 | 0.344487 | right-censored rows retained and counted |
| all | 3D | 3 | 2322 | 2309 | 13 | 0.002704 | 0.000412 | 0.375 | 0.707547 | -0.000700 | 0.4819 | 0.000378 | 0.345 | 0.729866 | right-censored rows retained and counted |
| all | 5D | 5 | 2322 | 2299 | 23 | 0.004094 | 0.000635 | 0.496 | 0.619606 | -0.001388 | 0.4841 | 0.000715 | 0.560 | 0.575292 | right-censored rows retained and counted |
| all | 10D | 10 | 2322 | 2251 | 71 | 0.008135 | 0.000835 | 0.412 | 0.680133 | -0.002643 | 0.4811 | -0.001182 | -0.508 | 0.611293 | right-censored rows retained and counted |
| all | 21D | 21 | 2322 | 2173 | 149 | 0.016959 | 0.003173 | 1.176 | 0.239438 | -0.001731 | 0.4953 | 0.000230 | 0.076 | 0.939606 | right-censored rows retained and counted |
| all | 42D | 42 | 2322 | 2101 | 221 | 0.053878 | 0.023760 | 6.328 | 0.000000 | 0.000721 | 0.5017 | 0.020398 | 5.747 | 0.000000 | right-censored rows retained and counted |
| all | 63D | 63 | 2322 | 1960 | 362 | 0.090321 | 0.042903 | 8.882 | 0.000000 | 0.009641 | 0.5211 | 0.036747 | 8.402 | 0.000000 | right-censored rows retained and counted |
| all | 126D | 126 | 2322 | 1592 | 730 | 0.176779 | 0.084560 | 11.905 | 0.000000 | 0.032062 | 0.5624 | 0.068399 | 11.007 | 0.000000 | right-censored rows retained and counted |
| all | 252D | 252 | 2322 | 1238 | 1084 | 0.315997 | 0.157459 | 16.032 | 0.000000 | 0.068101 | 0.6016 | 0.127823 | 17.355 | 0.000000 | right-censored rows retained and counted |
| all | 504D | 504 | 2322 | 721 | 1601 | 0.518057 | 0.253685 | 18.272 | 0.000000 | 0.086060 | 0.6219 | 0.183704 | 19.755 | 0.000000 | right-censored rows retained and counted |
| all | end_of_sample |  | 2322 | 2322 | 0 | 0.700227 | 0.344900 | 17.515 | 0.000000 | 0.095527 | 0.6301 | 0.211704 | 19.327 | 0.000000 | right-censored rows retained and counted |
| top5 | 1D | 1 | 1362 | 1362 | 0 | 0.003931 | 0.003050 | 3.263 | 0.001104 | 0.001380 | 0.5352 | 0.003050 | 3.263 | 0.001104 | right-censored rows retained and counted |
| top5 | 2D | 2 | 1362 | 1361 | 1 | 0.006188 | 0.004781 | 3.944 | 0.000080 | 0.000488 | 0.5095 | 0.004732 | 3.934 | 0.000084 | right-censored rows retained and counted |
| top5 | 3D | 3 | 1362 | 1359 | 3 | 0.006925 | 0.004501 | 3.179 | 0.001478 | 0.001507 | 0.5162 | 0.004429 | 3.167 | 0.001539 | right-censored rows retained and counted |
| top5 | 5D | 5 | 1362 | 1356 | 6 | 0.007631 | 0.004406 | 2.481 | 0.013094 | 0.000533 | 0.5081 | 0.004181 | 2.365 | 0.018032 | right-censored rows retained and counted |
| top5 | 10D | 10 | 1362 | 1336 | 26 | 0.018956 | 0.011788 | 4.775 | 0.000002 | 0.002276 | 0.5213 | 0.011489 | 4.806 | 0.000002 | right-censored rows retained and counted |
| top5 | 21D | 21 | 1362 | 1293 | 69 | 0.031435 | 0.017313 | 4.781 | 0.000002 | 0.005992 | 0.5367 | 0.016427 | 4.961 | 0.000001 | right-censored rows retained and counted |
| top5 | 42D | 42 | 1362 | 1257 | 105 | 0.085075 | 0.054929 | 10.264 | 0.000000 | 0.019636 | 0.5705 | 0.051094 | 11.186 | 0.000000 | right-censored rows retained and counted |
| top5 | 63D | 63 | 1362 | 1183 | 179 | 0.140659 | 0.092714 | 13.452 | 0.000000 | 0.044568 | 0.6050 | 0.085150 | 15.300 | 0.000000 | right-censored rows retained and counted |
| top5 | 126D | 126 | 1362 | 1000 | 362 | 0.267753 | 0.174241 | 17.588 | 0.000000 | 0.083105 | 0.6762 | 0.156895 | 21.840 | 0.000000 | right-censored rows retained and counted |
| top5 | 252D | 252 | 1362 | 796 | 566 | 0.455846 | 0.291735 | 21.482 | 0.000000 | 0.130266 | 0.7651 | 0.250958 | 28.122 | 0.000000 | right-censored rows retained and counted |
| top5 | 504D | 504 | 1362 | 471 | 891 | 0.712853 | 0.433119 | 23.001 | 0.000000 | 0.150631 | 0.8164 | 0.348332 | 33.365 | 0.000000 | right-censored rows retained and counted |
| top5 | end_of_sample |  | 1362 | 1362 | 0 | 0.955687 | 0.574310 | 20.505 | 0.000000 | 0.160248 | 0.8576 | 0.407662 | 34.788 | 0.000000 | right-censored rows retained and counted |
| non_top | 1D | 1 | 960 | 960 | 0 | -0.002934 | -0.004384 | -3.113 | 0.001850 | -0.001486 | 0.4562 | -0.004384 | -3.113 | 0.001850 | right-censored rows retained and counted |
| non_top | 2D | 2 | 960 | 955 | 5 | -0.002665 | -0.004607 | -2.984 | 0.002845 | -0.002315 | 0.4729 | -0.004533 | -2.953 | 0.003142 | right-censored rows retained and counted |
| non_top | 3D | 3 | 960 | 950 | 10 | -0.003285 | -0.005388 | -3.121 | 0.001800 | -0.003018 | 0.4333 | -0.005369 | -3.087 | 0.002021 | right-censored rows retained and counted |
| non_top | 5D | 5 | 960 | 943 | 17 | -0.000924 | -0.004715 | -2.645 | 0.008177 | -0.004474 | 0.4500 | -0.004202 | -2.347 | 0.018940 | right-censored rows retained and counted |
| non_top | 10D | 10 | 960 | 915 | 45 | -0.007219 | -0.014706 | -4.378 | 0.000012 | -0.011863 | 0.4240 | -0.019160 | -4.328 | 0.000015 | right-censored rows retained and counted |
| non_top | 21D | 21 | 960 | 880 | 80 | -0.003580 | -0.016889 | -4.295 | 0.000018 | -0.015185 | 0.4365 | -0.022749 | -4.085 | 0.000044 | right-censored rows retained and counted |
| non_top | 42D | 42 | 960 | 844 | 116 | 0.009616 | -0.020461 | -4.423 | 0.000010 | -0.026145 | 0.4042 | -0.023152 | -4.346 | 0.000014 | right-censored rows retained and counted |
| non_top | 63D | 63 | 960 | 777 | 183 | 0.018903 | -0.027767 | -4.904 | 0.000001 | -0.031998 | 0.4021 | -0.031925 | -4.972 | 0.000001 | right-censored rows retained and counted |
| non_top | 126D | 126 | 960 | 592 | 368 | 0.047710 | -0.042674 | -5.140 | 0.000000 | -0.066795 | 0.4010 | -0.057154 | -5.891 | 0.000000 | right-censored rows retained and counted |
| non_top | 252D | 252 | 960 | 442 | 518 | 0.117587 | -0.033046 | -2.911 | 0.003600 | -0.083620 | 0.3698 | -0.046875 | -4.620 | 0.000004 | right-censored rows retained and counted |
| non_top | 504D | 504 | 960 | 250 | 710 | 0.241690 | -0.000886 | -0.051 | 0.959163 | -0.119327 | 0.3458 | -0.049861 | -3.619 | 0.000295 | right-censored rows retained and counted |
| non_top | end_of_sample |  | 960 | 960 | 0 | 0.337793 | 0.019426 | 0.867 | 0.385961 | -0.147461 | 0.3073 | -0.066312 | -3.904 | 0.000094 | right-censored rows retained and counted |
| buy | 1D | 1 | 1808 | 1808 | 0 | 0.002121 | 0.001255 | 1.631 | 0.102800 | -0.000566 | 0.4862 | 0.001255 | 1.631 | 0.102800 | right-censored rows retained and counted |
| buy | 2D | 2 | 1808 | 1803 | 5 | 0.003794 | 0.002356 | 2.471 | 0.013477 | -0.000926 | 0.4862 | 0.002356 | 2.501 | 0.012394 | right-censored rows retained and counted |
| buy | 3D | 3 | 1808 | 1797 | 11 | 0.003817 | 0.001904 | 1.713 | 0.086726 | -0.001143 | 0.4729 | 0.001904 | 1.740 | 0.081946 | right-censored rows retained and counted |
| buy | 5D | 5 | 1808 | 1787 | 21 | 0.004635 | 0.001785 | 1.268 | 0.204642 | -0.001687 | 0.4806 | 0.001653 | 1.185 | 0.235905 | right-censored rows retained and counted |
| buy | 10D | 10 | 1808 | 1748 | 60 | 0.012329 | 0.005402 | 2.666 | 0.007681 | -0.002693 | 0.4834 | 0.004595 | 2.181 | 0.029199 | right-censored rows retained and counted |
| buy | 21D | 21 | 1808 | 1688 | 120 | 0.019761 | 0.006180 | 2.197 | 0.028031 | -0.002172 | 0.4928 | 0.005095 | 1.795 | 0.072688 | right-censored rows retained and counted |
| buy | 42D | 42 | 1808 | 1630 | 178 | 0.053241 | 0.023301 | 5.753 | 0.000000 | -0.002438 | 0.4934 | 0.021163 | 5.743 | 0.000000 | right-censored rows retained and counted |
| buy | 63D | 63 | 1808 | 1531 | 277 | 0.092438 | 0.045528 | 8.549 | 0.000000 | 0.006638 | 0.5160 | 0.040512 | 8.798 | 0.000000 | right-censored rows retained and counted |
| buy | 126D | 126 | 1808 | 1234 | 574 | 0.179659 | 0.088600 | 11.124 | 0.000000 | 0.026710 | 0.5564 | 0.074359 | 11.418 | 0.000000 | right-censored rows retained and counted |
| buy | 252D | 252 | 1808 | 957 | 851 | 0.325429 | 0.166941 | 14.998 | 0.000000 | 0.070183 | 0.6007 | 0.133812 | 16.195 | 0.000000 | right-censored rows retained and counted |
| buy | 504D | 504 | 1808 | 552 | 1256 | 0.524399 | 0.262210 | 16.559 | 0.000000 | 0.083004 | 0.6045 | 0.189621 | 18.550 | 0.000000 | right-censored rows retained and counted |
| buy | end_of_sample |  | 1808 | 1808 | 0 | 0.703101 | 0.350122 | 15.586 | 0.000000 | 0.086103 | 0.6095 | 0.217818 | 18.656 | 0.000000 | right-censored rows retained and counted |
| sell | 1D | 1 | 514 | 514 | 0 | -0.002524 | -0.004520 | -1.876 | 0.060611 | 0.002130 | 0.5603 | -0.004520 | -1.876 | 0.060611 | right-censored rows retained and counted |
| sell | 2D | 2 | 514 | 513 | 1 | -0.001926 | -0.004224 | -1.541 | 0.123306 | 0.002045 | 0.5233 | -0.004217 | -1.539 | 0.123905 | right-censored rows retained and counted |
| sell | 3D | 3 | 514 | 512 | 2 | -0.001210 | -0.004835 | -1.584 | 0.113206 | 0.001427 | 0.5136 | -0.004989 | -1.611 | 0.107202 | right-censored rows retained and counted |
| sell | 5D | 5 | 514 | 512 | 2 | 0.002194 | -0.003409 | -1.144 | 0.252562 | -0.000415 | 0.4961 | -0.002584 | -0.853 | 0.393838 | right-censored rows retained and counted |
| sell | 10D | 10 | 514 | 503 | 11 | -0.006618 | -0.015232 | -2.684 | 0.007281 | -0.002531 | 0.4728 | -0.021504 | -2.911 | 0.003600 | right-censored rows retained and counted |
| sell | 21D | 21 | 514 | 485 | 29 | 0.007104 | -0.007404 | -1.043 | 0.296817 | 0.000932 | 0.5039 | -0.016880 | -1.799 | 0.072073 | right-censored rows retained and counted |
| sell | 42D | 42 | 514 | 471 | 43 | 0.056116 | 0.025377 | 2.754 | 0.005892 | 0.008755 | 0.5311 | 0.017708 | 1.874 | 0.060887 | right-censored rows retained and counted |
| sell | 63D | 63 | 514 | 429 | 85 | 0.082873 | 0.033669 | 3.008 | 0.002627 | 0.014003 | 0.5389 | 0.023503 | 2.079 | 0.037661 | right-censored rows retained and counted |
| sell | 126D | 126 | 514 | 358 | 156 | 0.166648 | 0.070348 | 4.498 | 0.000007 | 0.034266 | 0.5837 | 0.047437 | 2.927 | 0.003426 | right-censored rows retained and counted |
| sell | 252D | 252 | 514 | 281 | 233 | 0.282821 | 0.124106 | 5.959 | 0.000000 | 0.058136 | 0.6051 | 0.106758 | 6.599 | 0.000000 | right-censored rows retained and counted |
| sell | 504D | 504 | 514 | 169 | 345 | 0.495750 | 0.223700 | 7.762 | 0.000000 | 0.108892 | 0.6829 | 0.162893 | 7.501 | 0.000000 | right-censored rows retained and counted |
| sell | end_of_sample |  | 514 | 514 | 0 | 0.690117 | 0.326535 | 7.985 | 0.000000 | 0.118470 | 0.7023 | 0.190197 | 6.889 | 0.000000 | right-censored rows retained and counted |
| low_lookahead | 1D | 1 | 796 | 796 | 0 | 0.001260 | 0.000066 | 0.084 | 0.932807 | -0.000636 | 0.4912 | 0.000066 | 0.084 | 0.932807 | right-censored rows retained and counted |
| low_lookahead | 2D | 2 | 796 | 792 | 4 | 0.003848 | 0.001152 | 0.987 | 0.323504 | -0.000454 | 0.4925 | 0.001103 | 0.949 | 0.342831 | right-censored rows retained and counted |
| low_lookahead | 3D | 3 | 796 | 785 | 11 | 0.003827 | 0.000963 | 0.649 | 0.516569 | -0.001775 | 0.4485 | 0.000864 | 0.590 | 0.555061 | right-censored rows retained and counted |
| low_lookahead | 5D | 5 | 796 | 785 | 11 | 0.007416 | 0.001831 | 1.006 | 0.314575 | -0.002456 | 0.4673 | 0.001849 | 1.031 | 0.302354 | right-censored rows retained and counted |
| low_lookahead | 10D | 10 | 796 | 764 | 32 | 0.011506 | 0.003439 | 1.193 | 0.232703 | -0.007389 | 0.4422 | 0.003055 | 1.098 | 0.272357 | right-censored rows retained and counted |
| low_lookahead | 21D | 21 | 796 | 724 | 72 | 0.022164 | 0.006952 | 1.660 | 0.096989 | -0.001110 | 0.4987 | 0.006474 | 1.663 | 0.096373 | right-censored rows retained and counted |
| low_lookahead | 42D | 42 | 796 | 673 | 123 | 0.058758 | 0.025211 | 4.377 | 0.000012 | -0.005434 | 0.4749 | 0.023805 | 4.576 | 0.000005 | right-censored rows retained and counted |
| low_lookahead | 63D | 63 | 796 | 603 | 193 | 0.093378 | 0.044451 | 5.367 | 0.000000 | -0.010755 | 0.4761 | 0.038173 | 5.567 | 0.000000 | right-censored rows retained and counted |
| low_lookahead | 126D | 126 | 796 | 534 | 262 | 0.165661 | 0.078712 | 6.383 | 0.000000 | 0.021617 | 0.5352 | 0.064868 | 7.047 | 0.000000 | right-censored rows retained and counted |
| low_lookahead | 252D | 252 | 796 | 380 | 416 | 0.294995 | 0.143227 | 8.543 | 0.000000 | 0.044718 | 0.5754 | 0.111290 | 9.340 | 0.000000 | right-censored rows retained and counted |
| low_lookahead | 504D | 504 | 796 | 182 | 614 | 0.447393 | 0.209350 | 9.281 | 0.000000 | 0.048991 | 0.5766 | 0.150180 | 10.186 | 0.000000 | right-censored rows retained and counted |
| low_lookahead | end_of_sample |  | 796 | 796 | 0 | 0.618656 | 0.294766 | 9.098 | 0.000000 | 0.041278 | 0.5691 | 0.185689 | 10.867 | 0.000000 | right-censored rows retained and counted |
| duplicate_collapsed | 1D | 1 | 1693 | 1693 | 0 | 0.002153 | 0.001147 | 1.551 | 0.120814 | 0.000282 | 0.5050 | 0.001147 | 1.551 | 0.120814 | right-censored rows retained and counted |
| duplicate_collapsed | 2D | 2 | 1693 | 1689 | 4 | 0.003215 | 0.001600 | 1.700 | 0.089133 | -0.000101 | 0.4973 | 0.001585 | 1.673 | 0.094412 | right-censored rows retained and counted |
| duplicate_collapsed | 3D | 3 | 1693 | 1684 | 9 | 0.003498 | 0.001239 | 1.095 | 0.273590 | -0.000782 | 0.4820 | 0.001170 | 1.026 | 0.305101 | right-censored rows retained and counted |
| duplicate_collapsed | 5D | 5 | 1693 | 1678 | 15 | 0.005382 | 0.001660 | 1.209 | 0.226720 | -0.001179 | 0.4849 | 0.001575 | 1.132 | 0.257650 | right-censored rows retained and counted |
| duplicate_collapsed | 10D | 10 | 1693 | 1639 | 54 | 0.013869 | 0.005922 | 2.949 | 0.003190 | -0.001296 | 0.4914 | 0.005344 | 2.580 | 0.009885 | right-censored rows retained and counted |
| duplicate_collapsed | 21D | 21 | 1693 | 1582 | 111 | 0.024089 | 0.010139 | 3.576 | 0.000349 | 0.001310 | 0.5080 | 0.009059 | 3.228 | 0.001247 | right-censored rows retained and counted |
| duplicate_collapsed | 42D | 42 | 1693 | 1523 | 170 | 0.058483 | 0.028000 | 6.752 | 0.000000 | 0.003899 | 0.5097 | 0.025270 | 6.742 | 0.000000 | right-censored rows retained and counted |
| duplicate_collapsed | 63D | 63 | 1693 | 1420 | 273 | 0.094177 | 0.045971 | 8.654 | 0.000000 | 0.013533 | 0.5363 | 0.041242 | 8.924 | 0.000000 | right-censored rows retained and counted |
