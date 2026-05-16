# Locked Sample Manifests

These manifests make the final-package sample state explicit without exporting transcript text, raw database files, raw API responses, or article bodies.

## What Is Locked

- `01_locked_event_manifest.csv` is the manifest-supported final event sample: **1,554 committed event IDs** from `data/exports/research_grade_analysis/05_event_timeline_dataset.csv`.
- `02_locked_transcript_manifest.csv` is compact current RunPod transcript metadata for **9,992 live DB transcript rows**, with no `full_text` column. It marks which transcript videos support at least one locked final event.
- `03_locked_sample_reconciliation.csv` records live DB counts, locked artifact counts, and reproducibility status.

## Why This Differs From The Current Live DB

The expanded live RunPod database currently has **9,992 transcript rows** and **2,341 recommendation-event rows**. The committed final package uses a historical locked artifact panel with **8,994 transcript count** and **1,554 accepted event IDs**. The event lock is reproducible from committed files; the 8,994 transcript count is not reproducible from the current DB or a committed transcript-id manifest.

## Reproducibility Status

- **1,554 accepted events:** reproducible from committed files. Use `01_locked_event_manifest.csv` as the final event-id manifest.
- **8,994 transcripts:** historical artifact count only. No committed manifest was found that lists those 8,994 transcript video IDs, and the current DB filters inspected do not reproduce the count.
- **9,992 transcripts / 2,341 recommendation events:** expanded live RunPod DB state, not yet reconciled into the final paper sample.

## Paper Citation Guidance

The safest paper wording is: "The final analysis uses a manifest-supported locked artifact sample of 1,554 transcript-supported recommendation events. The associated 8,994 transcript count is a historical locked-package count that remains a sample-lock limitation because the transcript-id manifest is not recoverable from committed files. The expanded live database contains 9,992 transcripts and 2,341 recommendation events and should be treated as a separate future expansion until regenerated end to end."

Do not cite the expanded live DB counts as final paper counts unless the full empirical package is regenerated from an explicit new lock.

## Free-News Scaffold

Free-news outputs are diagnostic scaffolding only. Current source-code audit shows **0 real GDELT queried events** and **1,554 simulated fallback rows**. These outputs are not empirical public-news exclusion evidence and are not a Bloomberg News substitute.

## Future Expanded DB Work

Future work should create a new lock version before rebuilding any final package artifact. That lock should include event IDs, transcript video IDs, source DB hash or export timestamp, and explicit filters. Do not overwrite this locked artifact sample with live DB outputs without changing the sample version and updating the paper language.
