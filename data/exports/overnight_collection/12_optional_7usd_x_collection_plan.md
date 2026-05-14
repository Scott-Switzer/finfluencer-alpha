# Optional $7 X Collection Continuation Plan

Generated: 2026-05-14T16:17:46Z

## Continuation Decision
- Do not run this continuation now.
- Gate status: not approved. The source/classifier audit found material ticker precision and date-coverage issues, so the condition for continuing collection is not met.
- This file records the bounded economics and the conditions that would have to be satisfied before a later manual continuation.

## Current Spend And Estimated Capacity
- Current X spend from `apify_collection_runs`: $17.9563
- Current imported X posts from runs: 6,936
- Current average cost per imported item: $0.0026
- Current configured X/global cap used for planning: $18.0000
- Remaining estimated capacity up to $25 total X spend: $7.0437

## Hypothetical Cap Change If Later Approved
- Proposed hard cap increase would be from about $18.0000 to no more than $25.0000 total X spend.
- No runtime/config value was changed for this audit.
- A future continuation must use a fresh manual checkpoint and a short continuation command, not the full overnight runner.

## Expected Continuation Yield At Current Rate
- Expected additional runs: about 124
- Expected additional posts: about 2,720
- Expected final post count: roughly 9,384-9,792
- Current average imported posts per run: 21.9
- Current average cost per run: $0.0566

## Sources To Prioritize If A Later Audit Clears Continuation
- Validated likely/verified creator or X-native finance profiles with ISO-compatible actor output.
- Sources with demonstrated seed-ticker precision and low duplicate rates.
- Underrepresented validated tickers after reviewing concentration in filtered event-study inputs.

## Sources To Exclude Or Deprioritize
- Unverified/inferred YouTube handles until separately validated.
- Broad cashtag/search sources that produce common-word ticker tokens or non-equity promotion noise.
- Market-control accounts for recommendation-event expansion; keep them only if more control attention observations are needed.
- Any actor/source combination that cannot honor historical date windows or returns non-ISO/unparseable timestamps.

## Checkpoint Rule
- If continuation is later approved, write a mini-checkpoint after roughly every $1.00 of additional X spend.
- Each checkpoint must report spend, imported posts, duplicates, duplicate rate, ticker precision, recommendation-event density, date coverage, top sources, and false-positive examples without raw post text.

## Stop Conditions
- Duplicate rate rises materially above the current 0.46%.
- Finance relevance or validated ticker precision deteriorates.
- Classifier false positives dominate new events.
- Actor output does not cover the requested historical window.
- Apify costs exceed the approved cap.
- Actor failures repeat.

## Commit Safety
- No secrets, raw X data, DB files, logs, caches, backups, raw transcript dumps, or giant files will be committed.
