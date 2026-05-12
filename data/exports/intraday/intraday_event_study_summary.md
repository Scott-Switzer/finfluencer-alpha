# Intraday Event Study Summary

- Events input: `data/exports/validation/clean_auto_labeled_events.csv`
- Intraday market-data input: `data/imports/market_data/yfinance_intraday_market_data.csv`
- Events processed: 132
- Events matched with intraday windows: 6
- Events missing intraday data: 126
- Results CSV: `data/exports/intraday/intraday_event_study_results.csv`
- By creator CSV: `data/exports/intraday/intraday_event_study_by_creator.csv`
- By ticker CSV: `data/exports/intraday/intraday_event_study_by_ticker.csv`
- Methodology note: `data/exports/intraday/intraday_methodology_note.md`

Intraday extension warning: this uses recent yfinance minute data and is not a replacement for the main daily study.
