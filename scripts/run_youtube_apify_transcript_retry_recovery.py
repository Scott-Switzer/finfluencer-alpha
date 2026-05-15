#!/usr/bin/env python3
"""Controlled retry ladder for YouTube Apify transcript recovery."""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finfluencer_alpha.apify_key_manager import (  # noqa: E402
    ApifyBudgetError,
    ApifyKeyManager,
    classify_apify_key_failure,
)
from finfluencer_alpha.apify_transcripts import collect_apify_transcripts  # noqa: E402
from finfluencer_alpha.db import connect  # noqa: E402

OUT_DIR = ROOT / "data" / "exports" / "overnight_collection"
LIVE_MD = OUT_DIR / "72_youtube_apify_retry_recovery_live_status.md"
LIVE_CSV = OUT_DIR / "72_youtube_apify_retry_recovery_live_status.csv"
FINAL_MD = OUT_DIR / "73_youtube_apify_retry_recovery_final_report.md"
FINAL_CSV = OUT_DIR / "73_youtube_apify_retry_recovery_final_report.csv"


def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _language_mode(mode: str) -> list[str]:
    key = (mode or "english_fallback").strip().lower()
    if key == "strict_en":
        return ["en"]
    if key == "broad_fallback":
        return ["en", "en-US", "en-GB", "en-CA", "en-AU"]
    return ["en", "en-US", "en-GB"]


def _load_retry_queue(path: Path, max_videos: int) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            vid = str(row.get("video_id") or "").strip()
            if not vid or vid in out:
                continue
            out.append(vid)
            if max_videos > 0 and len(out) >= max_videos:
                break
    return out


def _status_map(video_ids: list[str]) -> dict[str, tuple[str, str]]:
    if not video_ids:
        return {}
    placeholders = ",".join("?" for _ in video_ids)
    out: dict[str, tuple[str, str]] = {}
    with connect() as conn:
        cols = {str(r["name"]).lower() for r in conn.execute("PRAGMA table_info(youtube_transcripts)").fetchall()}
        ts_expr = "COALESCE(retrieved_at, collected_at, '')" if "collected_at" in cols else "COALESCE(retrieved_at, '')"
        query = f"""
            SELECT video_id,
                   COALESCE(status,'') AS status,
                   COALESCE(error_type,'') AS error_type,
                   {ts_expr} AS ts
            FROM youtube_transcripts
            WHERE video_id IN ({placeholders})
            ORDER BY ts DESC
        """
        for r in conn.execute(query, video_ids).fetchall():
            vid = str(r["video_id"])
            if vid not in out:
                out[vid] = (str(r["status"] or ""), str(r["error_type"] or ""))
    return out


def _is_provider_level_failure(reason: str) -> bool:
    lower = reason.lower()
    if any(token in lower for token in ("transcriptnotfound", "agerestricted", "videounavailable", "url_not_supported", "video_id_not_found")):
        return False
    return True


def _classify_stop(reason: str) -> str:
    lower = reason.lower()
    if "invalid-input" in lower or "field input" in lower or "schema" in lower:
        return "STOP_SCHEMA_ERROR"
    if any(token in lower for token in ("unauthorized", "invalid token", " 401", "http 401")):
        return "STOP_AUTH_ERROR"
    if any(token in lower for token in ("payment required", "insufficient", "hard limit exceeded", "platform-feature-disabled", "actor-disabled", "http 402")):
        return "STOP_CREDIT_EXHAUSTED"
    return "STOP_PROVIDER_FAILURE"


