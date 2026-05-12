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
    
    token_keys = [
        "TRANSCRIPTAPI_KEY",
        "YOUTUBE_TRANSCRIPT_DEV_API_KEY",
        "YOUTUBETRANSCRIPT_API_KEY",
        "YOUTUBE_TRANSCRIPT_IO_API_KEY",
    ]
    token = None
    for k in token_keys:
        val = os.getenv(k)
        if val:
            token = val
            break
            
    if not token:
        print(f"Missing provider token. Checked: {', '.join(token_keys)}")
        return
        
    with input_path.open(encoding="utf-8") as f:
        queue = list(csv.DictReader(f))
        
    # Queue is already sorted by plan_slow_youtube_transcript_queue but let's re-verify logic just in case
    # Actually the queue is already prioritized correctly by the plan step.
    # Just take top max_credits items.
    
    # Filter out anything we've already done
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

    # Process in batches
    successful = 0
    failed = 0
    
    url = "https://www.youtube-transcript.io/api/transcripts"
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }
    
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i+batch_size]
        body = {"ids": batch}
        
        try:
            resp = requests.post(url, headers=headers, json=body)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After", "60")
                print(f"Rate limited. Retry after {retry_after}")
                time.sleep(int(retry_after))
                continue
                
            resp.raise_for_status()
            data = resp.json()
            
            with connect(database_url=database_url) as conn:
                for video_id, item in data.items():
                    if "transcript" in item and item["transcript"]:
                        # Insert successful
                        full_text = " ".join([seg.get("text", "") for seg in item["transcript"]])
                        conn.execute("""
                            INSERT INTO youtube_transcripts (
                                video_id, transcript_source, retrieval_method, retrieval_status,
                                provider_name, provider_version, status, full_text, segment_count, raw_json, source_confidence
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(video_id) DO UPDATE SET
                                full_text=excluded.full_text, status=excluded.status
                        """, (
                            video_id, "provider_api", "provider_api", "available",
                            provider, "1.0", "available", full_text, len(item["transcript"]), json.dumps(item["transcript"]), 1.0
                        ))
                        successful += 1
                    else:
                        failed += 1
                        conn.execute("""
                            INSERT INTO youtube_transcripts (
                                video_id, status, error_message, provider_name, retrieval_method
                            ) VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(video_id) DO UPDATE SET status=excluded.status
                        """, (video_id, "error", str(item.get("error", "No transcript")), provider, "provider_api"))
                conn.commit()
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            failed += len(batch)
            
    summary_md = Path("data/exports/transcripts/provider_capped_collection_summary.md")
    summary_csv = Path("data/exports/transcripts/provider_capped_collection_summary.csv")
    
    summary_md.write_text(f"""# Provider Collection Summary
- Attempted: {len(candidates)}
- Successful: {successful}
- Failed: {failed}
""")
    with summary_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["attempted", "successful", "failed"])
        writer.writerow([len(candidates), successful, failed])

