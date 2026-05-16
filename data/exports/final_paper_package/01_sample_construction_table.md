# Sample Construction Table

This table describes the committed locked artifact package, not the expanded
live RunPod DB. The 1,554 event count is manifest-supported. The 8,994
transcript count is a historical locked-package count and remains a sample-lock
limitation because no committed transcript-ID manifest was found.

| Metric | Count | Notes |
| --- | --- | --- |
| Transcripts collected | 8994 | Historical locked-package count; not reconstructible from current RunPod DB |
| Accepted recommendation events | 1554 | Manifest-supported YouTube transcript event panel |
| Creators | 35 | Main sample |
| Tickers | 23 | Main sample |
| Buy recommendations | 1209 | Classifier stance mapped to buy |
| Sell recommendations | 345 | Classifier stance mapped to sell |
| Market-data matched events, 1D | 1549 | Expanded yfinance data |
| Market-data matched events, 5D | 1536 | Expanded yfinance data |
| Low-lookahead events | 514 | before_open or weekend_or_holiday upload buckets |
| Duplicate-collapsed observations | 1117 | First event per creator+ticker+date cluster |
| High-quality A/B events | 922 | Automated event quality score >= 65 |
| Non-top-ticker events | 579 | Excludes NVDA, TSLA, AAPL, AMD, AMZN |

X/Twitter data is excluded from the main empirical sample.
