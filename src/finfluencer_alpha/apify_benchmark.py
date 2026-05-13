from __future__ import annotations

import csv
import statistics
from dataclasses import dataclass
from pathlib import Path

from .apify_queue import select_apify_transcript_queue
from .apify_transcripts import (
    APIFY_ACTOR_SPECS,
    _canonical_actor_id,
    _chunks,
    _fetch_run_results,
    _normalize_apify_output,
    _resolve_apify_token,
    _start_apify_run,
    _utc_now_iso,
    _wait_for_run,
)
from .config import EXPORTS_DIR, ensure_data_dirs

APIFY_BENCHMARK_DIR = EXPORTS_DIR / "transcripts"
DEFAULT_APIFY_BENCHMARK_CSV = APIFY_BENCHMARK_DIR / "apify_actor_benchmark.csv"
DEFAULT_APIFY_BENCHMARK_MD = APIFY_BENCHMARK_DIR / "apify_actor_benchmark.md"


@dataclass(frozen=True)
class ApifyActorBenchmarkResult:
    actor_rows: list[dict[str, object]]
    selected_video_ids: list[str]
    csv_path: Path
    markdown_path: Path


def _float_or_blank(value: float | None) -> float | str:
    return "" if value is None else round(value, 6)


def _distribution(values: list[int]) -> str:
    if not values:
        return "n/a"
    return (
        f"min={min(values)};"
        f"median={int(statistics.median(values))};"
        f"max={max(values)}"
    )


