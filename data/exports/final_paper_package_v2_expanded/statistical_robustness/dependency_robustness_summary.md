# Dependency Robustness Summary

Block bootstrap rows: 12 (includes `event_month` clustering).

FDR-adjusted one-sample rows: 105

21D and 63D event windows overlap in calendar time. Treat naive p-values as descriptive unless dependency-aware rows point the same way. Ticker, calendar-month, event-week, and creator clustered bootstrap resamples are included where feasible.

Mirrored tables: `clustered_or_block_bootstrap_summary.csv` and `clustered_inference_summary.csv`.
