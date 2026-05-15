# Collection Lock Rationale

## Decision

No additional Apify collection/recovery jobs should be run under current conditions. The project should move to analysis.

## Evidence

- Probe pass is **not** equivalent to recovery success.
- `11` provider-token pairs passed probe checks.
- All `11` failed controlled recovery attempts.
- Controlled recovery imported `0` transcripts.
- Controlled recovery gained `0` accepted recommendation events.
- Locked state remains:
  - transcripts: `9,992`
  - accepted recommendation events: `1,554`

## Implication

Further Apify collection is not worth continuing unless there is:

- new paid/rental access capacity, or
- a truly new provider path not already tested.

Until then, effort should focus on downstream research analysis using the locked dataset.
