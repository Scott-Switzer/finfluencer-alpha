# Preliminary Findings Memo (Professor Review Draft)

## Research Question

- Do locked-sample YouTube stock recommendations show provisional abnormal-return patterns after publication, without making causal claims?

## Method (Current Stage)

- Locked sample framing: 9,992 transcripts and 1,554 accepted recommendation events.
- Event metadata from local recommendation-event table joined to video metadata (creator, publication timestamp).
- Readiness and prototype outcomes based on existing yfinance market-data import and canonical event-study runner.

## What the Data Says Now

- The event sample is concentrated in a subset of creators and large-cap tickers.
- Duplicate clustering exists on creator+ticker+date combinations, so dependence-robust inference will matter.
- Most events appear usable for short windows, with a smaller usable set for longer post-event windows.

## Provisional Caveats and Limitations

- yfinance is interim/prototype-grade and not final licensed market data.
- X is excluded from the main historical sample for final inference under current coverage constraints.
- Current findings are associational and should not be interpreted as causal trading alpha.

## Next Bloomberg Step

- Execute the attached Bloomberg request CSV and rebuild the same tables with licensed data.
- Re-run window estimates and subgroup cuts under the same locked event IDs.
- Add clustering-robust standard errors and sensitivity checks in final paper tables.

## Proposed Charts/Tables

- Events by year, creator (top N), and ticker (top N).
- Window-level abnormal-return summary table (n, mean, median, t-stat, p-value where available).
- Subgroup panels by creator/year/recommendation type.
- Readiness heatmap by window and missingness/problem-ticker category.

## Provisional yfinance Result Snapshot

- 1D abnormal return: n=1516, mean=0.002728, median=0.000773, t=3.251377, p=0.001174.
- 5D abnormal return: n=1503, mean=0.005236, median=0.000422, t=3.195439, p=0.001425.
