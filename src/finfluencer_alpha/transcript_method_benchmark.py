from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import EXPORTS_DIR, ensure_data_dirs, get_settings
from .transcript_proxy import (
    ProxyConfig,
    create_yt_proxy_config,
    proxymode_summary,
    redact_credentials,
    resolve_proxy_config,
)
from .youtube_transcripts import (
    TranscriptFetchResult,
    create_youtube_transcript_api,
    fetch_transcript_for_video,
)

TRANSCRIPTS_EXPORT_DIR = EXPORTS_DIR / "transcripts"
DEFAULT_BENCHMARK_CSV_PATH = TRANSCRIPTS_EXPORT_DIR / "transcript_method_benchmark.csv"
DEFAULT_BENCHMARK_MD_PATH = TRANSCRIPTS_EXPORT_DIR / "transcript_method_benchmark.md"
SUPPORTED_BENCHMARK_METHODS = ("api-single", "api-session", "package-cli-batch")
BENCHMARK_COLUMNS = [
    "method",
    "run_mode",
    "selected_video_count",
    "live_requests_attempted",
    "successes",
    "disabled",
    "unavailable",
    "no_language",
    "request_blocked",
    "ip_blocked",
    "rate_limited",
    "proxy_errors",
    "other_errors",
    "terminal_failures",
    "transient_failures",
    "block_proxy_failures",
    "elapsed_seconds",
    "seconds_per_successful_transcript",
    "metadata_complete_successes",
    "metadata_completeness",
    "support_status",
    "recommendation",
    "stop_reason",
    "notes",
]


@dataclass(frozen=True)
class TranscriptMethodBenchmarkResult:
    csv_path: Path
    markdown_path: Path
    rows: tuple[dict[str, Any], ...]
    stopped_reason: str | None


def _clean(value: object) -> str:
    return str(value or "").strip()


def _read_video_ids(path: Path, max_videos: int) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Benchmark queue input not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        video_ids: list[str] = []
        seen: set[str] = set()
        for row in reader:
            video_id = _clean(row.get("video_id"))
            if not video_id or video_id in seen:
                continue
            seen.add(video_id)
            video_ids.append(video_id)
            if len(video_ids) >= max_videos:
                break
    return video_ids


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=BENCHMARK_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _metadata_complete(result: TranscriptFetchResult) -> bool:
    return all(
        (
            bool(result.language),
            bool(result.language_code),
            result.is_generated is not None,
            result.is_translatable is not None,
            bool(result.retrieval_method),
            result.source_confidence is not None,
            bool(result.provider_version),
        )
    )


def _empty_row(method: str, *, run_mode: str, selected: int, notes: str) -> dict[str, Any]:
    return {
        "method": method,
        "run_mode": run_mode,
        "selected_video_count": selected,
        "live_requests_attempted": 0,
        "successes": 0,
        "disabled": 0,
        "unavailable": 0,
        "no_language": 0,
        "request_blocked": 0,
        "ip_blocked": 0,
        "rate_limited": 0,
        "proxy_errors": 0,
        "other_errors": 0,
        "terminal_failures": 0,
        "transient_failures": 0,
        "block_proxy_failures": 0,
        "elapsed_seconds": 0.0,
        "seconds_per_successful_transcript": "",
        "metadata_complete_successes": 0,
        "metadata_completeness": "",
        "support_status": "not_measured" if run_mode == "dry_run" else "skipped",
        "recommendation": "do_not_promote",
        "stop_reason": "",
        "notes": notes,
    }


def _status_bucket(result: TranscriptFetchResult) -> str:
    status = _clean(result.status) or "error"
    if status == "available":
        return "successes"
    if status in {
        "disabled",
        "unavailable",
        "no_language",
        "request_blocked",
        "ip_blocked",
        "rate_limited",
    }:
        return status
    message = " ".join(part for part in [result.error_type, result.error_message] if part).lower()
    if "proxy" in message:
        return "proxy_errors"
    return "other_errors"


