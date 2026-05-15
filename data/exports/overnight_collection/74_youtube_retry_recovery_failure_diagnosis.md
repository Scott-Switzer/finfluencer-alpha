# YouTube retry recovery failure diagnosis

Generated UTC: `2026-05-15T20:32:30Z`
Provider: `supreme_coder/youtube-transcript-scraper`
Controlled retry stop reason: `STOP_CREDIT_EXHAUSTED`

## What happened

- Retry queue built successfully with `2887` prioritized videos.
- Controlled retry ran with batch size `20`, language mode `english_fallback`, spend cap `$0.50`.
- Runner rotated across token slots and stopped after repeated credit-limit responses:
  - `provider_failures_by_type={"STOP_CREDIT_EXHAUSTED": 11, "credit_limit_token": 11}`
- No paid runs were accepted during this controlled retry:
  - attempted `0`, imported `0`, spend `$0.00`.

## Diagnosis by failure class

- Queue quality: **not primary blocker in this run** (no video-level attempts executed).
- Provider instability: **not primary blocker** (no 5xx/runtime instability observed in this controlled window).
- Captions unavailable: **not primary blocker for this run** (no batch-level transcript fetches started).
- IP/proxy blocking: **not observed** in this controlled retry.
- Import/parser issue: **not observed**; parser path was not reached due actor start rejection.
- Key/account issue: **primary blocker**. Actor start calls returned platform credit-limit/hard-limit style 403 responses across available slots.

## Decision

- Exhaustion-mode retry was **not run** because controlled retry success rate was `0.0` and imported transcripts were `0`.
- Further provider retries are **not currently worth it** until eligible Apify accounts have usable credit/headroom for this actor.
- Recommended next action: replenish/replace eligible token slots, then rerun controlled retry first.
