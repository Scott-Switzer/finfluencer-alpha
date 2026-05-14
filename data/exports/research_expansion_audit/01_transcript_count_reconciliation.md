# Transcript Count Reconciliation

- Total videos in current RunPod DB: **11,922**.
- Transcript rows: **9,763** across **9,763** unique videos.
- Successful transcripts: **9,747**.
- Transcripts with `full_text > 50` chars: **9,742**.
- Coverage using successful transcripts: **81.8%**.
- Coverage using `full_text > 50`: **81.7%**.
- Duplicate transcript video IDs: **0**.

## Reconciliation
- The prior 9,747 successful-transcript count is present in the live DB.
- The OpenCode 6,384 count is not present in the current DB. It appears in committed markdown only and reflects a stale pre-collection snapshot or copied report, not the current RunPod database.
- The correct current text-usable count to cite is **9,742** if the paper uses the strict `full_text > 50` filter, or **9,747** if it cites successful transcript retrievals.
- The DB is not stale or partial relative to the OpenCode report; it is more complete.
