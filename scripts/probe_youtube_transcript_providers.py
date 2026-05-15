#!/usr/bin/env python3
"""Probe multiple YouTube transcript Apify actors with schema-aware canaries."""
from __future__ import annotations

import csv
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finfluencer_alpha.apify_key_manager import ApifyBudgetError, ApifyKeyManager  # noqa: E402
from finfluencer_alpha.youtube_transcript_provider_registry import (  # noqa: E402
    get_all_provider_profiles,
    parse_provider_output_item,
    schema_summary,
)

APIFY_BASE = "https://api.apify.com/v2"
OUT_DIR = ROOT / "data" / "exports" / "overnight_collection"
PROBE_CSV = OUT_DIR / "75_youtube_provider_probe.csv"
PROBE_MD = OUT_DIR / "75_youtube_provider_probe.md"
DEFAULT_RETRY_QUEUE = OUT_DIR / "71_youtube_transcript_retry_queue.csv"

CANDIDATES = [
    "supreme_coder/youtube-transcript-scraper",
    "insight_api_labs/youtube-transcript",
    "topaz_sharingan/Youtube-Transcript-Scraper-1",
    "topaz_sharingan/Youtube-Transcript-Scraper",
    "starvibe/youtube-video-transcript",
    "scrape-creators/best-youtube-transcripts-scraper",
    "zerohour/yt-transcript",
    "optimus-fulcria/youtube-transcript-extractor",
    "akash9078/youtube-transcript-extractor",
    "johnvc/YoutubeTranscripts",
]


@dataclass
class ProbeRow:
    provider_key: str
    actor_id: str
    actor_permission_level: str
    token_slot_number: str
    attempted: int
    start_http_status: str
    apify_error_type: str
    run_status: str
    dataset_items: int
    transcripts_importable: int
    permanent_video_failures: int
    transient_video_failures: int
    provider_failures: int
    observed_spend: float
    selected_for_recovery: int
    decision: str
    reason: str
    input_schema_summary: str
    output_schema_summary: str

    def as_dict(self) -> dict[str, object]:
        return {
            "provider_key": self.provider_key,
            "actor_id": self.actor_id,
            "actor_permission_level": self.actor_permission_level,
            "token_slot_number": self.token_slot_number,
            "attempted": self.attempted,
            "start_http_status": self.start_http_status,
            "apify_error_type": self.apify_error_type,
            "run_status": self.run_status,
            "dataset_items": self.dataset_items,
            "transcripts_importable": self.transcripts_importable,
            "permanent_video_failures": self.permanent_video_failures,
            "transient_video_failures": self.transient_video_failures,
            "provider_failures": self.provider_failures,
            "observed_spend": round(self.observed_spend, 6),
            "selected_for_recovery": self.selected_for_recovery,
            "decision": self.decision,
            "reason": self.reason,
            "input_schema_summary": self.input_schema_summary,
            "output_schema_summary": self.output_schema_summary,
        }


def _clean(value: object) -> str:
    return str(value or "").strip()


def _truthy(value: str | None) -> bool:
    return _clean(value).lower() in {"1", "true", "yes", "on", "y"}


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_actor(actor_id: str) -> str:
    return actor_id.replace("/", "~", 1) if "/" in actor_id and "~" not in actor_id else actor_id


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _language_mode(value: str) -> list[str]:
    mode = _clean(value).lower() or "english_fallback"
    if mode == "strict_en":
        return ["en"]
    if mode == "broad_fallback":
        return ["en", "en-US", "en-GB", "en-CA", "en-AU"]
    return ["en", "en-US", "en-GB"]


def _load_probe_ids(path: Path, per_provider: int, providers: int) -> list[str]:
    need = max(3, per_provider * max(1, providers))
    ids: list[str] = []
    if not path.exists():
        return ids
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            vid = _clean(row.get("video_id"))
            if not vid or vid in ids:
                continue
            ids.append(vid)
            if len(ids) >= need:
                break
    return ids


