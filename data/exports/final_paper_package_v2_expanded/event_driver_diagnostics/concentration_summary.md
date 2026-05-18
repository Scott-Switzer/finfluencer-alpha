# Concentration diagnostics

Sample: **2322** events with computed **5D / 21D / 63D** forward SPY BHAR.

## Ticker concentration

- **Top-5 ticker share of events**: 0.609
- Full table: `concentration_by_ticker.csv` (ranks by `n_events`).

## Creator concentration

- **Top-5 creator share of events**: 0.632
- Full table: `concentration_by_creator.csv`.

## Notes

- Means are **equal-weighted across events** within each name (not dollar-weighted).
- Use with sensitivity bounds; large names can drive heterogeneity.
- `concentration_diagnostics.csv` lists **summed** SPY BHAR for top-5 names by horizon (legacy-style concentration).
