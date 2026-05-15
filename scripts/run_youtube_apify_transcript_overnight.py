#!/usr/bin/env python3
"""Overnight YouTube transcript expansion via selected Apify provider."""
from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finfluencer_alpha.apify_key_manager import ApifyBudgetError, ApifyKeyManager  # noqa: E402
from finfluencer_alpha.apify_transcripts import collect_apify_transcripts  # noqa: E402
from finfluencer_alpha.db import connect  # noqa: E402

OUT_DIR = ROOT / "data" / "exports" / "overnight_collection"
QUEUE_CSV = OUT_DIR / "50_youtube_transcript_expansion_queue.csv"
LIVE_MD = OUT_DIR / "53_youtube_apify_overnight_live_status.md"
CHECKPOINT_JSON = OUT_DIR / "53_youtube_apify_overnight_checkpoint.json"


@dataclass
class BatchMetrics:
    attempted: int = 0
    imported: int = 0
    permanent_failures: int = 0
    transient_failures: int = 0
    estimated_spend_usd: float = 0.0


def _truthy(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def _load_queue(max_videos: int) -> list[str]:
    if not QUEUE_CSV.exists():
        return []
    out: list[str] = []
    with QUEUE_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            vid = (row.get("video_id") or "").strip()
            if not vid or vid in out:
                continue
            out.append(vid)
            if len(out) >= max_videos:
                break
    return out


def _status_map(video_ids: list[str]) -> dict[str, str]:
    if not video_ids:
        return {}
    placeholders = ",".join("?" for _ in video_ids)
    q = f"""
      SELECT video_id, status
      FROM youtube_transcripts
      WHERE video_id IN ({placeholders})
    """
    out: dict[str, str] = {}
    with connect() as conn:
        for r in conn.execute(q, video_ids).fetchall():
            out[str(r["video_id"])] = str(r["status"] or "")
    return out


def _accepted_event_count() -> int:
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM transcript_recommendation_events").fetchone()
        return int(row["n"] or 0)


def _transcript_count() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM youtube_transcripts WHERE status='available' AND COALESCE(full_text,'') != ''"
        ).fetchone()
        return int(row["n"] or 0)


