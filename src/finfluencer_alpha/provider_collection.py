from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path

import requests

from .db import connect


def collect_provider_capped(
    database_url: str,
    input_path: Path,
    provider: str,
    max_credits: int,
    batch_size: int,
    confirm_run: bool,
    allow_asr: bool = False,
    only_previous_status: str | None = None,
):
    from dotenv import load_dotenv
    load_dotenv()

    if provider in ("auto", "youtube_transcript_dev"):
        provider = "youtubetranscript_dev"

    allow_asr_env = os.getenv("TRANSCRIPT_ALLOW_PROVIDER_ASR", "").lower() == "true" or allow_asr
    max_credits_env = os.getenv("TRANSCRIPT_MAX_PROVIDER_CREDITS")
    if max_credits_env and max_credits_env.isdigit():
        max_credits = min(max_credits, int(max_credits_env))

    token = None
    selected_env_var = None

    keys: list[str] = []
    if provider == "youtubetranscript_dev":
        keys = [
            "YOUTUBETRANSCRIPT_DEV_API_KEY",
            "YOUTUBE_TRANSCRIPT_DEV_API_KEY",
        ]
        tp = os.getenv("TRANSCRIPT_PROVIDER")
        if not tp or tp == "youtubetranscript_dev":
            keys.append("TRANSCRIPTAPI_KEY")

        for k in keys:
            val = os.getenv(k)
            if val:
                token = val
                selected_env_var = k
                break

    elif provider == "youtube_transcript_io":
        keys = ["YOUTUBE_TRANSCRIPT_IO_API_KEY", "YOUTUBETRANSCRIPT_API_KEY"]
        for k in keys:
            val = os.getenv(k)
            if val:
                token = val
                selected_env_var = k
                break

    if not token:
        print(f"Missing provider token for {provider}.")
        return

    print(f"Selected provider: {provider}")
    print(f"Selected env var: {selected_env_var}")

    with input_path.open(encoding="utf-8") as f:
        queue = list(csv.DictReader(f))

    queue_ids = [row["video_id"] for row in queue]
    existing = set()
    try:
        with connect(database_url=database_url) as conn:
            if queue_ids:
                placeholders = ",".join("?" for _ in queue_ids)
                if only_previous_status:
                    matching_status = {
                        r["video_id"]
                        for r in conn.execute(
                            f"SELECT video_id FROM youtube_transcripts WHERE video_id IN ({placeholders}) AND status = ?",
                            tuple(queue_ids) + (only_previous_status,)
                        ).fetchall()
                    }
                    existing = {vid for vid in queue_ids if vid not in matching_status}
                else:
                    existing = {
                        r["video_id"]
                        for r in conn.execute(
                            f"SELECT video_id FROM youtube_transcripts WHERE video_id IN ({placeholders}) AND status = 'available'",
                            tuple(queue_ids)
                        ).fetchall()
                    }
    except Exception:
        pass

    candidates = [row["video_id"] for row in queue if row["video_id"] not in existing][:max_credits]

    if not candidates:
        print("No candidates found.")
        return

    if not confirm_run:
        print(f"Dry run. {len(candidates)} candidates ready. First 5: {candidates[:5]}")
        return

    successful = 0
    failed = 0
    total_credits = 0
    total_requests = 0
    payment_required = False
    observed_safe_batch_size = batch_size
    batch_log: list[dict] = []

    if provider == "youtubetranscript_dev":
        url = "https://www.youtubetranscript.dev/api/v2/batch"
        current_batch_size = batch_size

        i = 0
        while i < len(candidates):
            if payment_required:
                break

            batch = candidates[i:i + current_batch_size]
            body = {"video_ids": batch, "source": "auto", "format": "timestamp"}

            success_in_batch = False
            all_keys_402 = True

            for test_key in keys:
                current_token = os.getenv(test_key)
                if not current_token:
                    continue

                headers = {
                    "Authorization": f"Bearer {current_token}",
                    "Content-Type": "application/json"
                }

                try:
                    resp = requests.post(url, headers=headers, json=body, timeout=30)
                    total_requests += 1
                    http_status = resp.status_code

                    if http_status == 429:
                        retry_after = resp.headers.get("Retry-After", "60")
                        print(f"Rate limited with {test_key}. Retry after {retry_after}")
                        batch_log.append({"batch_start": i, "batch_size": len(batch), "http_status": 429, "error": "rate_limited"})
                        time.sleep(min(int(retry_after), 120))
                        continue

                    if http_status == 401:
                        print(f"401 Unauthorized with {test_key}.")
                        batch_log.append({"batch_start": i, "batch_size": len(batch), "http_status": 401, "error": "unauthorized"})
                        continue  # Try next key

                    if http_status == 402:
                        print(f"402 Payment Required with {test_key}.")
                        batch_log.append({"batch_start": i, "batch_size": len(batch), "http_status": 402, "error": "payment_required"})
                        continue  # Try next key, but track

                    if http_status == 400:
                        # Adaptive batch size: reduce
                        error_text = resp.text[:200] if resp.text else ""
                        print(f"400 Bad Request with batch_size={len(batch)}. Reducing. Detail: {error_text}")
                        batch_log.append({"batch_start": i, "batch_size": len(batch), "http_status": 400, "error": "bad_request_batch_too_large"})
                        if current_batch_size > 1:
                            current_batch_size = max(1, current_batch_size // 2)
                            observed_safe_batch_size = current_batch_size
                            all_keys_402 = False
                            break  # Retry this batch with smaller size
                        else:
                            failed += len(batch)
                            i += len(batch)
                            all_keys_402 = False
                            break

                    all_keys_402 = False
                    resp.raise_for_status()
                    data = resp.json()
                    batch_credits = data.get("credits_used", 0)
                    total_credits += batch_credits

                    # Handling 202 processing polling
                    if http_status == 202 or data.get("status") == "processing":
                        poll_url = data.get("poll_url")
                        if poll_url:
                            for _ in range(10):
                                time.sleep(5)
                                poll_resp = requests.get(poll_url, headers=headers, timeout=30)
                                poll_resp.raise_for_status()
                                poll_data = poll_resp.json()
                                if poll_data.get("status") == "completed":
                                    data = poll_data
                                    break

                    results = data.get("results", [])

                    with connect(database_url=database_url) as conn:
                        for res in results:
                            vid = res.get("data", {}).get("video_id")
                            if not vid:
                                continue

                            status = res.get("status")
                            if status == "completed":
                                t_data = res.get("data", {}).get("transcript", {})
                                text = t_data.get("text")
                                segments = t_data.get("segments", [])
                                if not text and segments:
                                    text = " ".join([s.get("text", "") for s in segments])

                                source = t_data.get("source", "auto")
                                if source == "asr" and not allow_asr_env:
                                    failed += 1
                                    conn.execute("""
                                        INSERT INTO youtube_transcripts (video_id, status, error_message, provider_name, retrieval_method)
                                        VALUES (?, ?, ?, ?, ?) ON CONFLICT(video_id) DO UPDATE SET status=excluded.status
                                    """, (vid, "no_language", "ASR not allowed", provider, "provider_api"))
                                    continue

                                transcript_source = f"provider_{source}"
                                retrieval_method = "provider_api"
                                source_confidence = 1.0
                                if source == "asr":
                                    transcript_source = "provider_asr"
                                    retrieval_method = "provider_api_asr"
                                    source_confidence = 0.8

                                conn.execute("""
                                    INSERT INTO youtube_transcripts (
                                        video_id, transcript_source, retrieval_method, retrieval_status,
                                        provider_name, provider_version, status, full_text, segment_count, raw_json, source_confidence
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(video_id) DO UPDATE SET
                                        full_text=excluded.full_text, status=excluded.status,
                                        transcript_source=excluded.transcript_source,
                                        retrieval_method=excluded.retrieval_method,
                                        source_confidence=excluded.source_confidence
                                """, (
                                    vid, transcript_source, retrieval_method, "available",
                                    provider, "2.0", "available", text, len(segments), json.dumps(segments), source_confidence
                                ))
                                successful += 1
                            else:
                                failed += 1
                                conn.execute("""
                                    INSERT INTO youtube_transcripts (
                                        video_id, status, error_message, provider_name, retrieval_method
                                    ) VALUES (?, ?, ?, ?, ?)
                                    ON CONFLICT(video_id) DO UPDATE SET status=excluded.status
                                """, (vid, "error", str(res.get("status", "Failed")), provider, "provider_api"))
                        conn.commit()

                    batch_log.append({
                        "batch_start": i, "batch_size": len(batch),
                        "http_status": http_status, "error": None,
                        "credits_used": batch_credits, "imported": successful
                    })
                    success_in_batch = True
                    observed_safe_batch_size = current_batch_size
                    i += len(batch)
                    break  # Stop trying keys since this one worked

                except requests.exceptions.RequestException as e:
                    print(f"Request failed with {test_key}: {e}")
                    batch_log.append({"batch_start": i, "batch_size": len(batch), "http_status": 0, "error": str(type(e).__name__)})

            if all_keys_402:
                print("All keys returned 402. Stopping provider path.")
                payment_required = True
                break

            if not success_in_batch and not all_keys_402:
                # Check if we broke out for batch size reduction
                if current_batch_size < batch_size:
                    continue  # Retry with smaller batch
                failed += len(batch)
                i += len(batch)

    else:
        print(f"Provider {provider} implementation not fully written here.")

    summary_md = Path("data/exports/transcripts/provider_capped_collection_summary.md")
    summary_csv = Path("data/exports/transcripts/provider_capped_collection_summary.csv")
    summary_md.parent.mkdir(parents=True, exist_ok=True)

    summary_md.write_text(
        f"# Provider Collection Summary\n"
        f"- Provider: {provider}\n"
        f"- Attempted IDs: {len(candidates)}\n"
        f"- Successful imports: {successful}\n"
        f"- Failed: {failed}\n"
        f"- Credits used (from response): {total_credits}\n"
        f"- HTTP requests made: {total_requests}\n"
        f"- Requested batch size: {batch_size}\n"
        f"- Observed safe batch size: {observed_safe_batch_size}\n"
        f"- Payment required (402): {payment_required}\n"
    )
    with summary_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "attempted_ids", "imported", "failed", "credits_used",
            "http_requests", "requested_batch_size", "observed_safe_batch_size",
            "payment_required"
        ])
        writer.writerow([
            len(candidates), successful, failed, total_credits,
            total_requests, batch_size, observed_safe_batch_size,
            payment_required
        ])

    print(f"Provider collection done: imported={successful}, failed={failed}, credits={total_credits}, safe_batch={observed_safe_batch_size}, 402={payment_required}")


