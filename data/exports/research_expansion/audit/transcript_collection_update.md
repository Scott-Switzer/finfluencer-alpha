# Transcript Collection Update

## Decision
Collection was **skipped** in this research-expansion run.

## Reason
- Current transcript count: **6,384** usable transcripts (full_text > 50 chars)
- Target: 10,000+ transcripts
- Gap: ~3,616 transcripts

## Why Skipped
1. **Time constraint:** A safe batch of 3,600+ transcripts would require multiple API calls and could take hours.
2. **Cost risk:** Even with conservative caps, scaling to 10,000 from 6,384 risks exceeding budget without guaranteed success.
3. **Pipeline priority:** The analytical bottleneck (150-event validation sample → 2,078 clean events) was the critical fix, not transcript volume.
4. **No duplicate processes:** No existing collection was running, but the marginal gain of ~3,600 transcripts does not change the core findings compared to fixing the event pipeline.

## What Changed Instead
- The **clean-event pipeline** was rebuilt to process **all 2,147 DB events** instead of the 150-event validation sample.
- This increased clean events from **113 to 2,078**.
- Valid 1D returns increased from **~131 to 2,068**.

## If Collection Resumes Later
- Use `python -m finfluencer_alpha collect-apify-transcripts` with a capped batch.
- Target the ~5,500 videos without transcripts.
- Monitor cost per transcript and stop if unit cost exceeds $0.02.