def _write_live_status(
    *,
    started_at: str,
    provider: str,
    dry_run: bool,
    token_slot: str,
    attempted: int,
    imported: int,
    perm_fail: int,
    trans_fail: int,
    spend: float,
    spend_by_slot: dict[str, float],
    accepted_events: int | None,
    queue_remaining: int,
    decision: str,
) -> None:
    success_rate = (imported / attempted) if attempted else 0.0
    cost_per_transcript = (spend / imported) if imported else 0.0
    cost_per_event = (spend / accepted_events) if accepted_events else 0.0
    lines = [
        "# YouTube Apify overnight live status",
        "",
        f"started_at: `{started_at}`",
        f"current_provider: `{provider}`",
        f"dry_run: `{dry_run}`",
        f"current_token_slot: `{token_slot}`",
        f"videos_attempted: `{attempted}`",
        f"transcripts_imported: `{imported}`",
        f"permanent_failures: `{perm_fail}`",
        f"transient_failures: `{trans_fail}`",
        f"estimated_spend_usd: `{round(spend, 6)}`",
        f"spend_by_token_slot: `{json.dumps({k: round(v, 6) for k, v in spend_by_slot.items()}, sort_keys=True)}`",
        f"success_rate: `{round(success_rate, 4)}`",
        f"accepted_events_discovered_so_far: `{accepted_events if accepted_events is not None else 'n/a'}`",
        f"cost_per_transcript_usd: `{round(cost_per_transcript, 6)}`",
        f"cost_per_accepted_event_usd: `{round(cost_per_event, 6) if accepted_events else 'n/a'}`",
        f"remaining_queued_videos: `{queue_remaining}`",
        f"recommended_continue_stop_decision: `{decision}`",
        "",
    ]
    LIVE_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    provider = os.getenv("YOUTUBE_APIFY_SELECTED_PROVIDER", "").strip()
    if not provider:
        raise SystemExit("YOUTUBE_APIFY_SELECTED_PROVIDER is required.")

    run_live = _truthy(os.getenv("RUN_YOUTUBE_APIFY_OVERNIGHT", "0"))
    dry_run = not run_live
    target_spend = _env_float("YOUTUBE_APIFY_TARGET_SPEND_USD", 5.0)
    max_total_spend = _env_float("YOUTUBE_APIFY_MAX_TOTAL_SPEND_USD", 10.0)
    batch_size = max(1, _env_int("YOUTUBE_APIFY_BATCH_SIZE", 10))
    max_videos = max(1, _env_int("YOUTUBE_APIFY_MAX_VIDEOS", 200))
    min_remaining_per_token = _env_float("YOUTUBE_APIFY_MIN_REMAINING_USD_PER_TOKEN", 0.0)
    stop_on_low_sr = _truthy(os.getenv("YOUTUBE_APIFY_STOP_ON_LOW_SUCCESS_RATE", "1"))
    success_floor = _env_float("YOUTUBE_APIFY_SUCCESS_RATE_FLOOR", 0.1)
    accepted_floor = _env_float("YOUTUBE_APIFY_ACCEPTED_EVENT_RATE_FLOOR", 0.0)

    queue_ids = _load_queue(max_videos=max_videos)
    started_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    km = ApifyKeyManager.from_env()
    if min_remaining_per_token > 0:
        for key in km.keys:
            if key.min_remaining_usd is None:
                key.min_remaining_usd = min_remaining_per_token

    idx = 0
    attempted = 0
    imported = 0
    permanent_failures = 0
    transient_failures = 0
    spend_total = 0.0
    spend_by_slot: dict[str, float] = {}
    current_slot = "none"

    start_transcripts = _transcript_count()
    start_events = _accepted_event_count()
    ckpt = {
        "started_at": started_at,
        "provider": provider,
        "dry_run": dry_run,
        "beginning_transcript_count": start_transcripts,
        "beginning_accepted_events": start_events,
        "processed_video_ids": [],
    }
    CHECKPOINT_JSON.write_text(json.dumps(ckpt, indent=2), encoding="utf-8")

    while idx < len(queue_ids):
        if spend_total >= max_total_spend or spend_total >= target_spend:
            break
        batch_ids = queue_ids[idx : idx + batch_size]
        idx += len(batch_ids)
        before = _status_map(batch_ids)

        if dry_run:
            attempted += len(batch_ids)
            _write_live_status(
                started_at=started_at,
                provider=provider,
                dry_run=True,
                token_slot="dry_run",
                attempted=attempted,
                imported=imported,
                perm_fail=permanent_failures,
                trans_fail=transient_failures,
                spend=spend_total,
                spend_by_slot=spend_by_slot,
                accepted_events=None,
                queue_remaining=max(0, len(queue_ids) - idx),
                decision="CONTINUE_DRY_RUN_ONLY",
            )
            continue

        try:
            key = km.choose_key(platform="youtube", projected_cost_usd=0.01)
        except ApifyBudgetError:
            _write_live_status(
                started_at=started_at,
                provider=provider,
                dry_run=False,
                token_slot="none",
                attempted=attempted,
                imported=imported,
                perm_fail=permanent_failures,
                trans_fail=transient_failures,
                spend=spend_total,
                spend_by_slot=spend_by_slot,
                accepted_events=_accepted_event_count(),
                queue_remaining=max(0, len(queue_ids) - idx),
                decision="STOP_NO_PICKABLE_KEY",
            )
            raise SystemExit(1) from None

        current_slot = key.label
        with km.activate_key(key):
            result = collect_apify_transcripts(
                video_ids=batch_ids,
                actor_id=provider,
                batch_size=batch_size,
                max_total_charge_usd=max(0.01, min(max_total_spend - spend_total, 1.0)),
                dry_run=False,
            )

        after = _status_map(batch_ids)
        bm = BatchMetrics(attempted=len(batch_ids), imported=result.available_count, estimated_spend_usd=float(result.cost_usd or 0.0))
        for vid in batch_ids:
            prev = before.get(vid, "")
            cur = after.get(vid, "")
            if prev == "available":
                continue
            if cur in {"disabled", "unavailable", "removed", "private", "age_restricted", "no_transcript"}:
                bm.permanent_failures += 1
            elif cur and cur != "available":
                bm.transient_failures += 1

        attempted += bm.attempted
        imported += bm.imported
        permanent_failures += bm.permanent_failures
        transient_failures += bm.transient_failures
        spend_total += bm.estimated_spend_usd
        spend_by_slot[current_slot] = spend_by_slot.get(current_slot, 0.0) + bm.estimated_spend_usd
        km.record_run(
            key_label=current_slot,
            platform="youtube",
            actor_id=provider,
            run_id=result.run_id,
            source_type="youtube_apify_overnight_batch",
            source_value="queue_csv",
            requested_items=len(batch_ids),
            imported_items=result.available_count,
            duplicates=result.skipped_existing_count,
            cost_usd=bm.estimated_spend_usd,
            status="completed",
            reason="batch_complete",
        )

        success_rate = (imported / attempted) if attempted else 0.0
        accepted_events = _accepted_event_count()
        accepted_rate = (accepted_events / imported) if imported else 0.0
        decision = "CONTINUE"
        if stop_on_low_sr and success_rate < success_floor:
            decision = "STOP_LOW_SUCCESS_RATE"
        if accepted_floor > 0 and imported > 0 and accepted_rate < accepted_floor:
            decision = "STOP_LOW_ACCEPTED_EVENT_RATE"
        if spend_total >= max_total_spend:
            decision = "STOP_MAX_TOTAL_SPEND_REACHED"

        processed = json.loads(CHECKPOINT_JSON.read_text(encoding="utf-8"))
        done = set(processed.get("processed_video_ids") or [])
        done.update(batch_ids)
        processed["processed_video_ids"] = sorted(done)
        processed["attempted"] = attempted
        processed["imported"] = imported
        processed["spend_total"] = round(spend_total, 6)
        processed["current_token_slot"] = current_slot
        CHECKPOINT_JSON.write_text(json.dumps(processed, indent=2), encoding="utf-8")

        _write_live_status(
            started_at=started_at,
            provider=provider,
            dry_run=False,
            token_slot=current_slot,
            attempted=attempted,
            imported=imported,
            perm_fail=permanent_failures,
            trans_fail=transient_failures,
            spend=spend_total,
            spend_by_slot=spend_by_slot,
            accepted_events=accepted_events,
            queue_remaining=max(0, len(queue_ids) - idx),
            decision=decision,
        )
        if decision.startswith("STOP_"):
            break

    if dry_run:
        _write_live_status(
            started_at=started_at,
            provider=provider,
            dry_run=True,
            token_slot="dry_run",
            attempted=attempted,
            imported=imported,
            perm_fail=permanent_failures,
            trans_fail=transient_failures,
            spend=spend_total,
            spend_by_slot=spend_by_slot,
            accepted_events=None,
            queue_remaining=max(0, len(queue_ids) - idx),
            decision="DRY_RUN_COMPLETE",
        )

    print(f"WROTE_LIVE_STATUS={_display_path(LIVE_MD)}")
    print(f"WROTE_CHECKPOINT={_display_path(CHECKPOINT_JSON)}")
    print(f"DRY_RUN={dry_run}")


if __name__ == "__main__":
    main()
