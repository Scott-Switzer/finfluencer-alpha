#!/usr/bin/env python3
"""Run dry-run or tiny canary for selected YouTube Apify transcript provider."""
from __future__ import annotations

import csv
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finfluencer_alpha.apify_transcripts import collect_apify_transcripts  # noqa: E402
from finfluencer_alpha.db import connect  # noqa: E402

OUT_DIR = ROOT / "data" / "exports" / "overnight_collection"
QUEUE_CSV = OUT_DIR / "50_youtube_transcript_expansion_queue.csv"
PLAN_CSV = OUT_DIR / "51_youtube_apify_provider_plan.csv"
OUT_CSV = OUT_DIR / "52_youtube_apify_canary_report.csv"
OUT_MD = OUT_DIR / "52_youtube_apify_canary_report.md"
DECISION_MD = OUT_DIR / "56_youtube_apify_canary_decision.md"


@dataclass
class CanaryRow:
    video_id: str
    provider: str
    dry_run: str
    attempted: str
    imported: str
    error_type: str
    error_message: str
    has_text: str
    has_video_id: str
    has_timestamps: str
    language: str
    is_generated: str
    decision: str


def _truthy(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _selected_provider() -> str:
    env = os.getenv("YOUTUBE_APIFY_SELECTED_PROVIDER", "").strip()
    if env:
        return env
    if PLAN_CSV.exists():
        with PLAN_CSV.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("selected") == "1":
                    return row.get("actor_id", "").strip()
    return "supreme_coder/youtube-transcript-scraper"


def _queue_ids(limit: int) -> list[str]:
    if not QUEUE_CSV.exists():
        return []
    out: list[str] = []
    with QUEUE_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            vid = (row.get("video_id") or "").strip()
            if not vid:
                continue
            out.append(vid)
            if len(out) >= limit:
                break
    return out


def _transcript_snapshot(video_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not video_ids:
        return {}
    placeholders = ",".join("?" for _ in video_ids)
    q = f"""
        SELECT video_id, status, language, is_generated, full_text, segment_count, error_type, error_message
        FROM youtube_transcripts
        WHERE video_id IN ({placeholders})
    """
    out: dict[str, dict[str, Any]] = {}
    with connect() as conn:
        for row in conn.execute(q, video_ids).fetchall():
            out[str(row["video_id"])] = dict(row)
    return out


def _map_error(status: str, error_type: str, error_message: str) -> str:
    s = (status or "").lower()
    t = (error_type or "").lower()
    m = (error_message or "").lower()
    if "invalid-input" in m or "field input." in m or "schema" in m:
        return "SchemaMismatch"
    if "no_transcript" in t or "no transcript" in m:
        return "TranscriptNotFound"
    if "age" in m and "restrict" in m:
        return "AgeRestricted"
    if "unavailable" in s or "unavailable" in m:
        return "VideoUnavailable"
    if "ip_blocked" in s or "ip blocked" in m:
        return "IpBlocked"
    if "timeout" in m or "timed_out" in s:
        return "Timeout"
    if "schema" in m or "malformed" in m:
        return "SchemaMismatch"
    if "empty" in m:
        return "EmptyTranscript"
    return "UnknownError"


def _write_decision_report(
    *,
    provider: str,
    dry_run: bool,
    video_count: int,
    imported_count: int,
    rows: list[CanaryRow],
    run_error: str,
    cap_usd: float,
    observed_spend_usd: float,
) -> None:
    fail_counts: dict[str, int] = {}
    for row in rows:
        if row.imported == "1":
            continue
        fail_counts[row.decision] = fail_counts.get(row.decision, 0) + 1
    attempted = sum(int(r.attempted or "0") for r in rows)
    success_rate = (imported_count / attempted) if attempted else 0.0
    cost_per_success = (observed_spend_usd / imported_count) if imported_count else 0.0
    passed = bool(dry_run) or (imported_count > 0 or any(
        r.decision in {"TranscriptNotFound", "VideoUnavailable", "AgeRestricted", "IpBlocked", "Timeout"}
        for r in rows
    )) and not run_error
    lines = [
        "# YouTube Apify canary decision",
        "",
        f"Generated (UTC): `{datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}`",
        "",
        f"- Selected provider: `{provider}`",
        f"- Dry-run: `{dry_run}`",
        f"- Videos targeted: `{video_count}`",
        f"- Videos attempted: `{attempted}`",
        f"- Successful transcripts imported: `{imported_count}`",
        f"- Observed spend (USD): `{round(observed_spend_usd, 6)}`",
        f"- Session cap (USD): `{cap_usd}`",
        f"- Success rate: `{round(success_rate, 4)}`",
        f"- Cost per successful transcript (USD): `{round(cost_per_success, 6) if imported_count else 'n/a'}`",
        f"- Canary result: `{'PASS' if passed else 'FAIL'}`",
        f"- Overnight allowed: `{'yes' if passed and not dry_run else 'no'}`",
        "",
    ]
    if run_error:
        lines += [
            "## Run-level error",
            "",
            f"- `{run_error}`",
            "",
        ]
    if fail_counts:
        lines += [
            "## Failure counts by type",
            "",
        ]
        for k in sorted(fail_counts.keys()):
            lines.append(f"- `{k}`: `{fail_counts[k]}`")
        lines.append("")
    DECISION_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dry_run = not _truthy(os.getenv("RUN_YOUTUBE_APIFY_TRANSCRIPT_CANARY", "0"))
    limit = int(os.getenv("YOUTUBE_APIFY_CANARY_MAX_VIDEOS", "10") or 10)
    if limit < 5:
        limit = 5
    if limit > 10:
        limit = 10
    max_charge = float(os.getenv("YOUTUBE_APIFY_CANARY_CAP_USD", "0.10") or 0.10)
    provider = _selected_provider()
    video_ids = _queue_ids(limit)
    started = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    run_error = ""
    observed_spend_usd = 0.0

    if not dry_run and video_ids:
        try:
            result = collect_apify_transcripts(
                video_ids=video_ids,
                actor_id=provider,
                batch_size=10,
                max_total_charge_usd=max_charge,
                dry_run=False,
            )
            observed_spend_usd = float(result.cost_usd or 0.0)
        except Exception as exc:  # noqa: BLE001 - explicit failure report path
            run_error = str(exc)
    after = _transcript_snapshot(video_ids)

    rows: list[CanaryRow] = []
    imported_count = 0
    for vid in video_ids:
        a = after.get(vid, {})
        status = str(a.get("status") or "")
        text = str(a.get("full_text") or "")
        seg_count = int(a.get("segment_count") or 0)
        imported = (not dry_run) and not run_error and status == "available" and bool(text.strip())
        if imported:
            imported_count += 1
        err_type = str(a.get("error_type") or "")
        err_msg = str(a.get("error_message") or run_error or "")
        decision = "IMPORTED" if imported else ("DRY_RUN_NO_CALL" if dry_run else _map_error(status, err_type, err_msg))
        rows.append(
            CanaryRow(
                video_id=vid,
                provider=provider,
                dry_run="1" if dry_run else "0",
                attempted="0" if dry_run else "1" if video_ids else "0",
                imported="1" if imported else "0",
                error_type=err_type,
                error_message=err_msg[:220],
                has_text=str(bool(text.strip())).lower(),
                has_video_id=str(bool(vid)).lower(),
                has_timestamps=str(seg_count > 0).lower(),
                language=str(a.get("language") or ""),
                is_generated=str(a.get("is_generated") if a.get("is_generated") is not None else ""),
                decision=decision,
            )
        )

    fields = list(CanaryRow.__annotations__.keys())
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r.__dict__)

    lines = [
        "# YouTube Apify transcript canary report",
        "",
        f"Started (UTC): `{started}`",
        f"Provider: `{provider}`",
        f"Dry-run: `{dry_run}`",
        f"Video count: `{len(video_ids)}`",
        f"Imported transcripts: `{imported_count}`",
        f"Observed spend USD: `{round(observed_spend_usd, 6)}`",
        f"Session cap USD: `{max_charge}`",
        "",
    ]
    if run_error:
        lines.append(f"- run_error=`{run_error[:400]}`")
        lines.append("")
    for r in rows:
        lines.append(
            f"- `{r.video_id}` attempted={r.attempted} imported={r.imported} "
            f"has_text={r.has_text} has_timestamps={r.has_timestamps} decision=`{r.decision}`"
        )
    OUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    _write_decision_report(
        provider=provider,
        dry_run=dry_run,
        video_count=len(video_ids),
        imported_count=imported_count,
        rows=rows,
        run_error=run_error,
        cap_usd=max_charge,
        observed_spend_usd=observed_spend_usd,
    )
    print(f"WROTE_CSV={_display_path(OUT_CSV)}")
    print(f"WROTE_MD={_display_path(OUT_MD)}")
    print(f"WROTE_DECISION={_display_path(DECISION_MD)}")
    print(f"DRY_RUN={dry_run}")


if __name__ == "__main__":
    main()
