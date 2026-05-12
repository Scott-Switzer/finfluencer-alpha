# Methodology

## Event source and construction

This study uses YouTube-derived recommendation events constructed from transcript and metadata pipelines. Candidate rows are filtered through deterministic, auditable rules to produce a strict clean event sample. The resulting clean file (`clean_auto_labeled_events.csv`) contains 132 recommendation events used for the prototype event-study stage.

## Validation approach

The current clean sample is rules-filtered rather than hand-labeled to a full gold-standard benchmark. This design favors reproducibility and auditability but may still include classification error relative to fully manual event validation.

## Market data source (prototype)

Market data is currently sourced from yfinance/Yahoo as an interim prototype import, not as a final production-quality research source. The prototype market-data file is used to test matching logic, return calculations, and reporting workflows before Bloomberg replacement.

## Benchmark adjustment

Abnormal return is computed relative to SPY:

- Abnormal return (horizon h) = stock return (h) − SPY return (h)

CAR is computed as the cumulative sum of daily abnormal returns across the chosen horizon.

## Event windows

Returns are evaluated over three post-event windows:

- 1D: immediate next-trading-day association
- 5D: short-run association
- 20D: medium-run association

These windows are intended to distinguish immediate market response from slightly longer adjustment dynamics.

## Ticker mapping and alias handling

Ticker alias handling is included to address symbol changes. In particular, `SQ -> XYZ` is supported to preserve match continuity when the traded symbol changes over time. Event outputs preserve the original event ticker for auditability while allowing mapped market-data tickers for joins.

## Match diagnostics

Event-study diagnostics compare clean events to matched event-study rows and identify unmatched cases with reason labels. In the current run, 132 clean events produce 131 matched rows, with one unmatched event (`event_id=420`, `SQ`) labeled `no ticker data`.

## Statistical reporting

The reporting layer computes means, medians, share-positive metrics, and one-sample t-statistics (with p-values where available) for abnormal returns and CARs at each horizon. Grouped summaries are also produced by creator, ticker, year, recommendation type, and direction.

## Limitations and Bloomberg replacement plan

Because yfinance is a prototype source, all inference claims remain provisional. Before final submission, Bloomberg-formatted market data should replace the yfinance import, and the full validation/event-study/reporting pipeline should be rerun to confirm whether key signs, magnitudes, and significance patterns persist.
