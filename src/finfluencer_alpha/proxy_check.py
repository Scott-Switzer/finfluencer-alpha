from __future__ import annotations

import csv
import hashlib
import os
from pathlib import Path

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
)


def _test_proxy_route(
    proxies: dict | None,
    proxy_config_obj,
    video_id: str,
    route_name: str,
    proxy_mode: str,
) -> dict:
    """Test a single proxy route: ipify, YouTube HEAD, transcript fetch."""
    connected = "no"
    egress_ip_hash = "redacted"
    ipify_status = "failed"
    yt_status = "failed"
    transcript_status = "untested"
    error_category = ""

    # 1. Test outbound IP via proxy
    try:
        resp = requests.get(
            "https://api.ipify.org?format=json",
            proxies=proxies,
            timeout=15,
        )
        if resp.status_code == 200:
            connected = "yes"
            ip = resp.json().get("ip", "")
            egress_ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:12] if ip else "redacted"
            ipify_status = "ok"
    except Exception as e:
        error_category = f"ipify_{type(e).__name__}"

    # 2. Test YouTube HEAD via proxy
    try:
        resp = requests.head(
            "https://www.youtube.com",
            proxies=proxies,
            timeout=15,
        )
        yt_status = "ok" if resp.status_code < 400 else f"http_{resp.status_code}"
    except Exception as e:
        yt_status = f"error_{type(e).__name__}"

    # 3. Test transcript fetch — ONLY if proxy connected
    if connected == "yes" and proxy_config_obj is not None:
        try:
            api = YouTubeTranscriptApi(proxy_config=proxy_config_obj)
            api.list(video_id)
            transcript_status = "available"
        except IpBlocked:
            transcript_status = "ip_blocked"
            error_category = "ip_blocked"
        except RequestBlocked:
            transcript_status = "request_blocked"
            error_category = "request_blocked"
        except NoTranscriptFound:
            transcript_status = "no_transcript"
        except TranscriptsDisabled:
            transcript_status = "disabled"
        except VideoUnavailable:
            transcript_status = "unavailable"
        except Exception as e:
            if "429" in str(e):
                transcript_status = "too_many_requests"
                error_category = "rate_limited"
            else:
                transcript_status = f"error_{type(e).__name__}"
                error_category = type(e).__name__
    elif connected == "no":
        transcript_status = "skipped_proxy_connection_failure"
        error_category = error_category or "proxy_connection_failure"

    should_use = (
        connected == "yes"
        and transcript_status == "available"
    )

    return {
        "route": route_name,
        "proxy_index": 0,
        "proxy_mode": proxy_mode,
        "connected": connected,
        "ipify_status": ipify_status,
        "youtube_status": yt_status,
        "transcript_status": transcript_status,
        "error_category": error_category,
        "should_use_for_collection": "true" if should_use else "false",
        "credential_redacted": "yes",
        "egress_ip_hash": egress_ip_hash,
    }