def _finalize_api_row(
    *,
    method: str,
    selected: int,
    attempts: int,
    counts: dict[str, int],
    metadata_complete_successes: int,
    elapsed_seconds: float,
    stop_reason: str | None,
) -> dict[str, Any]:
    successes = counts.get("successes", 0)
    terminal_failures = (
        counts.get("disabled", 0)
        + counts.get("unavailable", 0)
        + counts.get("no_language", 0)
    )
    transient_failures = counts.get("rate_limited", 0) + counts.get("other_errors", 0)
    block_proxy_failures = (
        counts.get("request_blocked", 0)
        + counts.get("ip_blocked", 0)
        + counts.get("proxy_errors", 0)
    )
    return {
        "method": method,
        "run_mode": "confirm_run",
        "selected_video_count": selected,
        "live_requests_attempted": attempts,
        "successes": successes,
        "disabled": counts.get("disabled", 0),
        "unavailable": counts.get("unavailable", 0),
        "no_language": counts.get("no_language", 0),
        "request_blocked": counts.get("request_blocked", 0),
        "ip_blocked": counts.get("ip_blocked", 0),
        "rate_limited": counts.get("rate_limited", 0),
        "proxy_errors": counts.get("proxy_errors", 0),
        "other_errors": counts.get("other_errors", 0),
        "terminal_failures": terminal_failures,
        "transient_failures": transient_failures,
        "block_proxy_failures": block_proxy_failures,
        "elapsed_seconds": round(elapsed_seconds, 6),
        "seconds_per_successful_transcript": (
            round(elapsed_seconds / successes, 6) if successes else ""
        ),
        "metadata_complete_successes": metadata_complete_successes,
        "metadata_completeness": round(
            metadata_complete_successes / successes, 6
        )
        if successes
        else "",
        "support_status": "supported",
        "recommendation": "do_not_promote",
        "stop_reason": stop_reason or "",
        "notes": "measurement_only_no_db_writes",
    }


def _run_api_method(
    *,
    method: str,
    video_ids: list[str],
    proxy_config: object | None,
    allow_translation: bool,
    languages: list[str],
) -> tuple[dict[str, Any], str | None]:
    counts: dict[str, int] = {}
    metadata_complete_successes = 0
    attempts = 0
    stop_reason: str | None = None
    api_client = (
        create_youtube_transcript_api(proxy_config=proxy_config)
        if method == "api-session"
        else None
    )
    started = time.perf_counter()
    for video_id in video_ids:
        attempts += 1
        result = fetch_transcript_for_video(
            video_id,
            languages=languages,
            allow_translation=allow_translation,
            proxy_config=None if api_client is not None else proxy_config,
            api_client=api_client,
        )
        bucket = _status_bucket(result)
        counts[bucket] = counts.get(bucket, 0) + 1
        if bucket == "successes" and _metadata_complete(result):
            metadata_complete_successes += 1
        if bucket in {"request_blocked", "ip_blocked", "rate_limited", "proxy_errors"}:
            stop_reason = bucket
            break
    elapsed_seconds = time.perf_counter() - started
    return (
        _finalize_api_row(
            method=method,
            selected=len(video_ids),
            attempts=attempts,
            counts=counts,
            metadata_complete_successes=metadata_complete_successes,
            elapsed_seconds=elapsed_seconds,
            stop_reason=stop_reason,
        ),
        stop_reason,
    )


def _cli_proxy_args(proxy_config: ProxyConfig) -> list[str]:
    if proxy_config.mode == "webshare":
        return [
            "--webshare-proxy-username",
            proxy_config.webshare_username or "",
            "--webshare-proxy-password",
            proxy_config.webshare_password or "",
        ]
    if proxy_config.mode == "generic":
        args: list[str] = []
        if proxy_config.http_proxy:
            args.extend(["--http-proxy", proxy_config.http_proxy])
        if proxy_config.https_proxy:
            args.extend(["--https-proxy", proxy_config.https_proxy])
        return args
    return []


