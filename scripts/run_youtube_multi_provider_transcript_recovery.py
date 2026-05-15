#!/usr/bin/env python3
"""Run multi-provider YouTube transcript recovery with provider/token fallback."""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finfluencer_alpha.apify_key_manager import (  # noqa: E402
    ApifyBudgetError,
    ApifyKeyManager,
)
from finfluencer_alpha.apify_transcripts import collect_apify_transcripts  # noqa: E402
from finfluencer_alpha.db import connect  # noqa: E402

OUT_DIR = ROOT / "data" / "exports" / "overnight_collection"
LIVE_MD = OUT_DIR / "76_youtube_multi_provider_recovery_live_status.md"
LIVE_CSV = OUT_DIR / "76_youtube_multi_provider_recovery_live_status.csv"
FINAL_MD = OUT_DIR / "77_youtube_multi_provider_recovery_final_report.md"
FINAL_CSV = OUT_DIR / "77_youtube_multi_provider_recovery_final_report.csv"
PROBE_CSV = OUT_DIR / "75_youtube_provider_probe.csv"
RETRY_QUEUE_CSV = OUT_DIR / "71_youtube_transcript_retry_queue.csv"


@dataclass
class Metrics:
    attempted: int = 0
    imported: int = 0
    duplicates: int = 0
    spend: float = 0.0
    permanent_failures: Counter[str] = None  # type: ignore[assignment]
    transient_failures: Counter[str] = None  # type: ignore[assignment]
    provider_failures: Counter[str] = None  # type: ignore[assignment]
    spend_by_provider: defaultdict[str, float] = None  # type: ignore[assignment]
    spend_by_token: defaultdict[str, float] = None  # type: ignore[assignment]
    attempts_by_provider: Counter[str] = None  # type: ignore[assignment]
    imports_by_provider: Counter[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.permanent_failures = Counter()
        self.transient_failures = Counter()
        self.provider_failures = Counter()
        self.spend_by_provider = defaultdict(float)
        self.spend_by_token = defaultdict(float)
        self.attempts_by_provider = Counter()
        self.imports_by_provider = Counter()


def _clean(value: object) -> str:
    return str(value or "").strip()


def _truthy(value: str | None) -> bool:
    return _clean(value).lower() in {"1", "true", "yes", "on", "y"}


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


def _language_mode(value: str) -> list[str]:
    mode = _clean(value).lower() or "english_fallback"
    if mode == "strict_en":
        return ["en"]
    if mode == "broad_fallback":
        return ["en", "en-US", "en-GB", "en-CA", "en-AU"]
    return ["en", "en-US", "en-GB"]


def _load_probe_passes(path: Path) -> list[str]:
    if not path.exists():
        return []
    providers: list[tuple[str, int]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if _clean(row.get("decision")) != "PROVIDER_PASS":
                continue
            actor_id = _clean(row.get("actor_id"))
            score = int(float(row.get("transcripts_importable") or 0))
            if actor_id:
                providers.append((actor_id, score))
    providers.sort(key=lambda x: (-x[1], x[0]))
    out: list[str] = []
    for actor_id, _ in providers:
        if actor_id not in out:
            out.append(actor_id)
    return out


def _load_retry_queue(path: Path, max_videos: int) -> list[str]:
    if not path.exists():
        return []
    ids: list[str] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            vid = _clean(row.get("video_id"))
            if not vid or vid in ids:
                continue
            ids.append(vid)
            if max_videos > 0 and len(ids) >= max_videos:
                break
    return ids


def _status_map(video_ids: list[str]) -> dict[str, str]:
    if not video_ids:
        return {}
    placeholders = ",".join("?" for _ in video_ids)
    out: dict[str, str] = {}
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT video_id, COALESCE(status,'') AS status
            FROM youtube_transcripts
            WHERE video_id IN ({placeholders})
            """,
            video_ids,
        ).fetchall()
        for r in rows:
            out[str(r["video_id"])] = str(r["status"] or "")
    return out


def _transcript_count() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM youtube_transcripts WHERE status='available' AND COALESCE(full_text,'')!=''"
        ).fetchone()
        return int(row["n"] or 0)


def _classify_actor_failure(reason: str) -> str:
    lower = reason.lower()
    if "invalid-input" in lower or "input is not valid" in lower or "field input" in lower:
        return "STOP_PROVIDER_SCHEMA_FAILURE"
    if any(x in lower for x in ("unauthorized", "invalid token", "http 401", " 401 ")):
        return "AUTH"
    if any(x in lower for x in ("payment required", "insufficient", "hard limit exceeded", "platform-feature-disabled", "actor-disabled", "http 402", "actor-is-not-rented", "subscription", "not rented")):
        return "CREDIT_OR_RENTAL"
    if any(x in lower for x in ("transcriptnotfound", "agerestricted", "videounavailable", "url_not_supported", "video_id_not_found")):
        return "VIDEO_LEVEL"
    return "ACTOR"


def _write_live(
    *,
    started_at: str,
    best_provider: str,
    fallback_used: list[str],
    stop_reason: str,
    queue_remaining: int,
    pair_status: dict[str, str],
    m: Metrics,
) -> None:
    success_rate = (m.imported / m.attempted) if m.attempted else 0.0
    cpt = (m.spend / m.imported) if m.imported else 0.0
    row = {
        "timestamp_utc": _iso_now(),
        "started_at": started_at,
        "selected_best_provider": best_provider,
        "fallback_providers_used": json.dumps(fallback_used),
        "provider_attempts_by_provider": json.dumps(dict(m.attempts_by_provider), sort_keys=True),
        "provider_token_pair_status": json.dumps(pair_status, sort_keys=True),
        "videos_attempted": m.attempted,
        "transcripts_imported": m.imported,
        "duplicate_existing_skipped": m.duplicates,
        "permanent_failures_by_type": json.dumps(dict(m.permanent_failures), sort_keys=True),
        "transient_failures_by_type": json.dumps(dict(m.transient_failures), sort_keys=True),
        "actor_provider_failures_by_type": json.dumps(dict(m.provider_failures), sort_keys=True),
        "spend_by_provider": json.dumps({k: round(v, 6) for k, v in m.spend_by_provider.items()}, sort_keys=True),
        "spend_by_token_slot_number": json.dumps({k: round(v, 6) for k, v in m.spend_by_token.items()}, sort_keys=True),
        "actual_spend_usd": round(m.spend, 6),
        "cost_per_transcript": round(cpt, 6),
        "success_rate": round(success_rate, 6),
        "remaining_queue": queue_remaining,
        "final_stop_reason": stop_reason,
    }
    write_header = not LIVE_CSV.exists() or LIVE_CSV.stat().st_size == 0
    with LIVE_CSV.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()), lineterminator="\n")
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    lines = [
        "# YouTube multi-provider recovery live status",
        "",
        f"started_at: `{started_at}`",
        f"selected_best_provider: `{best_provider}`",
        f"fallback_providers_used: `{json.dumps(fallback_used)}`",
        f"provider_attempts_by_provider: `{json.dumps(dict(m.attempts_by_provider), sort_keys=True)}`",
        f"provider_token_pair_status: `{json.dumps(pair_status, sort_keys=True)}`",
        f"videos_attempted: `{m.attempted}`",
        f"transcripts_imported: `{m.imported}`",
        f"duplicate_existing_skipped: `{m.duplicates}`",
        f"permanent_failures_by_type: `{json.dumps(dict(m.permanent_failures), sort_keys=True)}`",
        f"transient_failures_by_type: `{json.dumps(dict(m.transient_failures), sort_keys=True)}`",
        f"actor_provider_failures_by_type: `{json.dumps(dict(m.provider_failures), sort_keys=True)}`",
        f"spend_by_provider: `{json.dumps({k: round(v, 6) for k, v in m.spend_by_provider.items()}, sort_keys=True)}`",
        f"spend_by_token_slot_number_only: `{json.dumps({k: round(v, 6) for k, v in m.spend_by_token.items()}, sort_keys=True)}`",
        f"actual_spend_usd: `{round(m.spend, 6)}`",
        f"cost_per_transcript: `{round(cpt, 6)}`",
        f"success_rate: `{round(success_rate, 4)}`",
        f"remaining_queue: `{queue_remaining}`",
        f"final_stop_reason: `{stop_reason}`",
        "",
    ]
    LIVE_MD.write_text("\n".join(lines), encoding="utf-8")


def _write_final(
    *,
    started_at: str,
    best_provider: str,
    fallback_used: list[str],
    stop_reason: str,
    queue_remaining: int,
    pair_status: dict[str, str],
    m: Metrics,
) -> None:
    success_rate = (m.imported / m.attempted) if m.attempted else 0.0
    cpt = (m.spend / m.imported) if m.imported else 0.0
    row = {
        "started_at": started_at,
        "ended_at": _iso_now(),
        "selected_best_provider": best_provider,
        "fallback_providers_used": json.dumps(fallback_used),
        "provider_attempts_by_provider": json.dumps(dict(m.attempts_by_provider), sort_keys=True),
        "provider_token_pair_status": json.dumps(pair_status, sort_keys=True),
        "videos_attempted": m.attempted,
        "transcripts_imported": m.imported,
        "duplicate_existing_skipped": m.duplicates,
        "permanent_failures_by_type": json.dumps(dict(m.permanent_failures), sort_keys=True),
        "transient_failures_by_type": json.dumps(dict(m.transient_failures), sort_keys=True),
        "actor_provider_failures_by_type": json.dumps(dict(m.provider_failures), sort_keys=True),
        "spend_by_provider": json.dumps({k: round(v, 6) for k, v in m.spend_by_provider.items()}, sort_keys=True),
        "spend_by_token_slot_number": json.dumps({k: round(v, 6) for k, v in m.spend_by_token.items()}, sort_keys=True),
        "actual_spend_usd": round(m.spend, 6),
        "cost_per_transcript": round(cpt, 6),
        "success_rate": round(success_rate, 6),
        "remaining_queue": queue_remaining,
        "final_stop_reason": stop_reason,
        "more_credits_or_providers_available": int(stop_reason not in {"STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED", "STOP_NO_PROVIDER_PASSED_CANARY"}),
    }
    with FINAL_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)
    lines = ["# YouTube multi-provider recovery final report", ""]
    for k, v in row.items():
        lines.append(f"{k}: `{v}`")
    lines.append("")
    FINAL_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    live = _truthy(os.getenv("RUN_YOUTUBE_MULTI_PROVIDER_RECOVERY", "0"))
    cap_usd = _env_float("YOUTUBE_MULTI_PROVIDER_RECOVERY_CAP_USD", 2.00)
    exhaust = _truthy(os.getenv("YOUTUBE_MULTI_PROVIDER_EXHAUST_CREDITS", "0"))
    max_videos = _env_int("YOUTUBE_MULTI_PROVIDER_MAX_VIDEOS", 1000)
    batch_size = max(1, _env_int("YOUTUBE_MULTI_PROVIDER_BATCH_SIZE_INITIAL", 10))
    batch_max = max(batch_size, _env_int("YOUTUBE_MULTI_PROVIDER_BATCH_SIZE_MAX", 50))
    success_floor = max(0.0, _env_float("YOUTUBE_MULTI_PROVIDER_MIN_SUCCESS_RATE", 0.20))
    failure_limit = max(1, _env_int("YOUTUBE_MULTI_PROVIDER_FAILURE_LIMIT", 3))
    languages = _language_mode(os.getenv("YOUTUBE_MULTI_PROVIDER_LANGUAGE_MODE", "english_fallback"))
    started_at = _iso_now()
    m = Metrics()
    km = ApifyKeyManager.from_env()
    providers = _load_probe_passes(PROBE_CSV)
    queue = _load_retry_queue(RETRY_QUEUE_CSV, max_videos=max_videos)
    fallback_used: list[str] = []
    stop_reason = "RUNNING"
    if not providers:
        stop_reason = "STOP_NO_PROVIDER_PASSED_CANARY"
        _write_live(
            started_at=started_at,
            best_provider="none",
            fallback_used=[],
            stop_reason=stop_reason,
            queue_remaining=len(queue),
            pair_status={},
            m=m,
        )
        _write_final(
            started_at=started_at,
            best_provider="none",
            fallback_used=[],
            stop_reason=stop_reason,
            queue_remaining=len(queue),
            pair_status={},
            m=m,
        )
        print("STOP_REASON=STOP_NO_PROVIDER_PASSED_CANARY")
        return
    if not queue:
        stop_reason = "STOP_QUEUE_EXHAUSTED"
        _write_live(
            started_at=started_at,
            best_provider=providers[0],
            fallback_used=[],
            stop_reason=stop_reason,
            queue_remaining=0,
            pair_status={},
            m=m,
        )
        _write_final(
            started_at=started_at,
            best_provider=providers[0],
            fallback_used=[],
            stop_reason=stop_reason,
            queue_remaining=0,
            pair_status={},
            m=m,
        )
        print("STOP_REASON=STOP_QUEUE_EXHAUSTED")
        return

    pair_status: dict[str, str] = {}
    provider_fail_streak: Counter[str] = Counter()
    provider_idx = 0
    batch_counter = 0
    idx = 0
    start_transcripts = _transcript_count()

    while idx < len(queue):
        if not exhaust and m.spend >= cap_usd:
            stop_reason = "STOP_SPEND_CAP"
            break
        if provider_idx >= len(providers):
            stop_reason = "STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED"
            break
        provider = providers[provider_idx]
        if provider not in fallback_used:
            fallback_used.append(provider)

        try:
            key = km.choose_key(platform="youtube", projected_cost_usd=0.01)
        except ApifyBudgetError:
            provider_idx += 1
            continue

        slot = "".join(ch for ch in key.label if ch.isdigit()) or "unknown"
        pair_key = f"{provider}::{slot}"
        if pair_status.get(pair_key, "").startswith("EXHAUSTED"):
            # try next key/provider combination.
            km.exclude_for_session(key.label, reason="pair_exhausted")
            continue

        batch_ids = queue[idx : idx + batch_size]
        before = _status_map(batch_ids)
        m.attempts_by_provider[provider] += len(batch_ids)
        batch_counter += 1

        if not live:
            m.attempted += len(batch_ids)
            idx += len(batch_ids)
            stop_reason = "DRY_RUN_ONLY"
            _write_live(
                started_at=started_at,
                best_provider=providers[0],
                fallback_used=fallback_used,
                stop_reason=stop_reason,
                queue_remaining=max(0, len(queue) - idx),
                pair_status=pair_status,
                m=m,
            )
            continue

        try:
            with km.activate_key(key):
                result = collect_apify_transcripts(
                    video_ids=batch_ids,
                    actor_id=provider,
                    batch_size=batch_size,
                    max_total_charge_usd=max(0.01, min(0.50, cap_usd - m.spend if not exhaust else 1.0)),
                    dry_run=False,
                    languages=languages,
                )
            pair_status[pair_key] = "ACTIVE"
            provider_fail_streak[provider] = 0
        except Exception as exc:  # noqa: BLE001
            reason = _clean(exc)
            kind = _classify_actor_failure(reason)
            if kind == "STOP_PROVIDER_SCHEMA_FAILURE":
                pair_status[pair_key] = "EXHAUSTED_SCHEMA"
                m.provider_failures["schema_failure"] += 1
                stop_reason = "STOP_PROVIDER_SCHEMA_FAILURE"
                break
            if kind in {"AUTH", "CREDIT_OR_RENTAL"}:
                pair_status[pair_key] = f"EXHAUSTED_{kind.lower()}"
                m.provider_failures["provider_start_failure"] += 1
                km.note_key_failure_for_rotation(key.label, reason, platform="youtube", projected_retry_usd=0.01)
                provider_idx = min(provider_idx + 1, len(providers))
            elif kind == "VIDEO_LEVEL":
                pair_status[pair_key] = "ACTIVE_VIDEO_LEVEL_ONLY"
            else:
                pair_status[pair_key] = "ACTIVE_ACTOR_FAILURE"
                provider_fail_streak[provider] += 1
                m.provider_failures["actor_failure"] += 1
                if provider_fail_streak[provider] >= failure_limit:
                    provider_idx = min(provider_idx + 1, len(providers))
                    if provider_idx >= len(providers):
                        stop_reason = "STOP_REPEATED_ACTOR_FAILURE"
                        break
            _write_live(
                started_at=started_at,
                best_provider=providers[0],
                fallback_used=fallback_used,
                stop_reason=stop_reason if stop_reason != "RUNNING" else "CONTINUE_AFTER_PROVIDER_SWITCH",
                queue_remaining=max(0, len(queue) - idx),
                pair_status=pair_status,
                m=m,
            )
            continue

        idx += len(batch_ids)
        after = _status_map(batch_ids)
        imported = int(result.available_count or 0)
        m.imported += imported
        m.imports_by_provider[provider] += imported
        m.attempted += len(batch_ids)
        m.duplicates += int(result.skipped_existing_count or 0)
        cost = float(result.cost_usd or 0.0)
        m.spend += cost
        m.spend_by_provider[provider] += cost
        m.spend_by_token[slot] += cost

        for vid in batch_ids:
            if before.get(vid) == "available":
                continue
            cur = _clean(after.get(vid)).lower()
            if cur in {"disabled", "unavailable", "removed", "private", "age_restricted", "no_transcript"}:
                m.permanent_failures[cur or "unknown"] += 1
            elif cur in {"ip_blocked", "request_blocked", "rate_limited", "error", "no_language"}:
                m.transient_failures[cur or "unknown"] += 1

        batch_sr = (imported / len(batch_ids)) if batch_ids else 0.0
        if batch_counter >= 3 and batch_sr >= 0.70:
            batch_size = batch_max
        if batch_sr < success_floor:
            batch_size = min(batch_size, 10)
        if m.attempted > 0 and (m.imported / m.attempted) < success_floor and batch_counter >= 5:
            stop_reason = "STOP_SUCCESS_RATE_FLOOR"
            break

        _write_live(
            started_at=started_at,
            best_provider=providers[0],
            fallback_used=fallback_used,
            stop_reason="CONTINUE",
            queue_remaining=max(0, len(queue) - idx),
            pair_status=pair_status,
            m=m,
        )

    if stop_reason == "RUNNING":
        stop_reason = "STOP_QUEUE_EXHAUSTED" if idx >= len(queue) else "STOP_ALL_PROVIDER_TOKEN_PAIRS_EXHAUSTED"

    _write_live(
        started_at=started_at,
        best_provider=providers[0],
        fallback_used=fallback_used,
        stop_reason=stop_reason,
        queue_remaining=max(0, len(queue) - idx),
        pair_status=pair_status,
        m=m,
    )
    _write_final(
        started_at=started_at,
        best_provider=providers[0],
        fallback_used=fallback_used,
        stop_reason=stop_reason,
        queue_remaining=max(0, len(queue) - idx),
        pair_status=pair_status,
        m=m,
    )
    end_transcripts = _transcript_count()
    print(f"WROTE_LIVE_MD={_display_path(LIVE_MD)}")
    print(f"WROTE_LIVE_CSV={_display_path(LIVE_CSV)}")
    print(f"WROTE_FINAL_MD={_display_path(FINAL_MD)}")
    print(f"WROTE_FINAL_CSV={_display_path(FINAL_CSV)}")
    print(f"STARTING_TRANSCRIPTS={start_transcripts}")
    print(f"ENDING_TRANSCRIPTS={end_transcripts}")
    print(f"NEW_TRANSCRIPTS={max(0, end_transcripts - start_transcripts)}")
    print(f"STOP_REASON={stop_reason}")
    print(f"DRY_RUN={not live}")


if __name__ == "__main__":
    main()
