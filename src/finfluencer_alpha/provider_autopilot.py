from __future__ import annotations

import csv
import json
import math
import re
import subprocess
import time
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import DATA_DIR, PROJECT_ROOT, ensure_data_dirs
from .db import connect, count_rows, init_db
from .provider_transcripts import (
    PROVIDER_FAILURE_COLUMNS,
    PROVIDER_IMPORT_COLUMNS,
    ProviderCollectionResult,
    collect_provider_transcripts,
)
from .transcript_vendor import (
    VendorCandidate,
    _eligible_vendor_candidates,
    _metric_bucket,
    _published_timestamp,
    build_transcript_coverage_bias_report,
    import_transcripts_csv,
)

PROVIDER_AUTOPILOT_RUNS_DIR = DATA_DIR / "runs" / "provider_autopilot"
QUEUE_COLUMNS = [
    "queue_rank",
    "video_id",
    "url",
    "creator",
    "creator_category",
    "published_at",
    "year",
    "title",
    "description",
    "priority_score",
    "ticker_signal_count",
    "recommendation_keyword_signal",
    "title_signal",
    "engagement_bucket",
    "current_view_count",
    "current_like_count",
    "current_comment_count",
    "sampling_stratum",
    "sampling_reason",
]
AUTOPILOT_FAILURE_COLUMNS = [
    "chunk_index",
    "attempt_number",
    "provider_attempt_output",
    *PROVIDER_FAILURE_COLUMNS,
]


class ProviderAutopilotError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderAutopilotConfig:
    provider: str = "transcriptapi"
    target_new_transcripts: int = 100
    max_attempts: int = 500
    chunk_size: int = 100
    queue_size: int = 500
    min_low_signal_share: float = 0.25
    max_per_creator: int = 0
    max_per_year: int = 0
    language: str = "en"
    timestamps: bool = False
    captions_only: bool = False
    retry_statuses: tuple[str, ...] = ("http_408",)
    max_retries: int = 2
    sleep_seconds: float = 3.0
    confirm_provider_run: bool = False
    dry_run: bool = False
    run_name: str | None = None
    resume: Path | None = None
    run_root: Path = PROVIDER_AUTOPILOT_RUNS_DIR


@dataclass(frozen=True)
class QueueBuildResult:
    rows: list[dict[str, object]]
    eligible_count: int
    skipped_existing_count: int


@dataclass(frozen=True)
class ProviderAutopilotResult:
    run_dir: Path
    manifest_path: Path
    final_summary_path: Path
    attempted: int
    successful: int
    failed: int
    skipped_existing: int
    retries: int
    dry_run: bool


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _clean(value: object) -> str:
    return str(value or "").strip()


