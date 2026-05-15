#!/usr/bin/env python3
"""Autonomous YouTube transcript expansion orchestrator."""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "exports" / "overnight_collection"
QUEUE_CSV = OUT_DIR / "50_youtube_transcript_expansion_queue.csv"
LEDGER_CSV = OUT_DIR / "apify_key_usage_ledger.csv"
RUNNER_STATUS_MD = OUT_DIR / "53_youtube_apify_overnight_live_status.md"
STATUS_MD = OUT_DIR / "62_youtube_autonomous_expansion_live_status.md"
STATUS_CSV = OUT_DIR / "62_youtube_autonomous_expansion_live_status.csv"
FINAL_MD = OUT_DIR / "63_youtube_autonomous_expansion_final_report.md"
FINAL_CSV = OUT_DIR / "63_youtube_autonomous_expansion_final_report.csv"

sys.path.insert(0, str(ROOT / "src"))
from finfluencer_alpha.db import connect  # noqa: E402


@dataclass
class CycleMetrics:
    cycle: int
    queue_before: int
    queue_after: int
    attempted: int
    imported: int
    perm_fail: int
    trans_fail: int
    spend_total_usd: float
    spend_by_slot_json: str
    token_slot: str
    accepted_start: int
    accepted_end: int
    new_accepted: int
    new_videos_discovered: int
    new_creators_discovered: int
    success_rate: float
    cost_per_transcript: float
    cost_per_accepted_event: float
    decision: str
    stop_reason: str
    youtube_quota_estimated: int


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _truthy(v: str | None) -> bool:
    return _clean(v).lower() in {"1", "true", "yes", "on", "y"}


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _run(cmd: list[str], env: dict[str, str] | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout + "\n" + proc.stderr).strip()


def _queue_size() -> int:
    if not QUEUE_CSV.exists():
        return 0
    with QUEUE_CSV.open(newline="", encoding="utf-8") as fh:
        rows = csv.reader(fh)
        try:
            next(rows)
        except StopIteration:
            return 0
        return sum(1 for _ in rows)


def _accepted_events() -> int:
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM transcript_recommendation_events").fetchone()
        return int(row["n"] or 0)


def _head_commit() -> str:
    code, out = _run(["git", "rev-parse", "--short", "HEAD"])
    return out.strip() if code == 0 else "unknown"


def _ledger_spend_snapshot() -> tuple[float, dict[str, float]]:
    if not LEDGER_CSV.exists():
        return 0.0, {}
    total = 0.0
    by_slot: dict[str, float] = {}
    with LEDGER_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if _clean(row.get("platform")).lower() != "youtube":
                continue
            cost = float(row.get("cost_usd") or 0.0)
            total += cost
            key = _clean(row.get("key_label")) or "unknown"
            by_slot[key] = by_slot.get(key, 0.0) + cost
    return total, by_slot


def _slot_number(label: str) -> str:
    text = _clean(label)
    m = re.search(r"(\d+)$", text)
    return m.group(1) if m else "unknown"


def _status_from_runner() -> dict[str, str]:
    if not RUNNER_STATUS_MD.exists():
        return {}
    out: dict[str, str] = {}
    for line in RUNNER_STATUS_MD.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip().strip("`")
    return out


