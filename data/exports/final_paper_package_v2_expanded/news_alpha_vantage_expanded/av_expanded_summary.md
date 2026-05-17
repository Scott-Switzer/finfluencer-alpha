# AV Expanded Summary

# Alpha Vantage expanded NEWS_SENTIMENT summary

- Events: 2341
- Query mode: `ticker_chunk`
- Plan rows OK (or resumed/legacy): 21
- Tickers with successful coverage: 4
- Requests attempted this run: 1
- Rate-limited plan rows: 1
- Clean / confounded / unknown (unknown is **not** clean): 98 / 586 / 1657
- Window calendar days: [5, 21, 63]
- Time bounds format: `YYYYMMDDTHHMM` (see `time_from` / `time_to` in request log).
- Legacy bulk metadata imported: True
- No API keys or raw article bodies are written to exports; only truncated titles and counts.

**Interpretation:** Partial public-news control. Unknown coverage must not be coded as clean.
Standard AV free tier is ~25 requests/day; ticker_chunk mode prioritizes non-top names within that budget.