def _recommendation(
    *,
    success_rate: float,
    malformed_outputs: int,
    empty_transcripts: int,
    cost_per_success: float | None,
) -> str:
    if malformed_outputs:
        return "deprioritize: malformed output observed"
    if empty_transcripts:
        return "inspect: empty transcript failures observed"
    if success_rate >= 0.8 and (cost_per_success is None or cost_per_success <= 0.01):
        return "promote: strongest fallback candidate"
    if success_rate >= 0.5:
        return "usable: benchmark on a larger missing-video slice"
    return "deprioritize: weak recovery rate"


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "actor_id",
        "price_signal",
        "attempted",
        "successful_transcripts",
        "failures",
        "empty_transcripts",
        "malformed_outputs",
        "success_rate",
        "cost_usd",
        "cost_per_success_usd",
        "timestamp_availability",
        "text_length_distribution",
        "schema_fields_observed",
        "recommendation",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, rows: list[dict[str, object]], selected_count: int) -> None:
    lines = [
        "# Apify Transcript Actor Benchmark",
        "",
        f"Selected missing/failure video IDs: {selected_count}",
        "",
        "| Actor | Attempted | Successes | Success rate | Cost USD | Cost/success | Recommendation |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row['actor_id']} | {row['attempted']} | {row['successful_transcripts']} | "
            f"{row['success_rate']} | {row['cost_usd']} | {row['cost_per_success_usd']} | "
            f"{row['recommendation']} |"
        )
    lines.extend(["", "## Details", ""])
    for row in rows:
        lines.extend(
            [
                f"### {row['actor_id']}",
                f"- Price signal: {row['price_signal']}",
                f"- Failures: {row['failures']}",
                f"- Empty transcripts: {row['empty_transcripts']}",
                f"- Malformed outputs: {row['malformed_outputs']}",
                f"- Timestamp availability: {row['timestamp_availability']}",
                f"- Text length distribution: {row['text_length_distribution']}",
                f"- Schema fields observed: {row['schema_fields_observed']}",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def benchmark_apify_transcript_actors(
    *,
    actors: list[str],
    start_date: str,
    end_date: str,
    max_videos_per_actor: int,
    batch_size: int,
    max_total_charge_usd: float,
    only_missing_transcripts: bool = True,
) -> ApifyActorBenchmarkResult:
    if not actors:
        raise ValueError("At least one Apify actor is required.")
    if max_total_charge_usd <= 0:
        raise ValueError("max_total_charge_usd must be positive.")
    if not only_missing_transcripts:
        raise ValueError("Benchmarking currently supports only missing/failure transcripts.")

    ensure_data_dirs()
    APIFY_BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    api_token = _resolve_apify_token()

    queue = select_apify_transcript_queue(
        start_date=start_date,
        end_date=end_date,
        max_videos=max_videos_per_actor,
    )
    selected_video_ids = [selection.video_id for selection in queue.selected]
    if not selected_video_ids:
        rows: list[dict[str, object]] = []
        _write_csv(DEFAULT_APIFY_BENCHMARK_CSV, rows)
        _write_markdown(DEFAULT_APIFY_BENCHMARK_MD, rows, 0)
        return ApifyActorBenchmarkResult(
            actor_rows=rows,
            selected_video_ids=[],
            csv_path=DEFAULT_APIFY_BENCHMARK_CSV,
            markdown_path=DEFAULT_APIFY_BENCHMARK_MD,
        )

    per_actor_cap = max_total_charge_usd / len(actors)
    rows: list[dict[str, object]] = []

    for actor_id in actors:
        canonical_actor_id = _canonical_actor_id(actor_id)
        spec = APIFY_ACTOR_SPECS.get(canonical_actor_id)
        actor_batch_size = max(1, batch_size)
        if spec and spec.max_urls_per_run is not None:
            actor_batch_size = min(actor_batch_size, spec.max_urls_per_run)

        all_results = []
        all_failures = []
        schema_fields: set[str] = set()
        actor_costs: list[float] = []
        retrieved_at = _utc_now_iso()

        for video_batch in _chunks(selected_video_ids, actor_batch_size):
            video_urls = [
                f"https://www.youtube.com/watch?v={video_id}"
                for video_id in video_batch
            ]
            run_response = _start_apify_run(
                canonical_actor_id,
                video_urls,
                api_token,
                max_total_charge_usd=per_actor_cap,
            )
            apify_run_id = str(
                run_response.get("data", {}).get("id") or run_response.get("id") or ""
            ).strip()
            run_status = _wait_for_run(apify_run_id, api_token)
            raw_cost = run_status.get("usageTotalUsd") or run_status.get("stats", {}).get(
                "totalCostUsd"
            )
            if raw_cost:
                try:
                    actor_costs.append(float(raw_cost))
                except (TypeError, ValueError):
                    pass
            raw_results = _fetch_run_results(apify_run_id, api_token)
            for item in raw_results:
                if isinstance(item, dict):
                    schema_fields.update(str(key) for key in item)
            results, failures = _normalize_apify_output(
                raw_results,
                set(video_batch),
                actor_id=canonical_actor_id,
                retrieved_at=retrieved_at,
                provider_run_id=apify_run_id,
            )
            all_results.extend(results)
            all_failures.extend(failures)

        attempted = len(selected_video_ids)
        successful = len(all_results)
        failures = len(all_failures)
        empty_transcripts = sum(
            1
            for failure in all_failures
            if str(failure.get("error_type")) == "no_transcript"
            and any(
                marker in str(failure.get("error_message", "")).lower()
                for marker in ("empty", "no transcript text or segments")
            )
        )
        malformed_outputs = sum(
            1
            for failure in all_failures
            if str(failure.get("error_type")) in {"malformed_output", "duplicate_result"}
        )
        success_rate_value = successful / attempted if attempted else 0.0
        cost = round(sum(actor_costs), 6) if actor_costs else 0.0
        cost_per_success = cost / successful if successful else None
        timestamp_successes = sum(1 for result in all_results if result.segment_count > 0)
        timestamp_availability = (
            f"{timestamp_successes}/{successful}"
            if successful
            else "0/0"
        )
        lengths = [int(result.character_count or 0) for result in all_results]
        recommendation = _recommendation(
            success_rate=success_rate_value,
            malformed_outputs=malformed_outputs,
            empty_transcripts=empty_transcripts,
            cost_per_success=cost_per_success,
        )
        row: dict[str, object] = {
            "actor_id": canonical_actor_id,
            "price_signal": spec.price_signal if spec else "not catalogued",
            "attempted": attempted,
            "successful_transcripts": successful,
            "failures": failures,
            "empty_transcripts": empty_transcripts,
            "malformed_outputs": malformed_outputs,
            "success_rate": round(success_rate_value, 6),
            "cost_usd": round(cost, 6),
            "cost_per_success_usd": _float_or_blank(cost_per_success),
            "timestamp_availability": timestamp_availability,
            "text_length_distribution": _distribution(lengths),
            "schema_fields_observed": ",".join(sorted(schema_fields)),
            "recommendation": recommendation,
        }
        rows.append(row)

    rows.sort(
        key=lambda row: (
            float(row["cost_per_success_usd"])
            if row["cost_per_success_usd"] != ""
            else float("inf"),
            -float(row["success_rate"]),
            str(row["actor_id"]),
        )
    )
    _write_csv(DEFAULT_APIFY_BENCHMARK_CSV, rows)
    _write_markdown(DEFAULT_APIFY_BENCHMARK_MD, rows, len(selected_video_ids))
    return ApifyActorBenchmarkResult(
        actor_rows=rows,
        selected_video_ids=selected_video_ids,
        csv_path=DEFAULT_APIFY_BENCHMARK_CSV,
        markdown_path=DEFAULT_APIFY_BENCHMARK_MD,
    )
