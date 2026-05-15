# Apify token rotation audit

Generated UTC: `2026-05-15T22:46:08Z`

- Probe rows in `75`: `12`
- Provider probe slot distribution: `{"unknown": 12}`
- Provider probe decisions: `{"START_FAILED_CREDIT": 12}`
- `66` visible slots: `["1", "10", "11", "2", "3", "4", "5", "6", "7", "8", "9"]`
- `66` available_for_actor_runs slots: `["1", "10", "11", "2", "3", "4", "5", "6", "7", "8", "9"]`
- YouTube ledger key labels observed: `["apify_main"]`
- YouTube ledger 403/limit rows: `24`
- `77` final stop reason: `STOP_NO_PROVIDER_PASSED_CANARY`

## Interpretation

- Were all slots tested in provider probe? `no_or_not_provable`
- Probe currently cannot prove slot coverage when `token_slot_number` is `unknown` for all rows.
- Runner/probe bug likely: token slot reporting/rotation evidence is insufficient; code patch recommended.
- `STOP_NO_PROVIDER_PASSED_CANARY` was emitted, but slot-level attribution in `75` is incomplete.