@dataclass
class Metrics:
    attempted: int = 0
    imported: int = 0
    duplicate_existing_skipped: int = 0
    spend: float = 0.0
    provider_failures: Counter[str] = None  # type: ignore[assignment]
    permanent_failures: Counter[str] = None  # type: ignore[assignment]
    transient_failures: Counter[str] = None  # type: ignore[assignment]
    spend_by_slot: dict[str, float] = None  # type: ignore[assignment]
    consecutive_provider_failures: int = 0
    batches: int = 0
    history_success_rate: list[float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.provider_failures = Counter()
        self.permanent_failures = Counter()
        self.transient_failures = Counter()
        self.spend_by_slot = {}
        self.history_success_rate = []


def _write_live_status(
    *,
    started_at: str,
    provider: str,
    batch_size: int,
    token_slot: str,
    queue_remaining: int,
    stop_reason: str,
    exhaust_mode: bool,
    recommend_more_retry: bool,
    m: Metrics,
) -> None:
    success_rate = (m.imported / m.attempted) if m.attempted else 0.0
    cost_per_transcript = (m.spend / m.imported) if m.imported else 0.0
    row = {
        "timestamp_utc": _iso_now(),
        "started_at": started_at,
        "provider": provider,
        "batch_size": batch_size,
        "token_slot_number": token_slot,
        "videos_attempted": m.attempted,
        "transcripts_imported": m.imported,
        "duplicate_existing_skipped": m.duplicate_existing_skipped,
        "permanent_failures_by_type": json.dumps(dict(m.permanent_failures), sort_keys=True),
        "transient_failures_by_type": json.dumps(dict(m.transient_failures), sort_keys=True),
        "provider_failures_by_type": json.dumps(dict(m.provider_failures), sort_keys=True),
        "actual_spend_usd": round(m.spend, 6),
        "spend_by_token_slot_number": json.dumps({k: round(v, 6) for k, v in m.spend_by_slot.items()}, sort_keys=True),
        "success_rate": round(success_rate, 6),
        "cost_per_transcript_usd": round(cost_per_transcript, 6),
        "remaining_retry_queue": queue_remaining,
        "stop_reason": stop_reason,
        "exhaustion_mode": int(exhaust_mode),
        "more_retry_recommended": int(recommend_more_retry),
    }
    fieldnames = list(row.keys())
    LIVE_CSV.parent.mkdir(parents=True, exist_ok=True)
    write_header = not LIVE_CSV.exists() or LIVE_CSV.stat().st_size == 0
    with LIVE_CSV.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    lines = [
        "# YouTube Apify retry recovery live status",
        "",
        f"started_at: `{started_at}`",
        f"provider: `{provider}`",
        f"batch_size: `{batch_size}`",
        f"token_slot_number_only: `{token_slot}`",
        f"videos_attempted: `{m.attempted}`",
        f"transcripts_imported: `{m.imported}`",
        f"duplicate_existing_skipped: `{m.duplicate_existing_skipped}`",
        f"permanent_failures_by_type: `{json.dumps(dict(m.permanent_failures), sort_keys=True)}`",
        f"transient_failures_by_type: `{json.dumps(dict(m.transient_failures), sort_keys=True)}`",
        f"provider_failures_by_type: `{json.dumps(dict(m.provider_failures), sort_keys=True)}`",
        f"actual_spend_usd: `{round(m.spend, 6)}`",
        f"spend_by_token_slot_number_only: `{json.dumps({k: round(v, 6) for k, v in m.spend_by_slot.items()}, sort_keys=True)}`",
        f"success_rate: `{round(success_rate, 4)}`",
        f"cost_per_transcript_usd: `{round(cost_per_transcript, 6)}`",
        f"remaining_retry_queue: `{queue_remaining}`",
        f"stop_reason: `{stop_reason}`",
        f"exhaustion_mode_used: `{exhaust_mode}`",
        f"more_retry_recommended: `{recommend_more_retry}`",
        "",
    ]
    LIVE_MD.write_text("\n".join(lines), encoding="utf-8")


def _write_final_report(
    *,
    started_at: str,
    provider: str,
    batch_size: int,
    queue_remaining: int,
    stop_reason: str,
    exhaust_mode: bool,
    recommend_more_retry: bool,
    m: Metrics,
) -> None:
    success_rate = (m.imported / m.attempted) if m.attempted else 0.0
    cost_per_transcript = (m.spend / m.imported) if m.imported else 0.0
    row = {
        "started_at": started_at,
        "ended_at": _iso_now(),
        "provider": provider,
        "final_batch_size": batch_size,
        "videos_attempted": m.attempted,
        "transcripts_imported": m.imported,
        "duplicate_existing_skipped": m.duplicate_existing_skipped,
        "permanent_failures_by_type": json.dumps(dict(m.permanent_failures), sort_keys=True),
        "transient_failures_by_type": json.dumps(dict(m.transient_failures), sort_keys=True),
        "provider_failures_by_type": json.dumps(dict(m.provider_failures), sort_keys=True),
        "actual_spend_usd": round(m.spend, 6),
        "spend_by_token_slot_number": json.dumps({k: round(v, 6) for k, v in m.spend_by_slot.items()}, sort_keys=True),
        "success_rate": round(success_rate, 6),
        "cost_per_transcript_usd": round(cost_per_transcript, 6),
        "remaining_retry_queue": queue_remaining,
        "stop_reason": stop_reason,
        "exhaustion_mode_used": int(exhaust_mode),
        "more_retry_recommended": int(recommend_more_retry),
    }
    with FINAL_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)
    lines = [
        "# YouTube Apify retry recovery final report",
        "",
        f"started_at: `{started_at}`",
        f"ended_at: `{row['ended_at']}`",
        f"provider: `{provider}`",
        f"final_batch_size: `{batch_size}`",
        f"videos_attempted: `{m.attempted}`",
        f"transcripts_imported: `{m.imported}`",
        f"duplicate_existing_skipped: `{m.duplicate_existing_skipped}`",
        f"permanent_failures_by_type: `{row['permanent_failures_by_type']}`",
        f"transient_failures_by_type: `{row['transient_failures_by_type']}`",
        f"provider_failures_by_type: `{row['provider_failures_by_type']}`",
        f"actual_spend_usd: `{row['actual_spend_usd']}`",
        f"spend_by_token_slot_number_only: `{row['spend_by_token_slot_number']}`",
        f"success_rate: `{row['success_rate']}`",
        f"cost_per_transcript_usd: `{row['cost_per_transcript_usd']}`",
        f"remaining_retry_queue: `{queue_remaining}`",
        f"stop_reason: `{stop_reason}`",
        f"exhaustion_mode_used: `{exhaust_mode}`",
        f"more_retry_recommended: `{recommend_more_retry}`",
        "",
    ]
    FINAL_MD.write_text("\n".join(lines), encoding="utf-8")


