# Long-Horizon Inference

| sample | horizon | n | mean_spy_bhar | naive_p | bootstrap_ci_lower | bootstrap_ci_upper | ticker_cluster_mean_p_proxy | creator_cluster_mean_p_proxy | bh_fdr_q | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 5D | 2322 | 0.000635 | 0.619606 | -0.002102 | 0.003552 | 0.166104 | 0.637684 | 0.619606 | cluster columns use cluster-mean proxy inference |
| all | 21D | 2322 | 0.003173 | 0.239438 | -0.002082 | 0.008322 | 0.272199 | 0.963734 | 0.272089 | cluster columns use cluster-mean proxy inference |
| all | 63D | 2322 | 0.042903 | 0.000000 | 0.033582 | 0.052261 | 0.252776 | 0.043424 | 0.000000 | cluster columns use cluster-mean proxy inference |
| all | 126D | 2322 | 0.084560 | 0.000000 | 0.071303 | 0.098130 | 0.298372 | 0.004324 | 0.000000 | cluster columns use cluster-mean proxy inference |
| all | 252D | 2322 | 0.157459 | 0.000000 | 0.139602 | 0.174182 | 0.462976 | 0.000190 | 0.000000 | cluster columns use cluster-mean proxy inference |
| top5 | 5D | 1362 | 0.004406 | 0.013094 | 0.000746 | 0.007955 | 0.080629 | 0.769765 | 0.017229 | cluster columns use cluster-mean proxy inference |
| top5 | 21D | 1362 | 0.017313 | 0.000002 | 0.010437 | 0.024797 | 0.013309 | 0.143767 | 0.000004 | cluster columns use cluster-mean proxy inference |
| top5 | 63D | 1362 | 0.092714 | 0.000000 | 0.078491 | 0.105520 | 0.024226 | 0.000194 | 0.000000 | cluster columns use cluster-mean proxy inference |
| top5 | 126D | 1362 | 0.174241 | 0.000000 | 0.156520 | 0.192642 | 0.036108 | 0.000005 | 0.000000 | cluster columns use cluster-mean proxy inference |
| top5 | 252D | 1362 | 0.291735 | 0.000000 | 0.265452 | 0.320052 | 0.035917 | 0.000000 | 0.000000 | cluster columns use cluster-mean proxy inference |
| non_top | 5D | 960 | -0.004715 | 0.008177 | -0.008578 | -0.001428 | 0.122267 | 0.502189 | 0.011357 | cluster columns use cluster-mean proxy inference |
| non_top | 21D | 960 | -0.016889 | 0.000018 | -0.024528 | -0.009094 | 0.198691 | 0.436543 | 0.000030 | cluster columns use cluster-mean proxy inference |
| non_top | 63D | 960 | -0.027767 | 0.000001 | -0.038430 | -0.016745 | 0.044351 | 0.366434 | 0.000002 | cluster columns use cluster-mean proxy inference |
| non_top | 126D | 960 | -0.042674 | 0.000000 | -0.060044 | -0.025965 | 0.018823 | 0.367440 | 0.000000 | cluster columns use cluster-mean proxy inference |
| non_top | 252D | 960 | -0.033046 | 0.003600 | -0.055238 | -0.009249 | 0.015478 | 0.182197 | 0.005294 | cluster columns use cluster-mean proxy inference |
| buy | 5D | 1808 | 0.001785 | 0.204642 | -0.001234 | 0.004372 | 0.182166 | 0.906052 | 0.243621 | cluster columns use cluster-mean proxy inference |
| buy | 21D | 1808 | 0.006180 | 0.028031 | 0.001263 | 0.011870 | 0.302245 | 0.369707 | 0.035039 | cluster columns use cluster-mean proxy inference |
| buy | 63D | 1808 | 0.045528 | 0.000000 | 0.034826 | 0.056510 | 0.265681 | 0.004258 | 0.000000 | cluster columns use cluster-mean proxy inference |
| buy | 126D | 1808 | 0.088600 | 0.000000 | 0.072354 | 0.105260 | 0.305669 | 0.000189 | 0.000000 | cluster columns use cluster-mean proxy inference |
| buy | 252D | 1808 | 0.166941 | 0.000000 | 0.145702 | 0.191819 | 0.473101 | 0.000008 | 0.000000 | cluster columns use cluster-mean proxy inference |
| sell | 5D | 514 | -0.003409 | 0.252562 | -0.009028 | 0.002660 | 0.217178 | 0.855692 | 0.274524 | cluster columns use cluster-mean proxy inference |
| sell | 21D | 514 | -0.007404 | 0.296817 | -0.021899 | 0.007100 | 0.174383 | 0.950207 | 0.309184 | cluster columns use cluster-mean proxy inference |
| sell | 63D | 514 | 0.033669 | 0.002627 | 0.014716 | 0.055256 | 0.276368 | 0.321639 | 0.004105 | cluster columns use cluster-mean proxy inference |
| sell | 126D | 514 | 0.070348 | 0.000007 | 0.039363 | 0.100151 | 0.375654 | 0.112248 | 0.000013 | cluster columns use cluster-mean proxy inference |
| sell | 252D | 514 | 0.124106 | 0.000000 | 0.086454 | 0.160923 | 0.602632 | 0.025095 | 0.000000 | cluster columns use cluster-mean proxy inference |
