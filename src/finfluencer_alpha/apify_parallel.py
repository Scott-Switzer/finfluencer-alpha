from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .apify_queue import select_apify_transcript_queue
from .apify_transcripts import collect_apify_transcripts


@dataclass(frozen=True)
class ShardResult:
    shard_id: int
    attempted: int
    available: int
    no_transcript: int
    errors: int
    blocked: int
    skipped_existing: int
    cost_usd: float | None
    run_id: str
    actor_id: str
    duration_seconds: float


@dataclass(frozen=True)
class ParallelCollectionResult:
    shards: int
    total_attempted: int
    total_available: int
    total_no_transcript: int
    total_errors: int
    total_blocked: int
    total_skipped_existing: int
    total_cost_usd: float
    duration_seconds: float
    shard_results: list[ShardResult]


def _collect_shard(
    shard_id: int,
    video_ids: list[str],
    actor_id: str,
    batch_size: int,
    max_total_charge_usd: float | None,
) -> ShardResult:
    start = time.time()
    result = collect_apify_transcripts(
        video_ids=video_ids,
        actor_id=actor_id,
        batch_size=batch_size,
        max_total_charge_usd=max_total_charge_usd,
        dry_run=False,
    )
    duration = time.time() - start
    return ShardResult(
        shard_id=shard_id,
        attempted=result.attempted_count,
        available=result.available_count,
        no_transcript=result.no_transcript_count,
        errors=result.error_count,
        blocked=result.blocked_count,
        skipped_existing=result.skipped_existing_count,
        cost_usd=result.cost_usd,
        run_id=result.run_id,
        actor_id=result.actor_id,
        duration_seconds=duration,
    )


def collect_apify_transcripts_parallel(
    *,
    actor_id: str,
    start_date: str,
    end_date: str,
    segments: list[str] | None = None,
    exclude_segments: list[str] | None = None,
    shards: int = 3,
    videos_per_shard: int = 300,
    batch_size: int = 100,
    max_total_charge_usd_per_shard: float | None = None,
    total_cost_cap_usd: float | None = None,
    poll_interval_seconds: int = 30,
    max_runtime_minutes: int = 90,
    title_keywords: list[str] | None = None,
) -> ParallelCollectionResult:
    if shards < 1:
        raise ValueError("shards must be at least 1")
    if videos_per_shard < 1:
        raise ValueError("videos_per_shard must be at least 1")

    total_max_videos = shards * videos_per_shard

    queue = select_apify_transcript_queue(
        start_date=start_date,
        end_date=end_date,
        max_videos=total_max_videos,
        segments=segments,
        exclude_segments=exclude_segments,
        title_keywords=title_keywords,
    )

    video_ids = [sel.video_id for sel in queue.selected]
    if not video_ids:
        return ParallelCollectionResult(
            shards=0,
            total_attempted=0,
            total_available=0,
            total_no_transcript=0,
            total_errors=0,
            total_blocked=0,
            total_skipped_existing=0,
            total_cost_usd=0.0,
            duration_seconds=0.0,
            shard_results=[],
        )

    # Partition into non-overlapping shards
    shard_size = max(1, len(video_ids) // shards)
    shard_video_ids: list[list[str]] = []
    for i in range(shards):
        start_idx = i * shard_size
        if i == shards - 1:
            end_idx = len(video_ids)
        else:
            end_idx = (i + 1) * shard_size
        shard_video_ids.append(video_ids[start_idx:end_idx])

    # Enforce total cost cap by adjusting per-shard caps
    effective_per_shard_cap = max_total_charge_usd_per_shard
    if total_cost_cap_usd is not None:
        if effective_per_shard_cap is None:
            effective_per_shard_cap = total_cost_cap_usd / shards
        else:
            effective_per_shard_cap = min(
                effective_per_shard_cap, total_cost_cap_usd / shards
            )

    start_time = time.time()
    shard_results: list[ShardResult] = []
    cumulative_cost = 0.0
    stop_event = threading.Event()

    def cost_guard() -> None:
        while not stop_event.is_set():
            time.sleep(poll_interval_seconds)
            current_cost = sum(
                (r.cost_usd or 0.0) for r in shard_results
            )
            if total_cost_cap_usd is not None and current_cost >= total_cost_cap_usd:
                stop_event.set()
                break
            if time.time() - start_time > max_runtime_minutes * 60:
                stop_event.set()
                break

    guard_thread = threading.Thread(target=cost_guard, daemon=True)
    guard_thread.start()

    with ThreadPoolExecutor(max_workers=shards) as executor:
        futures = {
            executor.submit(
                _collect_shard,
                shard_id=i,
                video_ids=shard_video_ids[i],
                actor_id=actor_id,
                batch_size=batch_size,
                max_total_charge_usd=effective_per_shard_cap,
            ): i
            for i in range(shards)
            if shard_video_ids[i]
        }

        for future in as_completed(futures):
            if stop_event.is_set():
                # Cancel remaining futures if possible
                for f in futures:
                    f.cancel()
                break
            shard_id = futures[future]
            try:
                result = future.result()
                shard_results.append(result)
                cumulative_cost += result.cost_usd or 0.0
            except Exception:
                shard_results.append(
                    ShardResult(
                        shard_id=shard_id,
                        attempted=len(shard_video_ids[shard_id]),
                        available=0,
                        no_transcript=0,
                        errors=1,
                        blocked=0,
                        skipped_existing=0,
                        cost_usd=0.0,
                        run_id="",
                        actor_id=actor_id,
                        duration_seconds=0.0,
                    )
                )

    stop_event.set()
    guard_thread.join(timeout=5)
    duration = time.time() - start_time

    return ParallelCollectionResult(
        shards=len(shard_results),
        total_attempted=sum(r.attempted for r in shard_results),
        total_available=sum(r.available for r in shard_results),
        total_no_transcript=sum(r.no_transcript for r in shard_results),
        total_errors=sum(r.errors for r in shard_results),
        total_blocked=sum(r.blocked for r in shard_results),
        total_skipped_existing=sum(r.skipped_existing for r in shard_results),
        total_cost_usd=sum((r.cost_usd or 0.0) for r in shard_results),
        duration_seconds=duration,
        shard_results=shard_results,
    )