def _append_status_row(row: CycleMetrics) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = list(CycleMetrics.__annotations__.keys())
    exists = STATUS_CSV.exists()
    with STATUS_CSV.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        if not exists:
            w.writeheader()
        w.writerow(row.__dict__)

    lines = [
        "# YouTube autonomous expansion live status",
        "",
        f"started_at: `{_now()}`",
        f"current_cycle: `{row.cycle}`",
        f"current_HEAD: `{_head_commit()}`",
        f"current_provider: `{os.getenv('YOUTUBE_APIFY_SELECTED_PROVIDER', 'supreme_coder/youtube-transcript-scraper')}`",
        f"current_token_slot_number_only: `{row.token_slot}`",
        f"apify_spend_estimate_usd: `{round(row.spend_total_usd, 6)}`",
        f"apify_spend_by_token_slot_number_only: `{row.spend_by_slot_json}`",
        f"youtube_quota_estimate_observed: `{row.youtube_quota_estimated}`",
        f"queue_size_before_cycle: `{row.queue_before}`",
        f"queue_remaining_after_cycle: `{row.queue_after}`",
        f"videos_attempted: `{row.attempted}`",
        f"transcripts_imported: `{row.imported}`",
        f"duplicate_existing_skipped: `{max(0, row.attempted - row.imported - row.perm_fail - row.trans_fail)}`",
        f"permanent_failures: `{row.perm_fail}`",
        f"transient_failures: `{row.trans_fail}`",
        f"transcript_success_rate: `{round(row.success_rate, 4)}`",
        f"beginning_accepted_events: `{row.accepted_start}`",
        f"ending_accepted_events: `{row.accepted_end}`",
        f"new_accepted_events: `{row.new_accepted}`",
        f"cost_per_transcript: `{round(row.cost_per_transcript, 6) if row.imported else 'n/a'}`",
        f"cost_per_accepted_event: `{round(row.cost_per_accepted_event, 6) if row.new_accepted else 'n/a'}`",
        f"new_videos_discovered: `{row.new_videos_discovered}`",
        f"new_creators_discovered: `{row.new_creators_discovered}`",
        f"decision: `{row.decision}`",
        f"stop_reason: `{row.stop_reason}`",
        "",
    ]
    STATUS_MD.write_text("\n".join(lines), encoding="utf-8")


def _write_final_report(rows: list[CycleMetrics], stop_reason: str) -> None:
    total_attempted = sum(r.attempted for r in rows)
    total_imported = sum(r.imported for r in rows)
    total_new_events = sum(r.new_accepted for r in rows)
    total_new_videos = sum(r.new_videos_discovered for r in rows)
    total_new_creators = sum(r.new_creators_discovered for r in rows)
    spend = rows[-1].spend_total_usd if rows else 0.0
    lines = [
        "# YouTube autonomous expansion final report",
        "",
        f"generated_at: `{_now()}`",
        f"cycles_completed: `{len(rows)}`",
        f"total_attempted: `{total_attempted}`",
        f"total_imported: `{total_imported}`",
        f"total_new_accepted_events: `{total_new_events}`",
        f"total_new_videos_discovered: `{total_new_videos}`",
        f"total_new_creators_discovered: `{total_new_creators}`",
        f"final_apify_spend_estimate_usd: `{round(spend, 6)}`",
        f"stop_reason: `{stop_reason}`",
        "",
    ]
    FINAL_MD.write_text("\n".join(lines), encoding="utf-8")
    with FINAL_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["metric", "value"],
            lineterminator="\n",
        )
        w.writeheader()
        for metric, value in [
            ("cycles_completed", len(rows)),
            ("total_attempted", total_attempted),
            ("total_imported", total_imported),
            ("total_new_accepted_events", total_new_events),
            ("total_new_videos_discovered", total_new_videos),
            ("total_new_creators_discovered", total_new_creators),
            ("final_apify_spend_estimate_usd", round(spend, 6)),
            ("stop_reason", stop_reason),
        ]:
            w.writerow({"metric": metric, "value": value})


