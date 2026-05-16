# Intraday Coverage Report

- Candidate events within last 60 days: `153`
- Events with yfinance 60m rows available: `153`
- Reaction rows computed: `1224`

This is a recent-event diagnostic only. yfinance intraday coverage does not support the full 2018-2026 locked sample. The current implementation uses 60-minute bars, so sub-hour windows are coarse and may collapse to the same observed bar.