def _actor_meta(actor_id: str, token: str) -> dict[str, Any]:
    resp = requests.get(
        f"{APIFY_BASE}/acts/{_normalize_actor(actor_id)}",
        headers=_headers(token),
        timeout=60,
    )
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = {"error": resp.text[:400]}
        return {
            "http_status": resp.status_code,
            "error_type": _clean((body.get("error") or {}).get("type") if isinstance(body, dict) else ""),
            "error_message": _clean((body.get("error") or {}).get("message") if isinstance(body, dict) else body),
            "data": {},
        }
    body = resp.json()
    data = body.get("data") if isinstance(body, dict) else {}
    return {
        "http_status": resp.status_code,
        "error_type": "",
        "error_message": "",
        "data": data if isinstance(data, dict) else {},
    }


def _classify_start_failure(status: int, error_type: str, message: str) -> tuple[str, int]:
    lower = f"{error_type} {message}".lower()
    if status == 401 or "unauthorized" in lower or "invalid token" in lower:
        return "START_FAILED_AUTH", 1
    if status == 402 or any(x in lower for x in ("payment required", "hard limit exceeded", "platform-feature-disabled", "actor-disabled")):
        return "START_FAILED_CREDIT", 1
    if any(x in lower for x in ("actor-is-not-rented", "not rented", "subscription", "rent")):
        return "START_FAILED_RENTAL_REQUIRED", 1
    if status == 403 and any(x in lower for x in ("permission", "forbidden", "full-permission")):
        return "START_FAILED_PERMISSION", 1
    if "invalid-input" in lower or "input is not valid" in lower or "schema" in lower:
        return "START_FAILED_SCHEMA", 1
    return "RUN_FAILED", 1


def _parse_items(actor_id: str, items: list[dict[str, Any]]) -> tuple[int, int, int, str]:
    importable = 0
    permanent = 0
    transient = 0
    schema_keys: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        schema_keys.update(str(k) for k in item.keys())
        parsed = parse_provider_output_item(actor_id, item)
        text = _clean(parsed.get("text"))
        err = _clean(parsed.get("error_text"))
        is_perm = bool(parsed.get("is_permanent_error"))
        if text:
            importable += 1
        elif err:
            if is_perm:
                permanent += 1
            else:
                transient += 1
    return importable, permanent, transient, ",".join(sorted(schema_keys)[:25])