def _normalize_retry_statuses(statuses: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(_clean(status).lower() for status in statuses if _clean(status))
    return normalized or ("http_408",)


def _validate_config(config: ProviderAutopilotConfig) -> ProviderAutopilotConfig:
    provider = config.provider.strip().lower()
    if provider != "transcriptapi":
        raise ProviderAutopilotError(
            "provider-transcript-autopilot only supports --provider transcriptapi."
        )
    if not config.dry_run and not config.confirm_provider_run:
        raise ProviderAutopilotError(
            "Refusing provider autopilot without --confirm-provider-run. "
            "Use --dry-run to preview the queue without provider calls."
        )
    if config.target_new_transcripts < 1:
        raise ProviderAutopilotError("--target-new-transcripts must be at least 1.")
    if config.max_attempts < 1:
        raise ProviderAutopilotError("--max-attempts must be at least 1.")
    if config.chunk_size < 1:
        raise ProviderAutopilotError("--chunk-size must be at least 1.")
    if config.queue_size < 1:
        raise ProviderAutopilotError("--queue-size must be at least 1.")
    if not 0.0 <= config.min_low_signal_share <= 1.0:
        raise ProviderAutopilotError("--min-low-signal-share must be between 0 and 1.")
    if config.max_per_creator < 0:
        raise ProviderAutopilotError("--max-per-creator must be non-negative.")
    if config.max_per_year < 0:
        raise ProviderAutopilotError("--max-per-year must be non-negative.")
    if config.max_retries < 0:
        raise ProviderAutopilotError("--max-retries must be non-negative.")
    if config.sleep_seconds < 0:
        raise ProviderAutopilotError("--sleep-seconds must be non-negative.")
    return replace(
        config,
        provider=provider,
        retry_statuses=_normalize_retry_statuses(config.retry_statuses),
    )


def _title_signal(candidate: VendorCandidate) -> str:
    if candidate.recommendation_keyword_signal or candidate.ticker_signal_count:
        return "high_signal"
    return "low_signal"


def _engagement_bucket(candidate: VendorCandidate) -> str:
    return _metric_bucket(candidate.current_view_count)


def _candidate_allowed(
    candidate: VendorCandidate,
    *,
    selected_ids: set[str],
    creator_counts: Counter[str],
    year_counts: Counter[str],
    max_per_creator: int,
    max_per_year: int,
) -> bool:
    if candidate.video_id in selected_ids:
        return False
    if max_per_creator and creator_counts[candidate.creator] >= max_per_creator:
        return False
    if max_per_year and year_counts[candidate.year] >= max_per_year:
        return False
    return True


def _balance_key(
    candidate: VendorCandidate,
    *,
    low_needed: int,
    stratum_counts: Counter[tuple[str, str, str, str]],
    year_counts: Counter[str],
    creator_counts: Counter[str],
    category_counts: Counter[str],
    signal_counts: Counter[str],
    engagement_counts: Counter[str],
) -> tuple[object, ...]:
    signal = _title_signal(candidate)
    engagement = _engagement_bucket(candidate)
    stratum = (candidate.year, candidate.creator_category, signal, engagement)
    low_preference = 0 if low_needed > 0 and signal == "low_signal" else 1
    return (
        low_preference,
        stratum_counts[stratum],
        year_counts[candidate.year],
        category_counts[candidate.creator_category],
        signal_counts[signal],
        engagement_counts[engagement],
        creator_counts[candidate.creator],
        -candidate.priority_score,
        -_published_timestamp(candidate.published_at),
        candidate.creator.lower(),
        candidate.video_id,
    )


def _select_balanced_candidates(
    candidates: list[VendorCandidate],
    *,
    limit: int,
    min_low_signal_share: float,
    max_per_creator: int,
    max_per_year: int,
) -> list[VendorCandidate]:
    low_available = sum(1 for candidate in candidates if _title_signal(candidate) == "low_signal")
    low_target = min(low_available, math.ceil(limit * min_low_signal_share))
    selected: list[VendorCandidate] = []
    selected_ids: set[str] = set()
    year_counts: Counter[str] = Counter()
    creator_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    signal_counts: Counter[str] = Counter()
    engagement_counts: Counter[str] = Counter()
    stratum_counts: Counter[tuple[str, str, str, str]] = Counter()

    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.priority_score,
            -_published_timestamp(candidate.published_at),
            candidate.creator.lower(),
            candidate.video_id,
        ),
    )
    while len(selected) < limit:
        low_needed = max(0, low_target - signal_counts["low_signal"])
        slots_remaining = limit - len(selected)
        require_low = low_needed >= slots_remaining
        pool = [
            candidate
            for candidate in sorted_candidates
            if _candidate_allowed(
                candidate,
                selected_ids=selected_ids,
                creator_counts=creator_counts,
                year_counts=year_counts,
                max_per_creator=max_per_creator,
                max_per_year=max_per_year,
            )
            and (not require_low or _title_signal(candidate) == "low_signal")
        ]
        if not pool and require_low:
            pool = [
                candidate
                for candidate in sorted_candidates
                if _candidate_allowed(
                    candidate,
                    selected_ids=selected_ids,
                    creator_counts=creator_counts,
                    year_counts=year_counts,
                    max_per_creator=max_per_creator,
                    max_per_year=max_per_year,
                )
            ]
        if not pool:
            break
        selected_candidate = min(
            pool,
            key=lambda candidate: _balance_key(
                candidate,
                low_needed=low_needed,
                stratum_counts=stratum_counts,
                year_counts=year_counts,
                creator_counts=creator_counts,
                category_counts=category_counts,
                signal_counts=signal_counts,
                engagement_counts=engagement_counts,
            ),
        )
        signal = _title_signal(selected_candidate)
        engagement = _engagement_bucket(selected_candidate)
        stratum = (
            selected_candidate.year,
            selected_candidate.creator_category,
            signal,
            engagement,
        )
        selected_ids.add(selected_candidate.video_id)
        selected.append(selected_candidate)
        year_counts[selected_candidate.year] += 1
        creator_counts[selected_candidate.creator] += 1
        category_counts[selected_candidate.creator_category] += 1
        signal_counts[signal] += 1
        engagement_counts[engagement] += 1
        stratum_counts[stratum] += 1
    return selected


