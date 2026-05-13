from __future__ import annotations

import csv
import hashlib
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

from .transcript_proxy import _get_env


def _test_proxy_route(
    proxies: dict | None,
    proxy_config_obj,
    video_id: str,
    route_name: str,
    proxy_mode: str,
    source: str = "",
) -> dict:
    """Test a single proxy route: webshare ipv4, ipify, YouTube HEAD, transcript fetch."""
    connected_ws = "no"
    connected_ipify = "no"
    egress_ip_hash = "redacted"
    yt_status = "failed"
    transcript_status = "untested"
    error_category = ""

    # 1. Test via Webshare's own ipv4 endpoint
    try:
        resp = requests.get(
            "https://ipv4.webshare.io/",
            proxies=proxies,
            timeout=15,
        )
        if resp.status_code == 200:
            connected_ws = "yes"
            ip = resp.text.strip()
            egress_ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:12] if ip else "redacted"
    except Exception as exc:
        error_category = f"webshare_ipv4_{type(exc).__name__}"

    # 2. Test via ipify
    try:
        resp = requests.get(
            "https://api.ipify.org?format=json",
            proxies=proxies,
            timeout=15,
        )
        if resp.status_code == 200:
            connected_ipify = "yes"
            if egress_ip_hash == "redacted":
                ip = resp.json().get("ip", "")
                egress_ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:12] if ip else "redacted"
    except Exception as exc:
        if not error_category:
            error_category = f"ipify_{type(exc).__name__}"

    connected = "yes" if (connected_ws == "yes" or connected_ipify == "yes") else "no"

    # 3. Test YouTube HEAD via proxy
    try:
        resp = requests.head(
            "https://www.youtube.com",
            proxies=proxies,
            timeout=15,
        )
        yt_status = "ok" if resp.status_code < 400 else f"http_{resp.status_code}"
    except Exception as exc:
        yt_status = f"error_{type(exc).__name__}"

    # 4. Test transcript fetch — ONLY if proxy connected
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
        except Exception as exc:
            if "429" in str(exc):
                transcript_status = "too_many_requests"
                error_category = "rate_limited"
            else:
                transcript_status = f"error_{type(exc).__name__}"
                error_category = type(exc).__name__
    elif connected == "no":
        transcript_status = "skipped_proxy_connection_failure"
        error_category = error_category or "proxy_connection_failure"

    should_use = connected == "yes" and transcript_status == "available"

    return {
        "route": route_name,
        "proxy_index": 0,
        "proxy_mode": proxy_mode,
        "source": source,
        "connected_webshare_ipv4": connected_ws,
        "connected_ipify": connected_ipify,
        "youtube_reachable": yt_status,
        "transcript_status": transcript_status,
        "error_category": error_category,
        "should_use_for_collection": "true" if should_use else "false",
        "egress_ip_hash": egress_ip_hash,
        "credential_redacted": "yes",
    }


