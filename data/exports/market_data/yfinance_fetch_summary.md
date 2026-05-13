# yfinance Prototype Market Data Fetch Summary

This is interim Yahoo/yfinance prototype data, not Bloomberg data. Final research results should use Bloomberg where possible.

- Market-data request input: `data/exports/market_data/market_data_request.csv`
- Unique tickers input: `data/exports/market_data/unique_tickers.csv`
- Output CSV: `data/imports/market_data/yfinance_market_data.csv`
- Date range requested: 2019-08-26 to 2026-07-06
- Benchmark: SPY
- Dry run: False
- Requested original security tickers: 20
- Downloaded data security tickers: 20
- Alias mappings applied: 1
- Rows written: 32245
- Missing benchmark values on ticker rows: 0
- Event windows with sparse yfinance coverage warning: 0

## Adjusted Close Handling

`Adj Close` is used when yfinance returns it. If `Adj Close` is unavailable, `Close` is used as a fallback. The downloader calls yfinance with `auto_adjust=False`.

## Downloaded Tickers

- AAPL
- AMC
- AMD
- AMZN
- COIN
- CRM
- DIS
- GOOGL
- HOOD
- META
- MSFT
- NFLX
- NVDA
- PLTR
- PYPL
- ROKU
- SOFI
- XYZ
- TSLA
- UBER

## Alias Mappings Applied

- SQ -> XYZ

## Failed Tickers

- None.

## Provenance Warning

Do not commit raw/interim downloaded market data. Store it under `data/imports/market_data/` and replace it with Bloomberg data before final results.
