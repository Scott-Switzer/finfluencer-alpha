# X/Twitter Status and Future-Extension Plan

## Current Status

X/Twitter data is **excluded** from the main empirical sample. Reasons:

- Prior historical X collection attempts did not produce a dataset that passed
  strict validation: coverage was sparse, timestamps and author attribution
  were inconsistent across providers, and the resulting events could not be
  joined cleanly to the trading calendar.
- The locked YouTube sample (9,992 transcripts, 1,554 accepted events) is
  large enough to support primary inference; mixing in a small,
  poorly-validated X sample would create attribution risk without commensurate
  power gain.
- The repo's reporting framework already treats X as future/optional; this
  pass continues that posture.

X data is **not merged** with YouTube in any output produced by this pass.

## Required Future Validation Before Inclusion

Any future merge of X with the YouTube sample must pass *every* check below.
Each check must produce an auditable artifact in
`data/exports/research_grade_analysis/` or `data/exports/x_extension/`.

1. **Timestamp validity**
   - Post `created_at` matches X API authoritative timestamp byte-for-byte.
   - Spot-check sample of 50 posts cross-referenced against the live X URL.
   - No more than 1% of posts may have missing or zero-second-precision
     timestamps.

2. **Query reproducibility**
   - Stored `query_string`, `query_run_at`, and `cursor` for every collection
     batch.
   - Re-running the same query window in a fresh batch reproduces the same
     post_id set within +/-5% (tolerance for deletions).

3. **Author identity**
   - Each post is tied to a persistent `author_id` that resolves to the same
     screen name within the collection window.
   - No reliance on screen name as primary key (screen names change).

4. **Ticker/company mapping**
   - Cashtag extraction with a falsepositive denylist identical to the
     YouTube pipeline (`GDP`, `CEO`, etc.).
   - Plain uppercase extraction gated by the same starter universe and
     stock-context proximity rules.

5. **Event-window compatibility**
   - `event_date` is the trading-day-anchored conversion of `created_at`,
     applying the same weekday adjustment and trading-day index alignment as
     `06_event_timeline_methodology.md`.
   - Timing buckets (`before_open`, `during_market`, `after_close`,
     `weekend_or_holiday`) use the same UTC->ET conversion conventions.

6. **Duplicate control**
   - Cluster by `(author_id, ticker, event_date)`.
   - Cluster sizes match the YouTube validator schema.

7. **Raw-data retention**
   - Full raw payloads stored under `data/raw/x/` with cryptographic hashes.
   - Audit table `x_collection_runs` records every batch with start/end
     timestamps, cost, and provider.
   - No raw posts deleted except by manual approval logged in a stash report.

## Conditional Use Cases (Acceptable Once Validated)

- Diagnostic/control sample to test whether YouTube event timing is consistent
  with X attention timing. Reported as a sanity check, not as a primary
  estimand.
- Cross-platform attention spillover: P(X event within 24h | YouTube event)
  conditional on creator linkage. Requires creator-identity bridge file
  (which does not exist yet).
- Headline robustness rerun where the universe is restricted to events with X
  corroboration. Result reported as a robustness row, never as the headline.

## Hard Constraint

Until *every* check above passes a strict validation report (committed to
`data/exports/x_extension/x_validation_report.md` with sign-off date), X
data must not be used in the main empirical sample.