def check_webshare_proxies(
    max_proxies: int = 10,
    test_transcript_video_from: Path | None = None,
):
    from dotenv import load_dotenv
    load_dotenv()

    results: list[dict] = []

    # Pick a test video
    video_id = "58qhj_h_Ros"
    if test_transcript_video_from and test_transcript_video_from.exists():
        try:
            with test_transcript_video_from.open(encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                row = next(reader, None)
                if row:
                    video_id = row["video_id"]
        except Exception:
            pass

    # --- Route A: WebshareProxyConfig ---
    ws_user = os.getenv("WEBSHARE_PROXY_USERNAME")
    ws_pass = os.getenv("WEBSHARE_PROXY_PASSWORD")
    if ws_user and ws_pass:
        proxy_url = f"http://{ws_user}:{ws_pass}@p.webshare.io:80/"
        proxies = {"http": proxy_url, "https": proxy_url}
        try:
            from youtube_transcript_api.proxies import WebshareProxyConfig
            yt_proxy = WebshareProxyConfig(proxy_username=ws_user, proxy_password=ws_pass)
        except ImportError:
            yt_proxy = None
        r = _test_proxy_route(proxies, yt_proxy, video_id, "webshare_env_config", "webshare_config")
        results.append(r)
        print(f"Route webshare_env_config: connected={r['connected']}, yt={r['youtube_status']}, transcript={r['transcript_status']}")

    # --- Route B: Generic env proxies ---
    http_proxy = os.getenv("YT_TRANSCRIPT_HTTP_PROXY")
    https_proxy = os.getenv("YT_TRANSCRIPT_HTTPS_PROXY")
    if http_proxy or https_proxy:
        proxies = {}
        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            proxies["https"] = https_proxy
        try:
            from youtube_transcript_api.proxies import GenericProxyConfig
            yt_proxy = GenericProxyConfig(http_url=http_proxy, https_url=https_proxy)
        except ImportError:
            yt_proxy = None
        r = _test_proxy_route(proxies, yt_proxy, video_id, "generic_env", "generic")
        results.append(r)
        print(f"Route generic_env: connected={r['connected']}, yt={r['youtube_status']}, transcript={r['transcript_status']}")

    # --- Route C: Webshare direct API list ---
    ws_api_key = os.getenv("WEBSHARE_API_KEY")
    if ws_api_key:
        for mode_label in ("direct", "backbone"):
            try:
                api_resp = requests.get(
                    f"https://proxy.webshare.io/api/v2/proxy/list/?mode={mode_label}&page=1&page_size={max_proxies}",
                    headers={"Authorization": f"Token {ws_api_key}"},
                    timeout=15,
                )
                if api_resp.status_code == 200:
                    proxy_list = api_resp.json().get("results", [])
                    for idx, px in enumerate(proxy_list[:max_proxies]):
                        addr = px.get("proxy_address", "")
                        port = px.get("port", "")
                        px_user = px.get("username", "")
                        px_pass = px.get("password", "")
                        if not addr or not port:
                            continue
                        proxy_url = f"http://{px_user}:{px_pass}@{addr}:{port}/"
                        proxies = {"http": proxy_url, "https": proxy_url}
                        try:
                            from youtube_transcript_api.proxies import GenericProxyConfig
                            yt_proxy = GenericProxyConfig(
                                http_url=proxy_url, https_url=proxy_url
                            )
                        except ImportError:
                            yt_proxy = None
                        r = _test_proxy_route(
                            proxies, yt_proxy, video_id,
                            f"webshare_api_{mode_label}", mode_label,
                        )
                        r["proxy_index"] = idx
                        results.append(r)
                        print(f"Route webshare_api_{mode_label}[{idx}]: connected={r['connected']}, transcript={r['transcript_status']}")
                else:
                    print(f"Webshare API {mode_label} list returned {api_resp.status_code}")
            except Exception as e:
                print(f"Webshare API {mode_label} list error: {type(e).__name__}")

    # --- Route E: Download-token ---
    dl_token = os.getenv("WEBSHARE_PROXY_LIST_DOWNLOAD_TOKEN")
    if dl_token:
        try:
            dl_resp = requests.get(
                f"https://proxy.webshare.io/api/v2/proxy/list/download/{dl_token}/-/any/username/direct/-/",
                timeout=15,
            )
            if dl_resp.status_code == 200:
                lines = [ln.strip() for ln in dl_resp.text.strip().split("\n") if ln.strip()]
                for idx, line in enumerate(lines[:max_proxies]):
                    parts = line.split(":")
                    if len(parts) >= 4:
                        addr, port, px_user, px_pass = parts[0], parts[1], parts[2], parts[3]
                        proxy_url = f"http://{px_user}:{px_pass}@{addr}:{port}/"
                        proxies = {"http": proxy_url, "https": proxy_url}
                        try:
                            from youtube_transcript_api.proxies import GenericProxyConfig
                            yt_proxy = GenericProxyConfig(http_url=proxy_url, https_url=proxy_url)
                        except ImportError:
                            yt_proxy = None
                        r = _test_proxy_route(proxies, yt_proxy, video_id, "webshare_download_token", "direct")
                        r["proxy_index"] = idx
                        results.append(r)
                        print(f"Route download_token[{idx}]: connected={r['connected']}, transcript={r['transcript_status']}")
        except Exception as e:
            print(f"Download token error: {type(e).__name__}")

    # Write reports
    report_md = Path("data/exports/transcripts/webshare_proxy_health.md")
    report_csv = Path("data/exports/transcripts/webshare_proxy_health.csv")
    report_md.parent.mkdir(parents=True, exist_ok=True)

    csv_fields = [
        "route", "proxy_index", "proxy_mode", "connected",
        "ipify_status", "youtube_status", "transcript_status",
        "error_category", "should_use_for_collection",
        "credential_redacted", "egress_ip_hash",
    ]
    with report_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows(results)

    usable = sum(1 for r in results if r["should_use_for_collection"] == "true")
    md_lines = [
        "# Webshare Proxy Health Report",
        "",
        f"Routes tested: {len(results)}",
        f"Usable for collection: {usable}",
        "",
    ]
    for res in results:
        md_lines.append(f"## Route: {res['route']} (index {res['proxy_index']})")
        md_lines.append(f"- Mode: {res['proxy_mode']}")
        md_lines.append(f"- Connected: {res['connected']}")
        md_lines.append(f"- ipify: {res['ipify_status']}")
        md_lines.append(f"- YouTube: {res['youtube_status']}")
        md_lines.append(f"- Transcript: {res['transcript_status']}")
        md_lines.append(f"- Should use: {res['should_use_for_collection']}")
        md_lines.append(f"- Error: {res['error_category']}")
        md_lines.append("")

    report_md.write_text("\n".join(md_lines))
    print(f"Reports written to {report_md} and {report_csv}")
    print(f"Usable proxies: {usable}/{len(results)}")