def probe_youtubetranscript_dev(database_url: str, input_path: Path, max_videos: int = 1):
    from dotenv import load_dotenv
    load_dotenv()

    keys = [
        "YOUTUBETRANSCRIPT_DEV_API_KEY",
        "YOUTUBE_TRANSCRIPT_DEV_API_KEY",
    ]
    tp = os.getenv("TRANSCRIPT_PROVIDER")
    if not tp or tp == "youtubetranscript_dev":
        keys.append("TRANSCRIPTAPI_KEY")

    with input_path.open(encoding="utf-8") as f:
        queue = list(csv.DictReader(f))

    queue_ids = [row["video_id"] for row in queue]
    existing = set()
    try:
        with connect(database_url=database_url) as conn:
            if queue_ids:
                placeholders = ",".join("?" for _ in queue_ids)
                existing = {
                    r["video_id"]
                    for r in conn.execute(
                        f"SELECT video_id FROM youtube_transcripts WHERE video_id IN ({placeholders}) AND status = 'available'",
                        tuple(queue_ids)
                    ).fetchall()
                }
    except Exception:
        pass

    candidates = [vid for vid in queue_ids if vid not in existing]

    url = "https://www.youtubetranscript.dev/api/v2/transcribe"
    summary_md = Path("data/exports/transcripts/youtubetranscript_dev_probe.md")
    summary_csv = Path("data/exports/transcripts/youtubetranscript_dev_probe.csv")

    attempts = 0

    for vid in candidates:
        if attempts >= 3:
            break

        attempts += 1

        body = {"video": vid, "source": "auto", "format": "timestamp"}

        auth_failed_keys = []
        keys_with_value = [k for k in keys if os.getenv(k)]

        for test_key in keys_with_value:
            current_token = os.getenv(test_key)

            headers = {
                "Authorization": f"Bearer {current_token}",
                "Content-Type": "application/json"
            }

            try:
                resp = requests.post(url, headers=headers, json=body, timeout=30)
                if resp.status_code == 401:
                    auth_failed_keys.append(test_key)
                    continue
                if resp.status_code == 402:
                    print(f"402 Payment Required with {test_key}. Stopping provider path.")
                    return
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After", "60")
                    time.sleep(min(int(retry_after), 120))
                    resp = requests.post(url, headers=headers, json=body, timeout=30)

                resp.raise_for_status()
                data = resp.json()

                if resp.status_code == 202 or data.get("status") == "processing":
                    poll_url = data.get("poll_url")
                    if poll_url:
                        for _ in range(10):
                            time.sleep(5)
                            poll_resp = requests.get(poll_url, headers=headers, timeout=30)
                            poll_resp.raise_for_status()
                            poll_data = poll_resp.json()
                            if poll_data.get("status") == "completed":
                                data = poll_data
                                break

                if data.get("status") == "completed":
                    t_data = data.get("data", {}).get("transcript", {})
                    text = t_data.get("text")
                    segments = t_data.get("segments", [])
                    if not text and segments:
                        text = " ".join([s.get("text", "") for s in segments])

                    credits_used = data.get("credits_used", 0)
                    print(f"Success! Env var: {test_key}, credits: {credits_used}, length: {len(text) if text else 0}, segments: {len(segments)}")

                    source = t_data.get("source", "auto")
                    with connect(database_url=database_url) as conn:
                        conn.execute("""
                            INSERT INTO youtube_transcripts (
                                video_id, transcript_source, retrieval_method, retrieval_status,
                                provider_name, provider_version, status, full_text, segment_count, raw_json, source_confidence
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(video_id) DO UPDATE SET
                                full_text=excluded.full_text, status=excluded.status
                        """, (
                            vid, f"provider_{source}", "provider_api", "available",
                            "youtubetranscript_dev", "2.0", "available", text, len(segments), json.dumps(segments), 1.0
                        ))

                    summary_md.parent.mkdir(parents=True, exist_ok=True)
                    summary_md.write_text(f"# Probe Success\nEnv var: {test_key}\nVideo: {vid}\nCredits: {credits_used}\n")
                    with summary_csv.open("w", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerow(["video_id", "env_var", "credits_used", "status"])
                        writer.writerow([vid, test_key, credits_used, "success"])
                    return
                else:
                    print(f"Failed to fetch for {vid}: {data.get('status')} {data.get('message')}")
                    # try next candidate
                    break

            except Exception as e:
                print(f"Request error with {test_key}: {e}")

        if len(auth_failed_keys) == len(keys_with_value):
            print(f"All keys failed with 401: {auth_failed_keys}. Stopping provider path.")
            return
