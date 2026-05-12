import os
from pathlib import Path

from .slow_transcript_collection import collect_youtube_transcripts_slow
from .transcript_proxy import proxymode_summary, redact_credentials, resolve_proxy_config


def probe_proxy(input_path: Path, max_videos: int, proxy_mode: str, transcript_method: str, database_url: str):
    from dotenv import load_dotenv
    load_dotenv()
    
    keys = {
        "WEBSHARE": ["WEBSHARE_PROXY_USERNAME", "WEBSHARE_PROXY_PASSWORD"],
        "GENERIC": ["YT_TRANSCRIPT_HTTP_PROXY", "YT_TRANSCRIPT_HTTPS_PROXY"]
    }
    print("Credential Status:")
    for group, vars in keys.items():
        present = all(os.getenv(v) for v in vars)
        print(f"  {group} present: {present}")
    
    config = resolve_proxy_config(mode=proxy_mode)
    print(f"Resolved Proxy Mode: {redact_credentials(proxymode_summary(config))}")
    
    res = collect_youtube_transcripts_slow(
        input_path=input_path,
        max_videos=max_videos,
        delay_seconds=0,
        stop_on_block=True,
        confirm_run=True,
        database_url=database_url,
        proxy_mode=proxy_mode,
        transcript_method=transcript_method,
        output_summary_csv=Path("data/exports/transcripts/transcript_proxy_probe.csv"),
        output_summary_md=Path("data/exports/transcripts/transcript_proxy_probe.md")
    )
    return res