def _run_package_cli_batch(
    *,
    video_ids: list[str],
    proxy_config: ProxyConfig,
    languages: list[str],
) -> tuple[dict[str, Any], str | None]:
    started = time.perf_counter()
    args = [
        sys.executable,
        "-m",
        "youtube_transcript_api",
        *video_ids,
        "--format",
        "json",
        "--languages",
        *languages,
        *_cli_proxy_args(proxy_config),
    ]
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=240,
        )
    except (OSError, subprocess.TimeoutExpired):
        elapsed_seconds = time.perf_counter() - started
        row = _empty_row(
            "package-cli-batch",
            run_mode="confirm_run",
            selected=len(video_ids),
            notes="package_cli_unavailable_or_timed_out",
        )
        row.update(
            {
                "live_requests_attempted": len(video_ids),
                "elapsed_seconds": round(elapsed_seconds, 6),
                "support_status": "unsupported",
                "stop_reason": "package_cli_unavailable_or_timed_out",
            }
        )
        return row, None

    elapsed_seconds = time.perf_counter() - started
    text = completed.stdout.strip()
    row = _empty_row(
        "package-cli-batch",
        run_mode="confirm_run",
        selected=len(video_ids),
        notes="measurement_only_no_db_writes",
    )
    row.update(
        {
            "live_requests_attempted": len(video_ids),
            "elapsed_seconds": round(elapsed_seconds, 6),
        }
    )
    if completed.returncode != 0:
        row.update(
            {
                "support_status": "unsupported",
                "other_errors": len(video_ids),
                "transient_failures": len(video_ids),
                "stop_reason": "package_cli_nonzero_exit",
                "notes": "package_cli_nonzero_exit_output_not_parsed",
            }
        )
        return row, None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        row.update(
            {
                "support_status": "unsupported",
                "other_errors": len(video_ids),
                "transient_failures": len(video_ids),
                "stop_reason": "package_cli_json_parse_failed",
                "notes": "package_cli_output_not_safely_parseable",
            }
        )
        return row, None
    if not isinstance(parsed, list) or not all(isinstance(item, list) for item in parsed):
        row.update(
            {
                "support_status": "unsupported",
                "other_errors": len(video_ids),
                "transient_failures": len(video_ids),
                "stop_reason": "package_cli_json_shape_unsupported",
                "notes": "package_cli_json_shape_unsupported",
            }
        )
        return row, None

    successes = len(parsed)
    other_errors = max(0, len(video_ids) - successes)
    row.update(
        {
            "support_status": "supported_but_metadata_incomplete",
            "successes": successes,
            "other_errors": other_errors,
            "transient_failures": other_errors,
            "seconds_per_successful_transcript": (
                round(elapsed_seconds / successes, 6) if successes else ""
            ),
            "metadata_complete_successes": 0,
            "metadata_completeness": 0.0 if successes else "",
            "notes": "json_batch_parse_ok_but_language_generation_translation_metadata_missing",
        }
    )
    return row, None


def _promote_fastest_safe_method(rows: list[dict[str, Any]], *, confirm_run: bool) -> None:
    if not confirm_run:
        return
    by_method = {str(row["method"]): row for row in rows}
    single = by_method.get("api-single")
    session = by_method.get("api-session")
    if not single or not session:
        return
    try:
        single_speed = float(single["seconds_per_successful_transcript"])
        session_speed = float(session["seconds_per_successful_transcript"])
        session_metadata = float(session["metadata_completeness"])
    except (TypeError, ValueError):
        return
    if (
        single_speed > 0
        and 0 < session_speed < single_speed
        and int(session["block_proxy_failures"]) == 0
        and int(session["rate_limited"]) == 0
        and session_metadata >= 1.0
        and int(session["successes"]) > 0
    ):
        session["recommendation"] = "promote"


