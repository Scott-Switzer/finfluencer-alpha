# V2 SEC-Clean Event Study

| specification | n_1d | mean_1d_ar | t_1d | p_1d | n_5d | mean_5d_ar | t_5d | p_5d | median_5d_ar | win_rate_5d | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v2 all | 2322 | -0.000024 | -0.029 | 0.976636 | 2299 | 0.000556 | 0.431 | 0.666561 | -0.001417 | 0.482819 | all accepted/extracted events |
| v2 SEC-clean | 1328 | 0.000991 | 1.714 | 0.086593 | 1323 | 0.004144 | 2.823 | 0.004755 | 0.000421 | 0.510960 | full v2 SEC submissions metadata refresh |
| v2 SEC-confounded | 994 | -0.001379 | -0.807 | 0.419910 | 976 | -0.004309 | -1.884 | 0.059526 | -0.006216 | 0.444672 | material SEC filing within +/-5 calendar days |
| v2 SEC-clean top-5 | 776 | 0.001733 | 2.044 | 0.040924 | 774 | 0.003146 | 1.459 | 0.144628 | 0.000421 | 0.510336 |  |
| v2 SEC-clean non-top | 552 | -0.000052 | -0.073 | 0.942167 | 549 | 0.005551 | 3.070 | 0.002143 | 0.000651 | 0.511840 |  |
| v2 low-lookahead + SEC-clean | 484 | -0.000016 | -0.018 | 0.985387 | 481 | 0.009919 | 4.425 | 0.000010 | 0.000421 | 0.513514 |  |
| v2 duplicate-collapsed + SEC-clean | 1000 | 0.001076 | 1.656 | 0.097719 | 996 | 0.005319 | 3.460 | 0.000540 | 0.001114 | 0.516064 |  |

SEC flags use compact company submissions metadata only; no filing bodies are downloaded.
