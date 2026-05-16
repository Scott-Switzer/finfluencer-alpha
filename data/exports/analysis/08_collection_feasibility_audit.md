# Collection Feasibility Audit (YouTube Transcripts)

Generated UTC: `2026-05-15`
Branch: `x-youtube-full-research-expansion`
Scope: read-only feasibility audit (no jobs run, no recovery run, no spend)

## Executive finding

Probe pass does **not** currently translate into scalable collection. Latest controlled recovery stopped with `STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`, imported `0`, spent `$0`, and left queue backlog unprocessed (`remaining_queue=500` in multi-provider recovery report).

Current lock-state metrics to preserve:
- transcripts: `9,992`
- accepted recommendation events: `1,554`

## Evidence reviewed

- Provider probe artifacts: `data/exports/overnight_collection/75_youtube_provider_probe.md`, `data/exports/overnight_collection/75_youtube_provider_probe.csv`
- Controlled recovery artifacts: `data/exports/overnight_collection/76_youtube_multi_provider_recovery_live_status.md`, `data/exports/overnight_collection/77_youtube_multi_provider_recovery_final_report.md`, plus earlier retry-recovery diagnostics `73` and `74`
- Key usage ledger: `data/exports/overnight_collection/apify_key_usage_ledger.csv`
- Retry/remaining queue: `data/exports/overnight_collection/71_youtube_transcript_retry_queue.md`, `data/exports/overnight_collection/71_youtube_transcript_retry_queue.csv`, `data/exports/overnight_collection/50_youtube_transcript_expansion_queue.md`
- Provider registry and recovery/probe scripts: `src/finfluencer_alpha/youtube_transcript_provider_registry.py`, `scripts/probe_youtube_transcript_providers.py`, `scripts/run_youtube_multi_provider_transcript_recovery.py`
- Native/free pipeline and proxy/provider code paths: `src/finfluencer_alpha/youtube_transcripts.py`, `src/finfluencer_alpha/transcript_proxy.py`, `src/finfluencer_alpha/provider_transcripts.py`, `src/finfluencer_alpha/transcript_method_benchmark.py`
- Prior attempt documentation (Apify/proxy/provider): `docs/apify_transcript_collection.md`, `docs/youtube_transcript_strategy.md`, `data/exports/reporting/transcript_collection_limitations_for_paper.md`, `data/exports/reporting/tonight_transcript_collection_summary.md`, `data/exports/overnight_collection/84_collection_lock_rationale.md`

## Direct answers

### 1) Does probe pass mean tokens can collect at scale?

No. Probe pass only demonstrates a canary-level condition: a provider-token pair can start and return at least one importable item in a very small test window. It does **not** prove sustained start/run eligibility across larger batches, multiple slots, or repeated attempts under real recovery conditions.

### 2) Why did recovery fail after probe pass?

Recovery failed at the **provider-start / account-capacity layer**, not at transcript parsing/import.

Observed pattern:
- `videos_attempted=0`, `transcripts_imported=0`, `actual_spend_usd=0.0`
- `final_stop_reason=STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED`
- pair status marked `EXHAUSTED_credit_or_rental`
- provider failure class included `provider_start_failure`

This is consistent with account-level or rental-gating failures (credit/rental exhaustion) after canary success, which can happen when probe succeeds on a narrow condition but batch recovery immediately encounters 403/credit/rental gating.

### 3) Any remaining free/native transcript route worth trying now without paid Apify?

A free/native route exists in code (`youtube_transcript_api` with optional proxy handling and benchmarking), but evidence indicates weak near-term payoff:
- Prior proxy/Webshare route showed 0 usable proxies in diagnostics and 0 imports.
- Prior nightly summary and limitations docs show repeated blocking/rate-limit/proxy tunnel failures on that route.

Controller-review option (tiny dry-run only, later): a **very small** no-spend dry-run benchmark (`api-session`, `no-proxy`, ~5 videos) could validate whether platform conditions changed. This is only a verification check, not a scalable plan.

### 4) Any non-Apify provider already integrated and funded?

Integrated: yes (`youtubetranscript_dev`, `transcriptapi`, and native package paths are implemented).

Funded and currently viable at scale: no convincing evidence in latest artifacts. Historical/diagnostic reporting indicates provider credit/payment gating (`402 Payment Required`) and no demonstrated current funded headroom for meaningful batch expansion.

### 5) Remaining videos likely to convert into accepted events?

Low expected conversion right now under current constraints. The retry queue is large/prioritized, but recent controlled recovery imported `0`, and accepted-event count remained unchanged in lock-state outcomes. Without a functioning scalable collection path, backlog size does not convert into event gains.

### 6) Expected marginal value: more collection vs move to analysis?

Marginal value of more collection **right now** is low:
- repeated zero-import controlled attempts,
- exhausted provider-token pair statuses,
- no-cost recoveries yielding no additional transcripts/events.

Marginal value of moving to analysis is higher because the dataset is already large and locked (`9,992` transcripts; `1,554` accepted events), with incremental collection currently blocked by capacity constraints rather than queue design.

### 7) Decision: collect more or lock sample?

Given current evidence, there is no real no-new-credential/no-new-payment route proven to add transcripts at scale immediately. Continue only if controller approves a tiny verification dry-run on native path; otherwise prioritize analysis.

Final verdict: lock sample.
