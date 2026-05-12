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
):
    from dotenv import load_dotenv
    load_dotenv()
    
    if provider == "auto":
        provider = "youtubetranscript_dev"
        
    allow_asr_env = os.getenv("TRANSCRIPT_ALLOW_PROVIDER_ASR", "").lower() == "true"
    max_credits_env = os.getenv("TRANSCRIPT_MAX_PROVIDER_CREDITS")
    if max_credits_env and max_credits_env.isdigit():
        max_credits = min(max_credits, int(max_credits_env))
        
    token = None
    selected_env_var = None
    
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
        print(f"Dry run. Candidates: {candidates}")
        return

    successful = 0
    failed = 0
    total_credits = 0
    auth_failed = 0
    
    if provider == "youtubetranscript_dev":
        url = "https://www.youtubetranscript.dev/api/v2/batch"
        
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i+batch_size]
            body = {"video_ids": batch, "source": "auto", "format": {"timestamp": True}}
            
            success_in_batch = False
            for test_key in keys:
                current_token = os.getenv(test_key)
                if not current_token:
                    continue
                
                headers = {
                    "Authorization": f"Bearer {current_token}",
                    "Content-Type": "application/json"
                }
                
                try:
                    resp = requests.post(url, headers=headers, json=body)
                    if resp.status_code == 429:
                        retry_after = resp.headers.get("Retry-After", "60")
                        print(f"Rate limited with {test_key}. Retry after {retry_after}")
                        time.sleep(int(retry_after))
                        continue
                    if resp.status_code == 401:
                        print(f"401 Unauthorized with {test_key}.")
                        auth_failed += 1
                        continue # Try next key
                    if resp.status_code == 402:
                        print(f"402 Payment Required with {test_key}.")
                        auth_failed += 1
                        continue # Try next key
                        
                    resp.raise_for_status()
                    data = resp.json()
                    total_credits += data.get("credits_used", 0)
                    
                    # Handling 202 processing polling
                    if resp.status_code == 202 or data.get("status") == "processing":
                        poll_url = data.get("poll_url")
                        if poll_url:
                            for _ in range(10):
                                time.sleep(5)
                                poll_resp = requests.get(poll_url, headers=headers)
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
                                    
                                conn.execute("""
                                    INSERT INTO youtube_transcripts (
                                        video_id, transcript_source, retrieval_method, retrieval_status,
                                        provider_name, provider_version, status, full_text, segment_count, raw_json, source_confidence
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(video_id) DO UPDATE SET
                                        full_text=excluded.full_text, status=excluded.status
                                """, (
                                    vid, f"provider_{source}", "provider_api", "available",
                                    provider, "2.0", "available", text, len(segments), json.dumps(segments), 1.0
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
                    success_in_batch = True
                    break # Stop trying keys since this one worked
                except requests.exceptions.RequestException as e:
                    print(f"Request failed with {test_key}: {e}")
                    
            if not success_in_batch:
                failed += len(batch)
                
    else:
        print(f"Provider {provider} implementation not fully written here.")
            
    summary_md = Path("data/exports/transcripts/provider_capped_collection_summary.md")
    summary_csv = Path("data/exports/transcripts/provider_capped_collection_summary.csv")
    summary_md.parent.mkdir(parents=True, exist_ok=True)
    summary_md.write_text(f"# Provider Collection Summary\n- Attempted: {len(candidates)}\n- Successful: {successful}\n- Failed: {failed}\n- Auth Failed: {auth_failed}\n- Credits Used: {total_credits}\n")
    with summary_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["attempted", "successful", "failed", "auth_failed", "credits_used"])
        writer.writerow([len(candidates), successful, failed, auth_failed, total_credits])