def _build_generic_proxy_config(proxy_url: str):
    """Build a GenericProxyConfig from a proxy URL."""
    try:
        from youtube_transcript_api.proxies import GenericProxyConfig
        return GenericProxyConfig(http_url=proxy_url, https_url=proxy_url)
    except ImportError:
        return None


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

    print(f"Test video: {video_id}")

    # --- Route 1: WEBSHARE_PROXY_LIST_DOWNLOAD_URL (full dashboard URL) ---
    dl_url = _get_env("WEBSHARE_PROXY_LIST_DOWNLOAD_URL")
    if dl_url:
        print("WEBSHARE_PROXY_LIST_DOWNLOAD_URL detected: yes")
        try:
            dl_resp = requests.get(dl_url, timeout=30)
            if dl_resp.status_code == 200:
                lines = [ln.strip() for ln in dl_resp.text.strip().split("\n") if ln.strip()]
                print(f"  Downloaded proxies: {len(lines)}")
                for idx, line in enumerate(lines[:max_proxies]):
                    if line.startswith("http"):
                        proxy_url = line
                    elif "@" in line:
                        proxy_url = f"http://{line}/"
                    else:
                        parts = line.split(":")
                        if len(parts) >= 4:
                            proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}/"
                        else:
                            continue
                    proxies = {"http": proxy_url, "https": proxy_url}
                    yt_proxy = _build_generic_proxy_config(proxy_url)
                    r = _test_proxy_route(proxies, yt_proxy, video_id, "download_url", "direct", "WEBSHARE_PROXY_LIST_DOWNLOAD_URL")
                    r["proxy_index"] = idx
                    results.append(r)
                    print(f"  [{idx}]: ws_ipv4={r['connected_webshare_ipv4']}, transcript={r['transcript_status']}")
            else:
                print(f"  Download URL returned {dl_resp.status_code}")
        except Exception as exc:
            print(f"  Download URL error: {type(exc).__name__}")
    else:
        print("WEBSHARE_PROXY_LIST_DOWNLOAD_URL detected: no")

    # --- Route 2: WEBSHARE_SINGLE_PROXY_URL (explicit dashboard proxy) ---
    single_url = _get_env("WEBSHARE_SINGLE_PROXY_URL")
    if single_url:
        proxies = {"http": single_url, "https": single_url}
        yt_proxy = _build_generic_proxy_config(single_url)
        r = _test_proxy_route(proxies, yt_proxy, video_id, "single_proxy_url", "direct", "WEBSHARE_SINGLE_PROXY_URL")
        results.append(r)
        print(f"Route single_proxy_url: ws_ipv4={r['connected_webshare_ipv4']}, ipify={r['connected_ipify']}, yt={r['youtube_reachable']}, transcript={r['transcript_status']}")

    # --- Route 3: WEBSHARE_DIRECT_PROXY_URLS (comma/newline list) ---
    direct_urls = _get_env("WEBSHARE_DIRECT_PROXY_URLS")
    if direct_urls:
        url_list = [u.strip() for u in direct_urls.replace(",", "\n").split("\n") if u.strip()]
        for idx, proxy_url in enumerate(url_list[:max_proxies]):
            proxies = {"http": proxy_url, "https": proxy_url}
            yt_proxy = _build_generic_proxy_config(proxy_url)
            r = _test_proxy_route(proxies, yt_proxy, video_id, "direct_proxy_urls", "direct", "WEBSHARE_DIRECT_PROXY_URLS")
            r["proxy_index"] = idx
            results.append(r)
            print(f"Route direct_proxy_urls[{idx}]: ws_ipv4={r['connected_webshare_ipv4']}, transcript={r['transcript_status']}")

    # --- Route 4: Download-token (legacy short form) ---
    dl_token = _get_env("WEBSHARE_PROXY_LIST_DOWNLOAD_TOKEN")
    if dl_token:
        try:
            dl_resp = requests.get(
                f"https://proxy.webshare.io/api/v2/proxy/list/download/{dl_token}/-/any/username/direct/-/",
                timeout=15,
            )
            if dl_resp.status_code == 200:
                lines = [ln.strip() for ln in dl_resp.text.strip().split("\n") if ln.strip()]
                print(f"Download-token proxies: {len(lines)}")
                for idx, line in enumerate(lines[:max_proxies]):
                    parts = line.split(":")
                    if len(parts) >= 4:
                        addr, port, px_user, px_pass = parts[0], parts[1], parts[2], parts[3]
                        proxy_url = f"http://{px_user}:{px_pass}@{addr}:{port}/"
                        proxies = {"http": proxy_url, "https": proxy_url}
                        yt_proxy = _build_generic_proxy_config(proxy_url)
                        r = _test_proxy_route(proxies, yt_proxy, video_id, "download_token", "direct", "DOWNLOAD_TOKEN")
                        r["proxy_index"] = idx
                        results.append(r)
                        print(f"  dl_token[{idx}]: ws_ipv4={r['connected_webshare_ipv4']}, transcript={r['transcript_status']}")
            else:
                print(f"Download-token returned {dl_resp.status_code}")
        except Exception as exc:
            print(f"Download-token error: {type(exc).__name__}")

    # --- Route 5: Webshare API direct + backbone lists ---
    ws_api_key = _get_env("WEBSHARE_API_KEY")
    if ws_api_key:
        print("WEBSHARE_API_KEY detected: yes")
        for mode_label in ("direct", "backbone"):
            try:
                api_resp = requests.get(
                    f"https://proxy.webshare.io/api/v2/proxy/list/?mode={mode_label}&page=1&page_size={max_proxies}",
                    headers={"Authorization": f"Token {ws_api_key}"},
                    timeout=15,
                )
                print(f"Webshare API {mode_label}: HTTP {api_resp.status_code}")
                if api_resp.status_code == 200:
                    data = api_resp.json()
                    proxy_list = data.get("results", [])
                    print(f"  {mode_label} proxies returned: {len(proxy_list)}")
                    for idx, px in enumerate(proxy_list[:max_proxies]):
                        addr = px.get("proxy_address", "")
                        port = px.get("port", "")
                        px_user = px.get("username", "")
                        px_pass = px.get("password", "")
                        if not addr or not port:
                            continue
                        proxy_url = f"http://{px_user}:{px_pass}@{addr}:{port}/"
                        proxies = {"http": proxy_url, "https": proxy_url}
                        yt_proxy = _build_generic_proxy_config(proxy_url)
                        r = _test_proxy_route(
                            proxies, yt_proxy, video_id,
                            f"webshare_api_{mode_label}", mode_label,
                            "WEBSHARE_API_KEY",
                        )
                        r["proxy_index"] = idx
                        results.append(r)
                        print(f"  [{idx}]: ws_ipv4={r['connected_webshare_ipv4']}, yt={r['youtube_reachable']}, transcript={r['transcript_status']}")
                elif api_resp.status_code == 401:
                    print(f"  Webshare API {mode_label}: 401 Unauthorized (check WEBSHARE_API_KEY)")
                else:
                    print(f"  Webshare API {mode_label}: unexpected {api_resp.status_code}")
            except Exception as exc:
                print(f"  Webshare API {mode_label} error: {type(exc).__name__}")
    else:
        print("WEBSHARE_API_KEY detected: no")

    # --- Route 6: WebshareProxyConfig (backbone via p.webshare.io) ---
    ws_user = _get_env("WEBSHARE_PROXY_USERNAME")
    ws_pass = _get_env("WEBSHARE_PROXY_PASSWORD")
    if ws_user and ws_pass:
        proxy_url = f"http://{ws_user}:{ws_pass}@p.webshare.io:80/"
        proxies = {"http": proxy_url, "https": proxy_url}
        try:
            from youtube_transcript_api.proxies import WebshareProxyConfig
            yt_proxy = WebshareProxyConfig(proxy_username=ws_user, proxy_password=ws_pass)
        except ImportError:
            yt_proxy = None
        r = _test_proxy_route(proxies, yt_proxy, video_id, "webshare_backbone_env", "backbone", "WEBSHARE_PROXY_USERNAME")
        results.append(r)
        print(f"Route webshare_backbone_env: ws_ipv4={r['connected_webshare_ipv4']}, transcript={r['transcript_status']}")

    # --- Route 7: Generic env proxies ---
    http_proxy = _get_env("YT_TRANSCRIPT_HTTP_PROXY")
    https_proxy = _get_env("YT_TRANSCRIPT_HTTPS_PROXY")
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
        r = _test_proxy_route(proxies, yt_proxy, video_id, "generic_env", "generic", "YT_TRANSCRIPT_HTTP_PROXY")
        results.append(r)
        print(f"Route generic_env: ws_ipv4={r['connected_webshare_ipv4']}, ipify={r['connected_ipify']}, transcript={r['transcript_status']}")

    # Write reports
    report_md = Path("data/exports/transcripts/webshare_proxy_health.md")
    report_csv = Path("data/exports/transcripts/webshare_proxy_health.csv")
    report_md.parent.mkdir(parents=True, exist_ok=True)

    csv_fields = [
        "route", "proxy_index", "proxy_mode", "source",
        "connected_webshare_ipv4", "connected_ipify",
        "youtube_reachable", "transcript_status",
        "error_category", "should_use_for_collection",
        "egress_ip_hash", "credential_redacted",
    ]
    with report_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows(results)

    usable = sum(1 for r in results if r["should_use_for_collection"] == "true")
    md_lines = [
        "# Webshare Proxy Health Report",
        "",
        f"Total routes tested: {len(results)}",
        f"Usable for collection: {usable}",
        "",
    ]
    for res in results:
        md_lines.append(f"## Route: {res['route']} (index {res['proxy_index']})")
        md_lines.append(f"- Mode: {res['proxy_mode']}")
        md_lines.append(f"- Source: {res['source']}")
        md_lines.append(f"- Webshare ipv4: {res['connected_webshare_ipv4']}")
        md_lines.append(f"- ipify: {res['connected_ipify']}")
        md_lines.append(f"- YouTube: {res['youtube_reachable']}")
        md_lines.append(f"- Transcript: {res['transcript_status']}")
        md_lines.append(f"- Should use: {res['should_use_for_collection']}")
        md_lines.append(f"- Error: {res['error_category']}")
        md_lines.append("")

    report_md.write_text("\n".join(md_lines))
    print(f"\nReports written to {report_md} and {report_csv}")
    print(f"Usable proxies: {usable}/{len(results)}")
