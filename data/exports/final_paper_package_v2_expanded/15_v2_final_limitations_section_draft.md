# V2 Final Limitations Section Draft

The v2 rebuild validates a larger primary candidate sample, but several limits
remain. First, v2 return coverage is not complete: 2299 of
2341 events have 5-day return windows. Missing coverage is primarily a
market-data availability issue for sparse or unsupported tickers and events too
close to the end of the price file.

Second, the SEC-clean row is only a known-subset join against v1 SEC flags:
713 SEC-clean events have 5-day returns in that partial join. V2
unique events require a separate SEC refresh before SEC-clean can be presented
as a full-sample robustness result.

Third, free-news outputs remain simulated diagnostic scaffolding and are not
used as empirical public-news exclusion evidence. No Bloomberg API or Bloomberg
news data are used.

Fourth, the results are associations around YouTube upload dates. They do not
establish causality, tradable alpha, or news-confound isolation.