def _get_transcript_count() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM youtube_transcripts WHERE status='available' AND COALESCE(full_text,'') != ''"
        ).fetchone()
        return int(row["n"] or 0)


def _get_queue_remaining(queue_path: Path) -> int:
    total = 0
    if not queue_path.exists():
        return 0
    with queue_path.open(newline="", encoding="utf-8") as fh:
        for _ in csv.DictReader(fh):
            total += 1
    return total


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    live_enabled = _truthy(os.getenv("RUN_YOUTUBE_APIFY_RETRY_RECOVERY", "0"))
    provider = os.getenv("YOUTUBE_APIFY_SELECTED_PROVIDER", "supreme_coder/youtube-transcript-scraper").strip()
    queue_path = ROOT / os.getenv(
        "YOUTUBE_RETRY_QUEUE_PATH",
        "data/exports/overnight_collection/71_youtube_transcript_retry_queue.csv",
    )
    batch_initial = max(1, _env_int("YOUTUBE_APIFY_RETRY_BATCH_SIZE_INITIAL", 20))
    batch_max = max(batch_initial, _env_int("YOUTUBE_APIFY_RETRY_BATCH_SIZE_MAX", 50))
    spend_cap = max(0.0, _env_float("YOUTUBE_APIFY_RETRY_CAP_USD", 2.0))
    exhaust_credits = _truthy(os.getenv("YOUTUBE_APIFY_RETRY_EXHAUST_CREDITS", "0"))
    language_mode = os.getenv("YOUTUBE_APIFY_RETRY_LANGUAGE_MODE", "english_fallback")
    languages = _language_mode(language_mode)
    min_success_rate = max(0.0, _env_float("YOUTUBE_APIFY_RETRY_MIN_SUCCESS_RATE", 0.20))
    provider_failure_limit = max(1, _env_int("YOUTUBE_APIFY_RETRY_PROVIDER_FAILURE_LIMIT", 3))
    max_videos = _env_int("YOUTUBE_APIFY_RETRY_MAX_VIDEOS", 1000)
    min_remaining_per_token = max(0.0, _env_float("YOUTUBE_APIFY_RETRY_MIN_REMAINING_USD_PER_TOKEN", 0.05))
    started_at = _iso_now()
    m = Metrics()
    batch_size = batch_initial
    stop_reason = "RUNNING"
    km = ApifyKeyManager.from_env()
    for key in km.keys:
        if key.min_remaining_usd is None:
            key.min_remaining_usd = min_remaining_per_token

    queue_ids = _load_retry_queue(queue_path, max_videos=max_videos)
    idx = 0
    key_provider_failures: Counter[str] = Counter()
    dry_run = not live_enabled
    starting_transcripts = _get_transcript_count()

    if not queue_ids:
        stop_reason = "STOP_EMPTY_RETRY_QUEUE"
        _write_live_status(
            started_at=started_at,
            provider=provider,
            batch_size=batch_size,
            token_slot="none",
            queue_remaining=0,
            stop_reason=stop_reason,
            exhaust_mode=exhaust_credits,
            recommend_more_retry=False,
            m=m,
        )
        _write_final_report(
            started_at=started_at,
            provider=provider,
            batch_size=batch_size,
            queue_remaining=0,
            stop_reason=stop_reason,
            exhaust_mode=exhaust_credits,
            recommend_more_retry=False,
            m=m,
        )
        print("NO_QUEUE_ITEMS=1")
        return

    while idx < len(queue_ids):
        if not exhaust_credits and m.spend >= spend_cap:
            stop_reason = "STOP_SPEND_CAP_REACHED"
            break
        try:
            key = km.choose_key(platform="youtube", projected_cost_usd=0.01)
        except ApifyBudgetError:
            stop_reason = "STOP_NO_PICKABLE_KEY"
            break

        token_slot_number = "".join(ch for ch in key.label if ch.isdigit()) or "unknown"
        batch_ids = queue_ids[idx : idx + batch_size]
        idx += len(batch_ids)
        before = _status_map(batch_ids)

        if dry_run:
            m.attempted += len(batch_ids)
            stop_reason = "DRY_RUN_ONLY"
            _write_live_status(
                started_at=started_at,
                provider=provider,
                batch_size=batch_size,
                token_slot=token_slot_number,
                queue_remaining=max(0, len(queue_ids) - idx),
                stop_reason=stop_reason,
                exhaust_mode=exhaust_credits,
                recommend_more_retry=True,
                m=m,
            )
            continue

        try:
            with km.activate_key(key):
                result = collect_apify_transcripts(
                    video_ids=batch_ids,
                    actor_id=provider,
                    batch_size=batch_size,
                    max_total_charge_usd=max(0.01, min(0.5, spend_cap - m.spend if not exhaust_credits else 1.0)),
                    dry_run=False,
                    languages=languages,
                )
            key_provider_failures[key.label] = 0
            m.consecutive_provider_failures = 0
        except Exception as exc:  # noqa: BLE001
            reason = str(exc)
            lower = reason.lower()
            failure_category = classify_apify_key_failure(reason) or "provider"
            if "ipblocked" in lower:
                m.transient_failures["IpBlocked"] += len(batch_ids)
                stop_reason = "CONTINUE_AFTER_IP_BACKOFF"
                batch_size = min(batch_size, 10)
                time.sleep(2)
                _write_live_status(
                    started_at=started_at,
                    provider=provider,
                    batch_size=batch_size,
                    token_slot=token_slot_number,
                    queue_remaining=max(0, len(queue_ids) - idx),
                    stop_reason=stop_reason,
                    exhaust_mode=exhaust_credits,
                    recommend_more_retry=True,
                    m=m,
                )
                continue
            if _is_provider_level_failure(reason):
                key_provider_failures[key.label] += 1
                m.consecutive_provider_failures += 1
                m.provider_failures[_classify_stop(reason)] += 1
            if any(token in lower for token in ("hard limit exceeded", "platform-feature-disabled", "actor-disabled")):
                km.note_key_failure_for_rotation(
                    key.label,
                    "payment required monthly usage hard limit exceeded",
                    platform="youtube",
                    projected_retry_usd=0.01,
                )
                m.provider_failures["credit_limit_token"] += 1
            elif failure_category in {"auth", "credit", "transient"}:
                km.note_key_failure_for_rotation(
                    key.label,
                    reason,
                    platform="youtube",
                    projected_retry_usd=0.01,
                )
            else:
                # Non-key-health provider errors should rotate key after repeated hits.
                if key_provider_failures[key.label] >= provider_failure_limit:
                    km.exclude_for_session(key.label, reason="provider_failure_limit")

            if m.consecutive_provider_failures >= provider_failure_limit:
                stop_reason = "STOP_REPEATED_PROVIDER_FAILURE"
                break
            stop_candidate = _classify_stop(reason)
            if stop_candidate in {"STOP_SCHEMA_ERROR", "STOP_AUTH_ERROR"}:
                stop_reason = stop_candidate
                break
            _write_live_status(
                started_at=started_at,
                provider=provider,
                batch_size=batch_size,
                token_slot=token_slot_number,
                queue_remaining=max(0, len(queue_ids) - idx),
                stop_reason="CONTINUE_AFTER_PROVIDER_FAILURE",
                exhaust_mode=exhaust_credits,
                recommend_more_retry=True,
                m=m,
            )
            continue

        after = _status_map(batch_ids)
        m.batches += 1
        m.attempted += len(batch_ids)
        m.imported += int(result.available_count or 0)
        m.duplicate_existing_skipped += int(result.skipped_existing_count or 0)
        cost = float(result.cost_usd or 0.0)
        m.spend += cost
        m.spend_by_slot[token_slot_number] = m.spend_by_slot.get(token_slot_number, 0.0) + cost

        for vid in batch_ids:
            prev = before.get(vid, ("", ""))[0].lower()
            cur_status, cur_error = after.get(vid, ("", ""))
            cur = cur_status.lower()
            err = cur_error or cur_status or "unknown"
            if prev == "available":
                continue
            if cur in {"disabled", "unavailable", "removed", "private", "age_restricted", "no_transcript"}:
                m.permanent_failures[err] += 1
            elif cur in {"ip_blocked", "request_blocked", "rate_limited", "error", "no_language"}:
                m.transient_failures[err] += 1

        batch_sr = (result.available_count / len(batch_ids)) if batch_ids else 0.0
        m.history_success_rate.append(batch_sr)
        if m.batches <= 3 and len(m.history_success_rate) == 3 and all(sr >= 0.70 for sr in m.history_success_rate[:3]):
            batch_size = batch_max
        if batch_sr < min_success_rate:
            batch_size = min(batch_size, 10)

        stop_reason = "CONTINUE"
        if not exhaust_credits and m.spend >= spend_cap:
            stop_reason = "STOP_SPEND_CAP_REACHED"
            break
        if m.consecutive_provider_failures >= provider_failure_limit:
            stop_reason = "STOP_REPEATED_PROVIDER_FAILURE"
            break
        _write_live_status(
            started_at=started_at,
            provider=provider,
            batch_size=batch_size,
            token_slot=token_slot_number,
            queue_remaining=max(0, len(queue_ids) - idx),
            stop_reason=stop_reason,
            exhaust_mode=exhaust_credits,
            recommend_more_retry=True,
            m=m,
        )

    if stop_reason in {"RUNNING", "CONTINUE"} and idx >= len(queue_ids):
        stop_reason = "STOP_QUEUE_EXHAUSTED"

    ending_transcripts = _get_transcript_count()
    new_transcripts = max(0, ending_transcripts - starting_transcripts)
    if stop_reason == "STOP_SPEND_CAP_REACHED" and new_transcripts > 0:
        recommend_more = True
    elif stop_reason in {"STOP_SCHEMA_ERROR", "STOP_AUTH_ERROR", "STOP_REPEATED_PROVIDER_FAILURE"}:
        recommend_more = False
    else:
        recommend_more = (m.imported / m.attempted) >= 0.20 if m.attempted else False

    _write_live_status(
        started_at=started_at,
        provider=provider,
        batch_size=batch_size,
        token_slot="unknown",
        queue_remaining=max(0, len(queue_ids) - idx),
        stop_reason=stop_reason,
        exhaust_mode=exhaust_credits,
        recommend_more_retry=recommend_more,
        m=m,
    )
    _write_final_report(
        started_at=started_at,
        provider=provider,
        batch_size=batch_size,
        queue_remaining=max(0, len(queue_ids) - idx),
        stop_reason=stop_reason,
        exhaust_mode=exhaust_credits,
        recommend_more_retry=recommend_more,
        m=m,
    )
    print(f"WROTE_LIVE_MD={_display_path(LIVE_MD)}")
    print(f"WROTE_LIVE_CSV={_display_path(LIVE_CSV)}")
    print(f"WROTE_FINAL_MD={_display_path(FINAL_MD)}")
    print(f"WROTE_FINAL_CSV={_display_path(FINAL_CSV)}")
    print(f"STARTING_TRANSCRIPTS={starting_transcripts}")
    print(f"ENDING_TRANSCRIPTS={ending_transcripts}")
    print(f"NEW_TRANSCRIPTS={new_transcripts}")
    print(f"QUEUE_ROWS={_get_queue_remaining(queue_path)}")
    print(f"DRY_RUN={dry_run}")
    print(f"STOP_REASON={stop_reason}")


if __name__ == "__main__":
    main()
