# Final Data Section

## Sample Construction
The primary dataset consists of **8,994** unique English-language transcripts collected from 35 financial influencers on YouTube. We employ a multi-stage classification pipeline to identify **1,554** distinct recommendation events. Each event is supported by transcript-level evidence windows that confirm both the ticker and the directional stance (bullish or bearish).

## Market Data
Abnormal returns are computed using local daily adjusted closing prices from yfinance, which serves as our free-data prototype. Returns are benchmarked against the SPY ETF. For a subset of recent events (n=1224), intraday data is used to provide diagnostic "first-hour" reactions, although full-sample intraday analysis is limited by the historical availability of free high-frequency data.

## SEC Metadata
We integrate official SEC EDGAR filing data to identify potential corporate news confounds. We successfully queried 23 unique tickers, mapping them to their respective CIKs to flag events occurring within ±5 days of a material filing (8-K, 10-Q, 10-K, etc.). 

## Limitations
We explicitly state that Bloomberg data was not used in the current empirical build. Bloomberg is treated as a future manual-CSV validation layer for total-return price replacement and comprehensive non-SEC news controls (e.g., analyst upgrades, press releases).