def _write_markdown(
    path: Path,
    *,
    rows: list[dict[str, Any]],
    input_path: Path,
    proxy_config: ProxyConfig,
    stopped_reason: str | None,
) -> Path:
    lines = [
        "# YouTube Transcript Method Benchmark",
        "",
        f"- Input queue: `{input_path}`",
        f"- Proxy mode resolved: {redact_credentials(proxymode_summary(proxy_config))}",
        f"- Benchmark stopped early: {stopped_reason or 'no'}",
        "- Scope: measurement only; transcripts were not written to `youtube_transcripts`.",
        "",
        "## Method Results",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"### {row['method']}",
                "",
                f"- Run mode: {row['run_mode']}",
                f"- Selected videos: {row['selected_video_count']}",
                f"- Live requests attempted: {row['live_requests_attempted']}",
                f"- Successes: {row['successes']}",
                f"- Terminal failures: {row['terminal_failures']}",
                f"- Transient failures: {row['transient_failures']}",
                f"- Block/proxy failures: {row['block_proxy_failures']}",
                f"- Elapsed seconds: {row['elapsed_seconds']}",
                f"- Seconds per successful transcript: {row['seconds_per_successful_transcript'] or 'N/A'}",
                f"- Metadata completeness: {row['metadata_completeness'] or 'N/A'}",
                f"- Support status: {row['support_status']}",
                f"- Recommendation: {row['recommendation']}",
                f"- Stop reason: {row['stop_reason'] or 'N/A'}",
                f"- Notes: {row['notes']}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def benchmark_youtube_transcript_methods(
    *,
    input_path: Path,
    max_videos: int,
    methods: list[str],
    proxy_mode: str,
    database_url: str | None = None,
    dry_run: bool = False,
    confirm_run: bool = False,
    output_csv_path: Path = DEFAULT_BENCHMARK_CSV_PATH,
    output_md_path: Path = DEFAULT_BENCHMARK_MD_PATH,
) -> TranscriptMethodBenchmarkResult:
    del database_url  # Benchmarking intentionally avoids database writes or reads.
    ensure_data_dirs()
    if dry_run and confirm_run:
        raise ValueError("Use either dry_run or confirm_run, not both.")
    if not dry_run and not confirm_run:
        raise ValueError("Benchmark requires --dry-run or --confirm-run.")
    invalid = [method for method in methods if method not in SUPPORTED_BENCHMARK_METHODS]
    if invalid:
        raise ValueError(
            "Unsupported benchmark methods: "
            + ", ".join(invalid)
            + ". Expected: "
            + ", ".join(SUPPORTED_BENCHMARK_METHODS)
        )
    video_ids = _read_video_ids(input_path, max_videos)
    if not video_ids:
        raise ValueError(f"No benchmarkable video IDs found in queue input: {input_path}")

    proxy_config = resolve_proxy_config(mode=proxy_mode)
    yt_proxy = create_yt_proxy_config(proxy_config)
    settings = get_settings()
    languages = settings.youtube_transcript_language_list
    rows: list[dict[str, Any]] = []
    stopped_reason: str | None = None

    for method in methods:
        if dry_run:
            rows.append(
                _empty_row(
                    method,
                    run_mode="dry_run",
                    selected=len(video_ids),
                    notes="dry_run_no_live_requests",
                )
            )
            continue
        if stopped_reason:
            rows.append(
                _empty_row(
                    method,
                    run_mode="confirm_run",
                    selected=len(video_ids),
                    notes=f"skipped_after_prior_stop:{stopped_reason}",
                )
            )
            continue
        if method in {"api-single", "api-session"}:
            row, method_stop = _run_api_method(
                method=method,
                video_ids=video_ids,
                proxy_config=yt_proxy,
                allow_translation=True,
                languages=languages,
            )
        else:
            row, method_stop = _run_package_cli_batch(
                video_ids=video_ids,
                proxy_config=proxy_config,
                languages=languages,
            )
        rows.append(row)
        if method_stop:
            stopped_reason = method_stop

    _promote_fastest_safe_method(rows, confirm_run=confirm_run)
    _write_csv(output_csv_path, rows)
    _write_markdown(
        output_md_path,
        rows=rows,
        input_path=input_path,
        proxy_config=proxy_config,
        stopped_reason=stopped_reason,
    )
    return TranscriptMethodBenchmarkResult(
        csv_path=output_csv_path,
        markdown_path=output_md_path,
        rows=tuple(rows),
        stopped_reason=stopped_reason,
    )
