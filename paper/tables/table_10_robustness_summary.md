# Table 10. Robustness and falsification summary

| check                             | value  | interpretation                                              | source                                                                                                                           |
| --------------------------------- | ------ | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Multi-source clean events         | 0      | No public-news-clean return claim is supported.             | data/exports/final_paper_package_v2_expanded/news_confound_master/news_clean_status_return_table.csv                             |
| Non-top market-quiet 21D SPY BHAR | -0.56% | Secondary sensitivity only; market quiet is not news clean. | data/exports/final_paper_package_v2_expanded/market_implied_confounds/returns_by_market_confound_bucket.csv                      |
| Cross-ticker placebo 5D mean diff | 0.19%  | Economically near-zero falsification benchmark.             | data/exports/final_paper_package_v2_expanded/research_frontier/placebo_matched_controls/creator_cross_ticker_placebo_results.csv |
| Label-shuffle placebo, 5D         | 0.91%  | Permutation p=0.0; descriptive heterogeneity check.         | data/exports/final_paper_package_v2_expanded/paper_robustness/placebo_permutation_summary.csv                                    |
| Label-shuffle placebo, 21D        | 3.42%  | Permutation p=0.0; descriptive heterogeneity check.         | data/exports/final_paper_package_v2_expanded/paper_robustness/placebo_permutation_summary.csv                                    |
