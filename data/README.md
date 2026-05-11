# Data Directory Policy

This directory contains both tracked and ignored files. The policy is designed to keep the repository small while preserving reproducibility-critical derived outputs.

## Tracked (committed to Git)

Small, cleaned, derived research outputs that are reproducibility-critical:

- `data/exports/validation/` — clean event labels, validation samples, auto-labeling summaries
- `data/exports/event_study/` — event-study results, diagnostics, summaries
- `data/exports/reporting/` — reporting tables, charts, methodology notes
- `data/exports/intraday/` — intraday feasibility scans, event-study outputs, summaries
- `data/exports/x_extension/` — X extension cost plans, candidate queries

These files are typically small (< 1 MB each) and represent the final derived state of the pipeline. They should be regenerated when upstream data or code changes.

## Ignored (not committed)

- **Raw imports** (`data/imports/`, `data/raw/`) — vendor data, paid data, yfinance prototype downloads
- **Databases** (`data/*.db`, `*.sqlite`, `*.sqlite3`) — local SQLite working copies
- **Backups** (`data/backups/`, `*.tar.gz`, `*.db.gz`) — archives and snapshots
- **Large/generated batches** (`data/interim/`, `data/processed/`, `data/runs/`) — intermediate pipeline artifacts
- **Raw transcript dumps** — full transcript text that should not be redistributed
- **Market data** (`data/imports/market_data/yfinance_*.csv`) — replaceable prototype market data
- **Secrets** (`.env`, `.env.*`) — API keys and credentials

## Final Inference

All event-study and reporting outputs should be rerun with Bloomberg-grade market data when available. The yfinance-derived outputs in this repository are interim prototypes and should be treated as lower-grade than Bloomberg-validated results.