def _write_outputs(rows: list[ProbeRow]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].as_dict().keys()) if rows else [
        "provider_key",
        "actor_id",
        "actor_permission_level",
        "token_slot_number",
        "attempted",
        "start_http_status",
        "apify_error_type",
        "run_status",
        "dataset_items",
        "transcripts_importable",
        "permanent_video_failures",
        "transient_video_failures",
        "provider_failures",
        "observed_spend",
        "selected_for_recovery",
        "decision",
        "reason",
        "input_schema_summary",
        "output_schema_summary",
    ]
    with PROBE_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())

    lines = [
        "# YouTube provider probe",
        "",
        f"Generated UTC: `{_iso_now()}`",
        "",
    ]
    for row in rows:
        lines.append(
            f"- `{row.actor_id}` decision=`{row.decision}` selected={row.selected_for_recovery} "
            f"importable={row.transcripts_importable} run_status=`{row.run_status}` reason=`{row.reason}`"
        )
    PROBE_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    live = _truthy(os.getenv("RUN_YOUTUBE_PROVIDER_PROBE", "0"))
    queue_path = ROOT / os.getenv(
        "YOUTUBE_RETRY_QUEUE_PATH",
        "data/exports/overnight_collection/71_youtube_transcript_retry_queue.csv",
    )
    cap_usd = float(os.getenv("YOUTUBE_PROVIDER_PROBE_CAP_USD", "0.25") or "0.25")
    per_provider = int(os.getenv("YOUTUBE_PROVIDER_PROBE_VIDEOS_PER_PROVIDER", "3") or "3")
    languages = _language_mode(os.getenv("YOUTUBE_PROVIDER_PROBE_LANGUAGE_MODE", "english_fallback"))
    km = ApifyKeyManager.from_env()
    probe_ids = _load_probe_ids(queue_path, per_provider, len(CANDIDATES))
    if not probe_ids:
        _write_outputs([])
        print("NO_PROBE_IDS=1")
        return

    profiles = {p.actor_id: p for p in get_all_provider_profiles()}
    recent_success_actors: list[str] = []
    # Add any prior successful provider actor IDs seen in DB.
    try:
        import sqlite3

        conn = sqlite3.connect(ROOT / "data" / "finfluencer_alpha.db")
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT provider_actor_id, COUNT(*) AS n
            FROM youtube_transcripts
            WHERE status='available' AND COALESCE(provider_actor_id,'')!=''
            GROUP BY provider_actor_id
            ORDER BY n DESC
            LIMIT 10
            """
        ).fetchall()
        conn.close()
        for r in rows:
            aid = _clean(r["provider_actor_id"])
            if aid and aid not in CANDIDATES:
                recent_success_actors.append(aid)
    except Exception:
        recent_success_actors = []

    actors = list(dict.fromkeys(CANDIDATES + recent_success_actors))
    rows: list[ProbeRow] = []
    spent_total = 0.0

    for idx, actor_id in enumerate(actors):
        if spent_total >= cap_usd:
            break
        provider = profiles.get(actor_id)
        provider_key = provider.provider_key if provider else actor_id.replace("/", "_")
        token_slot = "unknown"
        decision = "PROVIDER_UNUSABLE"
        reason = "not_attempted"
        start_http_status = ""
        apify_error_type = ""
        run_status = ""
        dataset_items = 0
        importable = 0
        permanent = 0
        transient = 0
        provider_failures = 0
        observed_spend = 0.0
        input_schema_sig = ""
        output_schema_sig = ""
        actor_permission = "unknown"
        attempted = 0

        try:
            key = km.choose_key(platform="youtube", projected_cost_usd=0.01)
        except ApifyBudgetError:
            rows.append(
                ProbeRow(
                    provider_key=provider_key,
                    actor_id=actor_id,
                    actor_permission_level=actor_permission,
                    token_slot_number=token_slot,
                    attempted=0,
                    start_http_status="",
                    apify_error_type="budget_error",
                    run_status="",
                    dataset_items=0,
                    transcripts_importable=0,
                    permanent_video_failures=0,
                    transient_video_failures=0,
                    provider_failures=1,
                    observed_spend=0.0,
                    selected_for_recovery=0,
                    decision="PROVIDER_UNUSABLE",
                    reason="no_pickable_key",
                    input_schema_summary="",
                    output_schema_summary="",
                )
            )
            continue
        token_slot = "".join(ch for ch in key.label if ch.isdigit()) or "unknown"

        with km.activate_key(key):
            meta = _actor_meta(actor_id, os.environ.get("APIFY_TOKEN", ""))
            data = meta.get("data") if isinstance(meta, dict) else {}
            if not isinstance(data, dict):
                data = {}
            input_schema = data.get("inputSchema") if isinstance(data.get("inputSchema"), dict) else None
            input_schema_sig = schema_summary(input_schema)
            actor_permission = _clean(data.get("actorPermissionLevel") or data.get("access") or "unknown")
            if int(meta.get("http_status") or 0) >= 400:
                start_http_status = str(meta.get("http_status") or "")
                apify_error_type = _clean(meta.get("error_type"))
                decision = "PROVIDER_UNUSABLE"
                reason = "metadata_fetch_failed"
                provider_failures = 1
            elif not live:
                decision = "PROBE_ONLY_DRY_RUN"
                reason = "dry_run_metadata_only"
            else:
                payload = (
                    provider.input_payload_builder(
                        [f"https://www.youtube.com/watch?v={vid}" for vid in probe_ids[idx * per_provider : (idx + 1) * per_provider] or probe_ids[:per_provider]],
                        languages,
                        input_schema,
                    )
                    if provider
                    else {
                        "urls": [{"url": f"https://www.youtube.com/watch?v={vid}"} for vid in probe_ids[:per_provider]],
                        "languages": languages,
                    }
                )
                attempted = len(probe_ids[idx * per_provider : (idx + 1) * per_provider] or probe_ids[:per_provider])
                try:
                    start = requests.post(
                        f"{APIFY_BASE}/acts/{_normalize_actor(actor_id)}/runs",
                        headers=_headers(os.environ.get("APIFY_TOKEN", "")),
                        json=payload,
                        params={"maxTotalChargeUsd": str(max(0.01, min(0.10, cap_usd - spent_total)))},
                        timeout=60,
                    )
                    start_http_status = str(start.status_code)
                    if start.status_code >= 400:
                        try:
                            body = start.json()
                        except Exception:
                            body = {"error": {"message": start.text[:400], "type": ""}}
                        err = body.get("error") if isinstance(body, dict) else {}
                        apify_error_type = _clean((err or {}).get("type"))
                        err_msg = _clean((err or {}).get("message") or body)
                        decision, provider_failures = _classify_start_failure(start.status_code, apify_error_type, err_msg)
                        reason = err_msg[:400]
                    else:
                        run_id = _clean((start.json().get("data") or {}).get("id"))
                        run_status = "RUNNING"
                        run_data: dict[str, Any] = {}
                        for _ in range(120):
                            poll = requests.get(
                                f"{APIFY_BASE}/actor-runs/{run_id}",
                                headers=_headers(os.environ.get("APIFY_TOKEN", "")),
                                timeout=30,
                            )
                            if poll.status_code >= 400:
                                run_status = f"HTTP_{poll.status_code}"
                                decision = "RUN_FAILED"
                                provider_failures = 1
                                reason = f"poll_failed_http_{poll.status_code}"
                                break
                            body = poll.json()
                            run_data = body.get("data") if isinstance(body, dict) else {}
                            run_status = _clean((run_data or {}).get("status"))
                            if run_status in {"SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"}:
                                break
                            time.sleep(1)
                        observed_spend = float((run_data.get("usageTotalUsd") or 0.0) if isinstance(run_data, dict) else 0.0)
                        spent_total += observed_spend
                        if run_status != "SUCCEEDED":
                            decision = "RUN_FAILED"
                            provider_failures = 1
                            reason = f"run_status_{run_status or 'unknown'}"
                        else:
                            ds_id = _clean((run_data or {}).get("defaultDatasetId"))
                            if not ds_id:
                                decision = "DATASET_EMPTY"
                                reason = "missing_default_dataset"
                            else:
                                ds = requests.get(
                                    f"{APIFY_BASE}/datasets/{ds_id}/items",
                                    headers=_headers(os.environ.get("APIFY_TOKEN", "")),
                                    params={"format": "json", "clean": "1"},
                                    timeout=120,
                                )
                                if ds.status_code >= 400:
                                    decision = "RUN_FAILED"
                                    provider_failures = 1
                                    reason = f"dataset_http_{ds.status_code}"
                                else:
                                    items = ds.json()
                                    if not isinstance(items, list):
                                        items = []
                                    dataset_items = len(items)
                                    if dataset_items == 0:
                                        decision = "DATASET_EMPTY"
                                        reason = "dataset_no_items"
                                    else:
                                        importable, permanent, transient, output_schema_sig = _parse_items(actor_id, items)
                                        if importable > 0:
                                            decision = "PROVIDER_PASS"
                                            reason = "importable_transcripts_found"
                                        elif permanent > 0 and transient == 0:
                                            decision = "ONLY_PERMANENT_VIDEO_FAILURES"
                                            reason = "video_level_permanent_only"
                                        elif output_schema_sig == "":
                                            decision = "OUTPUT_SCHEMA_UNKNOWN"
                                            reason = "could_not_parse_items"
                                        else:
                                            decision = "PROVIDER_UNUSABLE"
                                            reason = "no_importable_transcripts"
                except requests.RequestException as exc:
                    decision = "RUN_FAILED"
                    provider_failures = 1
                    reason = f"request_exception:{_clean(exc)}"[:400]

        rows.append(
            ProbeRow(
                provider_key=provider_key,
                actor_id=actor_id,
                actor_permission_level=actor_permission or "unknown",
                token_slot_number=token_slot,
                attempted=attempted,
                start_http_status=start_http_status,
                apify_error_type=apify_error_type,
                run_status=run_status,
                dataset_items=dataset_items,
                transcripts_importable=importable,
                permanent_video_failures=permanent,
                transient_video_failures=transient,
                provider_failures=provider_failures,
                observed_spend=observed_spend,
                selected_for_recovery=1 if decision == "PROVIDER_PASS" else 0,
                decision=decision,
                reason=reason,
                input_schema_summary=input_schema_sig,
                output_schema_summary=output_schema_sig or "n/a",
            )
        )

    _write_outputs(rows)
    print(f"WROTE_CSV={PROBE_CSV.relative_to(ROOT)}")
    print(f"WROTE_MD={PROBE_MD.relative_to(ROOT)}")
    print(f"DRY_RUN={not live}")


if __name__ == "__main__":
    main()
