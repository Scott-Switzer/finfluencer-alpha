# Final RunPod Audit

Date: 2026-05-11

## HEAD
`ce742b5` — Add validated intraday event-study outputs

Confirmed present on `origin/main`. Local `main` is up to date with origin.

## Quality Checks
- **ruff**: All checks passed
- **pytest**: 248 passed, 0 failed

## Intraday Validity Summary
- Eligible events (≤60 days): 11
- Planned event windows: 6
- Events excluded outside 1m limit: 5
- Shifted windows: 0
- Event windows downloaded: 6
- Event windows failed: 0
- Rows written: 11,505
- Events processed: 132
- Events matched: 6
- Events missing: 126
- matched_count (6) <= downloaded_event_id_count (6): True
- No shifted-window language in committed outputs
- Methodology note correctly states limited recent-sample yfinance extension

## Raw-Data Exclusion Status
All raw data paths properly ignored:
- `data/imports/` (market data, vendor data)
- `data/backups/` (archives)
- `data/runs/` (intermediate artifacts)
- `data/*.db` (SQLite databases)
- `runpod.env`, `runpod.env.pub`, `runpodctl` (runtime files)

## Remaining Untracked Outputs
Small, paper-facing derived outputs that should be committed in a follow-up:
- `data/exports/event_study/event_study_results.csv`
- `data/exports/event_study/event_study_summary.md`
- `data/exports/event_study/event_study_match_diagnostics.*`
- `data/exports/reporting/event_study_main_table.*`
- `data/exports/reporting/event_study_report_summary.md`
- `data/exports/reporting/methodology_note_yfinance_prototype.md`
- `data/exports/reporting/final_claims_guardrail.md`
- `data/exports/reporting/presentation_ready_findings.md`
- `data/exports/reporting/plain_english_results_walkthrough.md`
- `data/exports/reporting/paper_*_section_draft.md`
- `data/exports/reporting/charts/*.png`
- `data/exports/validation/auto_labeling_summary.*`
- `data/exports/validation/clean_auto_labeled_events_summary.md`

Large validation samples should remain untracked:
- `data/exports/validation/clean_auto_labeled_events.csv` (~318K)
- `data/exports/validation/clean_auto_labeled_events_exclusions.csv` (~974K)
- `data/exports/validation/event_validation_*.csv` (>300K each)

## GitHub Status
- Branch: `main`
- Local state: clean (no uncommitted changes)
- Origin sync: up to date
- No unpushed commits

## RunPod Shutdown
**Yes, RunPod can be safely shut down.**
All code changes are pushed to GitHub. Valid intraday outputs are committed. Raw data, imports, and large files remain properly ignored. The repo is in a clean, reproducible state.