def main() -> None:
    live = _truthy(os.getenv("RUN_YOUTUBE_AUTONOMOUS_EXPANSION"))
    dry_run_api_enable = _truthy(os.getenv("YOUTUBE_AUTONOMOUS_DRYRUN_ENABLE_APIS", "0"))
    dry_run_youtube_api_enable = _truthy(
        os.getenv("YOUTUBE_AUTONOMOUS_DRYRUN_ENABLE_YOUTUBE_API_CALLS", "0")
    )
    max_cycles = int(os.getenv("YOUTUBE_AUTONOMOUS_MAX_CYCLES", "20") or 20)
    min_new_videos = int(os.getenv("YOUTUBE_AUTONOMOUS_MIN_NEW_VIDEOS_TO_CONTINUE", "100") or 100)
    min_success_rate = float(os.getenv("YOUTUBE_AUTONOMOUS_MIN_TRANSCRIPT_SUCCESS_RATE", "0.10") or 0.10)
    min_event_yield = float(os.getenv("YOUTUBE_AUTONOMOUS_MIN_ACCEPTED_EVENT_YIELD", "0.00") or 0.00)
    enable_metadata_expansion = _truthy(os.getenv("YOUTUBE_AUTONOMOUS_ENABLE_METADATA_EXPANSION", "1"))
    queue_rows = int(os.getenv("YOUTUBE_AUTONOMOUS_MAX_QUEUE_ROWS", "50000") or 50000)

    if not live and not dry_run_api_enable:
        print("DRY_RUN_PLAN_ONLY=1")
    cycles: list[CycleMetrics] = []
    stop_reason = "max_cycles_reached"

    for cycle in range(1, max_cycles + 1):
        queue_before = _queue_size()
        accepted_start = _accepted_events()
        spend_before, _slot_before = _ledger_spend_snapshot()
        quota_estimate = 0
        new_vids = 0
        new_creators = 0
        runner_status: dict[str, str] = {}

        if live or dry_run_api_enable:
            env = os.environ.copy()
            env.setdefault("YOUTUBE_APIFY_SELECTED_PROVIDER", "supreme_coder/youtube-transcript-scraper")
            if not live:
                env["RUN_YOUTUBE_APIFY_OVERNIGHT"] = "0"
            code, out = _run(["python", "scripts/run_youtube_apify_transcript_overnight.py"], env=env)
            runner_status = _status_from_runner()
            if code != 0 and live:
                stop_reason = f"runner_failed_cycle_{cycle}"
                # still continue to reporting for this cycle

            _run(["python", "-m", "finfluencer_alpha", "build-transcript-events", "--refresh-existing"])
            _run(["python", "-m", "finfluencer_alpha", "export-transcript-events"])
            _run(["python", "scripts/summarize_youtube_transcript_expansion.py"])
            _ = out

        queue_after = _queue_size()
        if enable_metadata_expansion and (queue_after < min_new_videos):
            if live or dry_run_youtube_api_enable:
                env = os.environ.copy()
                env["RUN_YOUTUBE_AUTONOMOUS_EXPANSION"] = "1" if live else "0"
                env["YOUTUBE_AUTONOMOUS_CYCLE_ID"] = f"cycle_{cycle}"
                code, _out = _run(["python", "scripts/expand_youtube_stock_picker_universe.py"], env=env)
                if code == 0:
                    expansion_csv = ROOT / "data/exports/overnight_collection/61_youtube_dynamic_metadata_expansion.csv"
                    if expansion_csv.exists():
                        with expansion_csv.open(newline="", encoding="utf-8") as fh:
                            rows = list(csv.DictReader(fh))
                        new_vids = len({r["video_id"] for r in rows if r.get("included_in_queue") == "1"})
                        new_creators = len({r["channel_id"] for r in rows if r.get("included_in_queue") == "1"})
                        quota_estimate = sum(int(r.get("youtube_quota_estimated") or 0) for r in rows)
                _run(
                    ["python", "scripts/build_youtube_transcript_expansion_queue.py"],
                    env={
                        **os.environ,
                        "YOUTUBE_TRANSCRIPT_QUEUE_MAX_ROWS": str(queue_rows),
                        "YOUTUBE_TRANSCRIPT_QUEUE_EXPANSION_MODE": "exhaustive",
                    },
                )
                queue_after = _queue_size()

        spend_after, slot_after = _ledger_spend_snapshot()
        runner_decision = _clean(runner_status.get("recommended_continue_stop_decision"))
        attempted = int(float(runner_status.get("videos_attempted", "0") or 0))
        imported = int(float(runner_status.get("transcripts_imported", "0") or 0))
        perm_fail = int(float(runner_status.get("permanent_failures", "0") or 0))
        trans_fail = int(float(runner_status.get("transient_failures", "0") or 0))
        token_slot = _slot_number(runner_status.get("current_token_slot", "none"))
        accepted_end = _accepted_events()
        new_accepted = max(0, accepted_end - accepted_start)
        cycle_spend = max(0.0, spend_after - spend_before)
        success_rate = (imported / attempted) if attempted else 0.0
        event_yield = (new_accepted / imported) if imported else 0.0
        cost_per_transcript = (cycle_spend / imported) if imported else 0.0
        cost_per_accepted = (cycle_spend / new_accepted) if new_accepted else 0.0

        metric = CycleMetrics(
            cycle=cycle,
            queue_before=queue_before,
            queue_after=queue_after,
            attempted=attempted,
            imported=imported,
            perm_fail=perm_fail,
            trans_fail=trans_fail,
            spend_total_usd=spend_after,
            spend_by_slot_json=json.dumps(
                {
                    _slot_number(k): round(v, 6)
                    for k, v in slot_after.items()
                },
                sort_keys=True,
            ),
            token_slot=token_slot,
            accepted_start=accepted_start,
            accepted_end=accepted_end,
            new_accepted=new_accepted,
            new_videos_discovered=new_vids,
            new_creators_discovered=new_creators,
            success_rate=success_rate,
            cost_per_transcript=cost_per_transcript,
            cost_per_accepted_event=cost_per_accepted,
            decision="continue",
            stop_reason="",
            youtube_quota_estimated=quota_estimate,
        )

        if queue_after <= 0 and new_vids < min_new_videos:
            metric.decision = "stop"
            metric.stop_reason = "queue_depleted_and_low_new_discovery"
            stop_reason = metric.stop_reason
        elif runner_decision in {
            "STOP_ALL_KEYS_EXHAUSTED",
            "STOP_NO_PICKABLE_KEY",
            "STOP_BUDGET_EXHAUSTED",
        }:
            metric.decision = "stop"
            metric.stop_reason = "runner_reported_key_or_budget_stop"
            stop_reason = metric.stop_reason
        elif runner_decision in {
            "STOP_PROVIDER_FAILURE",
            "STOP_REPEATED_PROVIDER_FAILURE",
        }:
            metric.decision = "stop"
            metric.stop_reason = "runner_reported_provider_stop"
            stop_reason = metric.stop_reason
        elif runner_decision in {
            "STOP_LOW_SUCCESS_RATE",
            "STOP_LOW_ACCEPTED_EVENT_RATE",
        }:
            metric.decision = "stop"
            metric.stop_reason = "runner_reported_quality_floor_stop"
            stop_reason = metric.stop_reason
        elif live and attempted >= 100 and success_rate < min_success_rate:
            metric.decision = "stop"
            metric.stop_reason = "success_rate_below_floor"
            stop_reason = metric.stop_reason
        elif live and imported > 0 and event_yield < min_event_yield:
            metric.decision = "stop"
            metric.stop_reason = "accepted_event_yield_below_floor"
            stop_reason = metric.stop_reason
        elif cycle == max_cycles:
            metric.decision = "stop"
            metric.stop_reason = "max_cycles_reached"
            stop_reason = metric.stop_reason
        cycles.append(metric)
        _append_status_row(metric)
        if metric.decision == "stop":
            break

    _write_final_report(cycles, stop_reason)
    print(f"WROTE_STATUS_MD={_display_path(STATUS_MD)}")
    print(f"WROTE_STATUS_CSV={_display_path(STATUS_CSV)}")
    print(f"WROTE_FINAL_MD={_display_path(FINAL_MD)}")
    print(f"WROTE_FINAL_CSV={_display_path(FINAL_CSV)}")
    print(f"CYCLES_COMPLETED={len(cycles)}")


if __name__ == "__main__":
    main()
