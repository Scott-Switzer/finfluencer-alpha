# V2 Long-Horizon News and Alpha Workplan

The existing v2 package is strong for 1D/5D event windows, but that window is
too narrow to distinguish attention pops from durable alpha, medium-term
reversal, or long-run drift. Longer horizons matter because a recommendation
can coincide with short-lived attention, trend-following, or delayed
underperformance.

Long-horizon tests need both CAR and BHAR. CAR tracks summed daily abnormal
returns, while BHAR captures compounded holding-period performance. Calendar-
time portfolios are needed because overlapping event windows can make event-
level inference look stronger than an implementable strategy. Censoring controls
are required because recent events cannot have one- or two-year follow-up.

The largest credibility gap is still real public-news coverage. Simulated
free-news outputs are not evidence. Real provider status must be reported as
clean, confounded, or unknown.

Causality is treated as a falsification problem. The package tests pretrends,
matched controls, placebo dates, event-time decay, and long-run reversals; it
does not claim random assignment.

Priority list:
1. long-horizon return panel
2. long-horizon alpha / BHAR / CAR
3. event-time decay and reversal
4. real public-news provider repair
5. multi-provider compact news flags
6. long-horizon portfolio tests
7. creator/ticker fixed-effect regressions
8. matched controls / placebos at longer horizons
9. final narrative rewrite