def _existing_available_transcript_count() -> int:
    init_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM raw_youtube_videos y
            JOIN youtube_transcripts yt
              ON yt.video_id = y.video_id
            WHERE COALESCE(y.excluded_flag, 0) = 0
              AND yt.status = 'available'
              AND COALESCE(yt.full_text, '') != ''
            """
        ).fetchone()
    return int(row["n"] or 0)


def _queue_row(candidate: VendorCandidate, rank: int) -> dict[str, object]:
    signal = _title_signal(candidate)
    engagement = _engagement_bucket(candidate)
    return {
        "queue_rank": rank,
        "video_id": candidate.video_id,
        "url": candidate.url,
        "creator": candidate.creator,
        "creator_category": candidate.creator_category,
        "published_at": candidate.published_at,
        "year": candidate.year,
        "title": candidate.title,
        "description": candidate.description,
        "priority_score": round(candidate.priority_score, 3),
        "ticker_signal_count": candidate.ticker_signal_count,
        "recommendation_keyword_signal": candidate.recommendation_keyword_signal,
        "title_signal": signal,
        "engagement_bucket": engagement,
        "current_view_count": candidate.current_view_count,
        "current_like_count": candidate.current_like_count,
        "current_comment_count": candidate.current_comment_count,
        "sampling_stratum": (
            f"year={candidate.year};category={candidate.creator_category};"
            f"title_signal={signal};engagement={engagement}"
        ),
        "sampling_reason": "balanced_provider_autopilot_queue",
    }


def build_provider_autopilot_queue(config: ProviderAutopilotConfig) -> QueueBuildResult:
    candidates = _eligible_vendor_candidates(include_blocked=False)
    selected = _select_balanced_candidates(
        candidates,
        limit=config.queue_size,
        min_low_signal_share=config.min_low_signal_share,
        max_per_creator=config.max_per_creator,
        max_per_year=config.max_per_year,
    )
    return QueueBuildResult(
        rows=[_queue_row(candidate, index) for index, candidate in enumerate(selected, start=1)],
        eligible_count=len(candidates),
        skipped_existing_count=_existing_available_transcript_count(),
    )


def _sanitize_run_name(run_name: str | None) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_name or "").strip("._-")
    return cleaned[:80]


def _new_run_dir(config: ProviderAutopilotConfig) -> Path:
    root = _resolve_project_path(config.run_root)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = _sanitize_run_name(config.run_name)
    base_name = f"{timestamp}_{suffix}" if suffix else timestamp
    run_dir = root / base_name
    counter = 2
    while run_dir.exists():
        run_dir = root / f"{base_name}_{counter:02d}"
        counter += 1
    run_dir.mkdir(parents=True)
    return run_dir


def _write_rows(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    if path.exists():
        raise ProviderAutopilotError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _chunk_rows(rows: list[dict[str, str]], chunk_size: int) -> list[list[dict[str, str]]]:
    return [rows[index : index + chunk_size] for index in range(0, len(rows), chunk_size)]


def _append_failures(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUTOPILOT_FAILURE_COLUMNS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_import_csv(path: Path, rows: list[dict[str, object]]) -> None:
    _write_rows(path, rows, PROVIDER_IMPORT_COLUMNS)


def _collect_provider_chunk(
    *,
    config: ProviderAutopilotConfig,
    input_path: Path,
    output_path: Path,
    limit: int,
) -> ProviderCollectionResult:
    return collect_provider_transcripts(
        provider=config.provider,
        input_path=input_path,
        output_path=output_path,
        limit=limit,
        batch_size=config.chunk_size,
        language=config.language,
        timestamps=config.timestamps,
        captions_only=config.captions_only,
        allow_asr=False,
        confirm_provider_run=True,
        skip_existing=True,
    )


def _provider_failure_rows(
    *,
    failure_path: Path,
    chunk_index: int,
    attempt_number: int,
    provider_attempt_output: Path,
) -> list[dict[str, object]]:
    if not failure_path.exists():
        return []
    rows: list[dict[str, object]] = []
    for row in _read_rows(failure_path):
        rows.append(
            {
                "chunk_index": chunk_index,
                "attempt_number": attempt_number,
                "provider_attempt_output": str(provider_attempt_output),
                **row,
            }
        )
    return rows


def _successful_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [row for row in _read_rows(path) if _clean(row.get("video_id"))]


def _write_import_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _status_snapshot() -> dict[str, Any]:
    try:
        from .overtime_collection import transcript_collection_status

        return asdict(transcript_collection_status())
    except Exception as exc:
        return {"error": str(exc)}


def _run_backup() -> dict[str, Any]:
    script = PROJECT_ROOT / "scripts" / "backup_outputs.sh"
    if not script.exists():
        return {"status": "skipped", "reason": "scripts/backup_outputs.sh not found"}
    completed = subprocess.run(
        ["bash", str(script)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {"status": "ran", "returncode": completed.returncode}


def _run_post_run_tasks() -> dict[str, Any]:
    from .transcript_classify import build_transcript_recommendation_events
    from .transcript_exports import export_transcript_events

    build_result = build_transcript_recommendation_events(refresh_existing=True)
    export_paths = export_transcript_events()
    coverage_bias = build_transcript_coverage_bias_report()
    backup_result = _run_backup()
    return {
        "build_transcript_events": asdict(build_result),
        "export_transcript_events": {key: str(value) for key, value in export_paths.items()},
        "coverage_bias_sections": sorted(coverage_bias),
        "backup": backup_result,
    }


def _count_final_rows() -> dict[str, int]:
    init_db()
    with connect() as conn:
        return {
            "transcripts": count_rows(conn, "youtube_transcripts"),
            "transcript_recommendation_events": count_rows(
                conn,
                "transcript_recommendation_events",
            ),
        }


def _coverage_summary() -> dict[str, list[dict[str, object]]]:
    report = build_transcript_coverage_bias_report()
    return {
        "year": report.get("year", []),
        "creator_category": report.get("creator_category", []),
        "title_signal": report.get("title_keyword_signal", []),
    }


def _format_coverage_rows(rows: list[dict[str, object]], label_key: str) -> list[str]:
    if not rows:
        return ["_No rows._"]
    lines = ["| Segment | Covered | Uncovered | Total | Coverage |", "| --- | ---: | ---: | ---: | ---: |"]
    for row in rows:
        lines.append(
            "| "
            f"{row.get(label_key, '')} | "
            f"{row.get('covered', 0)} | "
            f"{row.get('uncovered', 0)} | "
            f"{row.get('total', 0)} | "
            f"{float(row.get('coverage_rate', 0.0)):.1%} |"
        )
    return lines


def _write_final_summary(
    *,
    path: Path,
    manifest: dict[str, Any],
    final_counts: dict[str, int],
    coverage: dict[str, list[dict[str, object]]],
) -> None:
    totals = manifest["totals"]
    lines = [
        "# Provider Transcript Autopilot Summary",
        "",
        f"- Run directory: `{manifest['run_dir']}`",
        f"- Status: {manifest['status']}",
        f"- Provider: {manifest['config']['provider']}",
        f"- Attempted: {totals['attempted']}",
        f"- Successful: {totals['successful']}",
        f"- Failed: {totals['failed']}",
        f"- Skipped existing: {totals['skipped_existing']}",
        f"- Retries: {totals['retries']}",
        f"- Final transcript count: {final_counts['transcripts']}",
        f"- Final event count: {final_counts['transcript_recommendation_events']}",
        "",
        "## Coverage by Year",
        "",
        *_format_coverage_rows(coverage.get("year", []), "year"),
        "",
        "## Coverage by Creator Category",
        "",
        *_format_coverage_rows(coverage.get("creator_category", []), "creator_category"),
        "",
        "## Coverage by Title Signal",
        "",
        *_format_coverage_rows(coverage.get("title_signal", []), "title_keyword_signal"),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _config_payload(config: ProviderAutopilotConfig) -> dict[str, Any]:
    payload = asdict(config)
    payload["retry_statuses"] = list(config.retry_statuses)
    payload["resume"] = str(config.resume) if config.resume else None
    payload["run_root"] = str(config.run_root)
    return payload


def _empty_totals(skipped_existing: int = 0) -> dict[str, int]:
    return {
        "attempted": 0,
        "provider_attempts_including_retries": 0,
        "successful": 0,
        "failed": 0,
        "skipped_existing": skipped_existing,
        "retries": 0,
    }


def _completed_totals(manifest: dict[str, Any]) -> dict[str, int]:
    totals = _empty_totals(int(manifest.get("queue", {}).get("skipped_existing_count", 0)))
    for chunk in manifest.get("chunks", []):
        if chunk.get("status") != "completed":
            continue
        totals["attempted"] += int(chunk.get("attempted", 0))
        totals["provider_attempts_including_retries"] += int(
            chunk.get("provider_attempts_including_retries", 0)
        )
        totals["successful"] += int(chunk.get("successful", 0))
        totals["failed"] += int(chunk.get("failed", 0))
        totals["skipped_existing"] += int(chunk.get("skipped_existing", 0))
        totals["retries"] += int(chunk.get("retries", 0))
    return totals


def _manifest_for_new_run(
    *,
    config: ProviderAutopilotConfig,
    run_dir: Path,
    queue_result: QueueBuildResult,
) -> dict[str, Any]:
    return {
        "run_dir": str(run_dir),
        "status": "started",
        "started_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "completed_at": None,
        "config": _config_payload(config),
        "queue": {
            "selected_queue_path": str(run_dir / "selected_queue.csv"),
            "selected_count": len(queue_result.rows),
            "eligible_count": queue_result.eligible_count,
            "skipped_existing_count": queue_result.skipped_existing_count,
        },
        "chunks": [],
        "totals": _empty_totals(queue_result.skipped_existing_count),
        "post_run": {},
    }


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise ProviderAutopilotError(f"Cannot resume; manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _config_from_manifest(
    current: ProviderAutopilotConfig,
    manifest: dict[str, Any],
) -> ProviderAutopilotConfig:
    stored = manifest.get("config", {})
    return replace(
        current,
        provider=stored.get("provider", current.provider),
        target_new_transcripts=int(
            stored.get("target_new_transcripts", current.target_new_transcripts)
        ),
        max_attempts=int(stored.get("max_attempts", current.max_attempts)),
        chunk_size=int(stored.get("chunk_size", current.chunk_size)),
        queue_size=int(stored.get("queue_size", current.queue_size)),
        min_low_signal_share=float(
            stored.get("min_low_signal_share", current.min_low_signal_share)
        ),
        max_per_creator=int(stored.get("max_per_creator", current.max_per_creator)),
        max_per_year=int(stored.get("max_per_year", current.max_per_year)),
        language=stored.get("language", current.language),
        timestamps=bool(stored.get("timestamps", current.timestamps)),
        captions_only=bool(stored.get("captions_only", current.captions_only)),
        retry_statuses=tuple(stored.get("retry_statuses", current.retry_statuses)),
        max_retries=int(stored.get("max_retries", current.max_retries)),
        sleep_seconds=float(stored.get("sleep_seconds", current.sleep_seconds)),
        run_name=stored.get("run_name", current.run_name),
        run_root=Path(stored.get("run_root", current.run_root)),
    )


def _upsert_chunk_manifest(manifest: dict[str, Any], chunk_status: dict[str, Any]) -> None:
    chunks = [chunk for chunk in manifest.get("chunks", []) if chunk.get("index") != chunk_status["index"]]
    chunks.append(chunk_status)
    manifest["chunks"] = sorted(chunks, key=lambda chunk: int(chunk["index"]))
    manifest["totals"] = _completed_totals(manifest)
    manifest["updated_at"] = _utc_now_iso()


def _write_planned_dry_run_chunks(
    *,
    run_dir: Path,
    queue_rows: list[dict[str, str]],
    config: ProviderAutopilotConfig,
    manifest: dict[str, Any],
) -> None:
    planned_rows = queue_rows[: config.max_attempts]
    for index, chunk in enumerate(_chunk_rows(planned_rows, config.chunk_size), start=1):
        input_path = run_dir / f"chunk_{index:03d}_input.csv"
        output_path = run_dir / f"chunk_{index:03d}_provider_output.csv"
        status_path = run_dir / f"chunk_{index:03d}_status.json"
        import_log_path = run_dir / f"chunk_{index:03d}_import_log.txt"
        _write_rows(input_path, chunk, QUEUE_COLUMNS)
        _write_import_csv(output_path, [])
        _write_import_log(import_log_path, ["Dry run only; provider collection was not run."])
        chunk_status = {
            "index": index,
            "status": "dry_run",
            "input_path": str(input_path),
            "output_path": str(output_path),
            "import_log_path": str(import_log_path),
            "status_path": str(status_path),
            "attempted": len(chunk),
            "provider_attempts_including_retries": 0,
            "successful": 0,
            "failed": 0,
            "skipped_existing": 0,
            "retries": 0,
        }
        _write_json(status_path, chunk_status)
        manifest["chunks"].append(chunk_status)


def _collect_chunk_with_retries(
    *,
    run_dir: Path,
    config: ProviderAutopilotConfig,
    chunk_index: int,
    chunk: list[dict[str, str]],
    failures_path: Path,
) -> dict[str, Any]:
    input_path = run_dir / f"chunk_{chunk_index:03d}_input.csv"
    output_path = run_dir / f"chunk_{chunk_index:03d}_provider_output.csv"
    import_log_path = run_dir / f"chunk_{chunk_index:03d}_import_log.txt"
    status_path = run_dir / f"chunk_{chunk_index:03d}_status.json"
    _write_rows(input_path, chunk, QUEUE_COLUMNS)

    original_by_video_id = {_clean(row.get("video_id")): row for row in chunk}
    pending_video_ids = list(original_by_video_id)
    successes_by_video_id: dict[str, dict[str, object]] = {}
    last_failure_by_video_id: dict[str, dict[str, object]] = {}
    provider_attempts = 0
    retries = 0
    skipped_existing = 0

    for attempt_number in range(1, config.max_retries + 2):
        if attempt_number > 1:
            if config.sleep_seconds:
                time.sleep(config.sleep_seconds)
            retries += len(pending_video_ids)
        attempt_label = "attempt_001" if attempt_number == 1 else f"retry_{attempt_number - 1:03d}"
        attempt_input_path = input_path
        if attempt_number > 1:
            attempt_input_path = run_dir / f"chunk_{chunk_index:03d}_{attempt_label}_input.csv"
            retry_rows = [original_by_video_id[video_id] for video_id in pending_video_ids]
            _write_rows(attempt_input_path, retry_rows, QUEUE_COLUMNS)
        attempt_output_path = run_dir / f"chunk_{chunk_index:03d}_{attempt_label}_provider_output.csv"
        result = _collect_provider_chunk(
            config=config,
            input_path=attempt_input_path,
            output_path=attempt_output_path,
            limit=len(pending_video_ids),
        )
        provider_attempts += result.attempted_count
        skipped_existing += result.skipped_existing_count

        for success_row in _successful_rows(attempt_output_path):
            video_id = _clean(success_row.get("video_id"))
            if video_id:
                successes_by_video_id[video_id] = success_row
                last_failure_by_video_id.pop(video_id, None)

        failure_rows = _provider_failure_rows(
            failure_path=result.failure_path,
            chunk_index=chunk_index,
            attempt_number=attempt_number,
            provider_attempt_output=attempt_output_path,
        )
        _append_failures(failures_path, failure_rows)
        for failure_row in failure_rows:
            video_id = _clean(failure_row.get("video_id"))
            if video_id and video_id not in successes_by_video_id:
                last_failure_by_video_id[video_id] = failure_row

        retryable_failures = [
            row
            for row in failure_rows
            if _clean(row.get("status")).lower() in config.retry_statuses
            and _clean(row.get("video_id")) in original_by_video_id
            and _clean(row.get("video_id")) not in successes_by_video_id
        ]
        pending_video_ids = [_clean(row["video_id"]) for row in retryable_failures]
        if not pending_video_ids:
            break

    combined_success_rows = list(successes_by_video_id.values())
    _write_import_csv(output_path, combined_success_rows)
    import_log_lines = [
        f"Provider successes available for import: {len(combined_success_rows)}",
        f"Provider attempts including retries: {provider_attempts}",
    ]
    imported_count = 0
    if combined_success_rows:
        import_result = import_transcripts_csv(output_path, source="external_provider")
        imported_count = import_result.imported_count
        import_log_lines.append(
            "Transcript import complete: "
            f"imported={import_result.imported_count}, "
            f"overwritten={import_result.overwritten_count}, "
            f"segments={import_result.segment_count}, "
            f"source={import_result.source}."
        )
    else:
        import_log_lines.append("No successful provider transcript rows to import.")
    _write_import_log(import_log_path, import_log_lines)

    status_snapshot = _status_snapshot()
    backup_result = _run_backup()
    final_failed_video_ids = set(last_failure_by_video_id)
    chunk_status = {
        "index": chunk_index,
        "status": "completed",
        "input_path": str(input_path),
        "output_path": str(output_path),
        "import_log_path": str(import_log_path),
        "status_path": str(status_path),
        "attempted": len(chunk),
        "provider_attempts_including_retries": provider_attempts,
        "successful": imported_count,
        "failed": len(final_failed_video_ids),
        "skipped_existing": skipped_existing,
        "retries": retries,
        "retry_statuses": list(config.retry_statuses),
        "final_failure_video_ids": sorted(final_failed_video_ids),
        "status_snapshot": status_snapshot,
        "backup": backup_result,
    }
    _write_json(status_path, chunk_status)
    return chunk_status


def run_provider_transcript_autopilot(
    config: ProviderAutopilotConfig,
) -> ProviderAutopilotResult:
    ensure_data_dirs()
    config = _validate_config(config)
    if config.resume:
        run_dir = _resolve_project_path(config.resume)
        manifest = _load_manifest(run_dir)
        config = _validate_config(_config_from_manifest(config, manifest))
        queue_rows = _read_rows(run_dir / "selected_queue.csv")
        manifest["status"] = "resumed"
        manifest["updated_at"] = _utc_now_iso()
    else:
        run_dir = _new_run_dir(config)
        queue_result = build_provider_autopilot_queue(config)
        selected_queue_path = run_dir / "selected_queue.csv"
        _write_rows(selected_queue_path, queue_result.rows, QUEUE_COLUMNS)
        manifest = _manifest_for_new_run(
            config=config,
            run_dir=run_dir,
            queue_result=queue_result,
        )
        queue_rows = _read_rows(selected_queue_path)

    manifest_path = run_dir / "manifest.json"
    failures_path = run_dir / "failures.csv"
    if not failures_path.exists():
        _append_failures(failures_path, [])

    if config.dry_run:
        if not manifest.get("chunks"):
            _write_planned_dry_run_chunks(
                run_dir=run_dir,
                queue_rows=queue_rows,
                config=config,
                manifest=manifest,
            )
        manifest["status"] = "dry_run"
        manifest["completed_at"] = _utc_now_iso()
        manifest["updated_at"] = _utc_now_iso()
        final_counts = _count_final_rows()
        coverage = _coverage_summary()
        _write_json(manifest_path, manifest)
        final_summary_path = run_dir / "final_summary.md"
        _write_final_summary(
            path=final_summary_path,
            manifest=manifest,
            final_counts=final_counts,
            coverage=coverage,
        )
        totals = manifest["totals"]
        return ProviderAutopilotResult(
            run_dir=run_dir,
            manifest_path=manifest_path,
            final_summary_path=final_summary_path,
            attempted=totals["attempted"],
            successful=totals["successful"],
            failed=totals["failed"],
            skipped_existing=totals["skipped_existing"],
            retries=totals["retries"],
            dry_run=True,
        )

    completed_chunks = {
        int(chunk["index"])
        for chunk in manifest.get("chunks", [])
        if chunk.get("status") == "completed"
    }
    manifest["totals"] = _completed_totals(manifest)
    rows_to_attempt = queue_rows[: config.max_attempts]
    for chunk_index, chunk in enumerate(_chunk_rows(rows_to_attempt, config.chunk_size), start=1):
        if chunk_index in completed_chunks:
            continue
        if manifest["totals"]["successful"] >= config.target_new_transcripts:
            break
        if manifest["totals"]["attempted"] > 0 and config.sleep_seconds:
            time.sleep(config.sleep_seconds)
        chunk_status = _collect_chunk_with_retries(
            run_dir=run_dir,
            config=config,
            chunk_index=chunk_index,
            chunk=chunk,
            failures_path=failures_path,
        )
        _upsert_chunk_manifest(manifest, chunk_status)
        _write_json(manifest_path, manifest)

    manifest["status"] = "completed"
    manifest["completed_at"] = _utc_now_iso()
    manifest["updated_at"] = _utc_now_iso()
    manifest["post_run"] = _run_post_run_tasks()
    final_counts = _count_final_rows()
    coverage = _coverage_summary()
    _write_json(manifest_path, manifest)
    final_summary_path = run_dir / "final_summary.md"
    _write_final_summary(
        path=final_summary_path,
        manifest=manifest,
        final_counts=final_counts,
        coverage=coverage,
    )
    totals = manifest["totals"]
    return ProviderAutopilotResult(
        run_dir=run_dir,
        manifest_path=manifest_path,
        final_summary_path=final_summary_path,
        attempted=totals["attempted"],
        successful=totals["successful"],
        failed=totals["failed"],
        skipped_existing=totals["skipped_existing"],
        retries=totals["retries"],
        dry_run=False,
    )
