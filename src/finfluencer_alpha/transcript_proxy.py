from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Literal

ProxyMode = Literal["auto", "no-proxy", "webshare", "generic", "webshare-list"]


@dataclass(frozen=True)
class ProxyConfig:
    mode: str
    http_proxy: str | None = None
    https_proxy: str | None = None
    webshare_username: str | None = None
    webshare_password: str | None = None
    proxy_list: list[str] | None = None
    proxy_index: int = 0

    @property
    def resolved_mode(self) -> str:
        return self.mode


def _check_env_webshare() -> tuple[str | None, str | None]:
    ws_user = os.getenv("WEBSHARE_PROXY_USERNAME")
    ws_pass = os.getenv("WEBSHARE_PROXY_PASSWORD")
    return (ws_user.strip() if ws_user else None), (ws_pass.strip() if ws_pass else None)


def _check_env_generic() -> tuple[str | None, str | None]:
    http_p = os.getenv("YT_TRANSCRIPT_HTTP_PROXY")
    https_p = os.getenv("YT_TRANSCRIPT_HTTPS_PROXY")
    return (http_p.strip() if http_p else None), (https_p.strip() if https_p else None)


def resolve_proxy_config(
    mode: ProxyMode = "auto",
    webshare_username: str | None = None,
    webshare_password: str | None = None,
    http_proxy: str | None = None,
    https_proxy: str | None = None,
) -> ProxyConfig:
    env_ws_user, env_ws_pass = _check_env_webshare()
    ws_user = webshare_username or env_ws_user
    ws_pass = webshare_password or env_ws_pass
    env_http, env_https = _check_env_generic()
    http_p = http_proxy or env_http
    https_p = https_proxy or env_https

    webshare_available = bool(ws_user and ws_pass)
    generic_available = bool(http_p or https_p)

    webshare_supported = False
    generic_supported = False
    try:
        from youtube_transcript_api.proxies import WebshareProxyConfig  # noqa: F401

        webshare_supported = True
    except ImportError:
        pass
    try:
        from youtube_transcript_api.proxies import GenericProxyConfig  # noqa: F401

        generic_supported = True
    except ImportError:
        pass

    if mode == "webshare":
        if not webshare_supported:
            raise ValueError(
                "proxy-mode=webshare requested but WebshareProxyConfig is not available "
                "in the installed youtube-transcript-api version"
            )
        if not webshare_available:
            raise ValueError(
                "proxy-mode=webshare requires WEBSHARE_PROXY_USERNAME and "
                "WEBSHARE_PROXY_PASSWORD environment variables"
            )
        return ProxyConfig(
            mode="webshare", webshare_username=ws_user, webshare_password=ws_pass
        )

    if mode == "generic":
        if not generic_supported:
            raise ValueError(
                "proxy-mode=generic requested but GenericProxyConfig is not available "
                "in the installed youtube-transcript-api version"
            )
        if not generic_available:
            raise ValueError(
                "proxy-mode=generic requires YT_TRANSCRIPT_HTTP_PROXY and/or "
                "YT_TRANSCRIPT_HTTPS_PROXY environment variables"
            )
        return ProxyConfig(mode="generic", http_proxy=http_p, https_proxy=https_p)

    if mode == "webshare-list":
        # This mode fetches proxies from all Webshare sources
        proxy_urls = []
        
        # 1. Single URL
        single = os.getenv("WEBSHARE_SINGLE_PROXY_URL")
        if single:
            proxy_urls.append(single)
            
        # 2. Direct URLs
        directs = os.getenv("WEBSHARE_DIRECT_PROXY_URLS")
        if directs:
            proxy_urls.extend([u.strip() for u in directs.replace(",", "\n").split("\n") if u.strip()])
            
        # 3. API Key
        api_key = os.getenv("WEBSHARE_API_KEY")
        if api_key:
            import requests
            for m in ["direct", "backbone"]:
                try:
                    resp = requests.get(
                        f"https://proxy.webshare.io/api/v2/proxy/list/?mode={m}&page=1&page_size=50",
                        headers={"Authorization": f"Token {api_key}"},
                        timeout=10
                    )
                    if resp.status_code == 200:
                        results = resp.json().get("results", [])
                        for p in results:
                            url = f"http://{p['username']}:{p['password']}@{p['proxy_address']}:{p['port']}/"
                            proxy_urls.append(url)
                except Exception:
                    pass
                    
        # 4. Download Token
        dl_token = os.getenv("WEBSHARE_PROXY_LIST_DOWNLOAD_TOKEN")
        if dl_token:
            import requests
            try:
                resp = requests.get(
                    f"https://proxy.webshare.io/api/v2/proxy/list/download/{dl_token}/-/any/username/direct/-/",
                    timeout=10
                )
                if resp.status_code == 200:
                    lines = [ln.strip() for ln in resp.text.strip().split("\n") if ln.strip()]
                    for line in lines:
                        parts = line.split(":")
                        if len(parts) >= 4:
                            url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}/"
                            proxy_urls.append(url)
            except Exception:
                pass

        if not proxy_urls:
             # Fallback to generic if no list found but generic set
             if generic_available:
                 return ProxyConfig(mode="generic", http_proxy=http_p, https_proxy=https_p)
             return ProxyConfig(mode="no-proxy")
             
        return ProxyConfig(mode="webshare-list", proxy_list=proxy_urls)

    if mode == "auto":
        if webshare_supported and webshare_available:
            return ProxyConfig(mode="webshare", webshare_username=ws_user, webshare_password=ws_pass)
        if generic_supported and generic_available:
            return ProxyConfig(mode="generic", http_proxy=http_p, https_proxy=https_p)
        return ProxyConfig(mode="no-proxy")

    return ProxyConfig(mode="no-proxy")


def redact_credentials(text: str) -> str:
    if not text:
        return text
    redacted = re.sub(r"://[^@]+@", "://***:***@", text)
    for var in ["WEBSHARE_PROXY_USERNAME", "WEBSHARE_PROXY_PASSWORD"]:
        val = os.getenv(var)
        if val:
            redacted = redacted.replace(val, "***")
    return redacted


def create_yt_proxy_config(config: ProxyConfig) -> Any | None:
    if config.mode == "webshare":
        from youtube_transcript_api.proxies import WebshareProxyConfig

        return WebshareProxyConfig(
            proxy_username=config.webshare_username,
            proxy_password=config.webshare_password,
        )
    elif config.mode == "generic":
        from youtube_transcript_api.proxies import GenericProxyConfig

        return GenericProxyConfig(
            http_url=config.http_proxy,
            https_url=config.https_proxy,
        )
    elif config.mode == "webshare-list":
        if not config.proxy_list:
            return None
        current_proxy = config.proxy_list[config.proxy_index % len(config.proxy_list)]
        from youtube_transcript_api.proxies import GenericProxyConfig
        return GenericProxyConfig(http_url=current_proxy, https_url=current_proxy)
    return None


def proxymode_summary(config: ProxyConfig) -> str:
    if config.mode == "webshare":
        return "webshare (credentials present)" if config.webshare_username else "webshare (no credentials)"
    if config.mode == "webshare-list":
        count = len(config.proxy_list) if config.proxy_list else 0
        return f"webshare-list (count={count})"
    if config.mode == "generic":
        parts = []
        if config.http_proxy:
            parts.append(f"http={redact_credentials(config.http_proxy)}")
        if config.https_proxy:
            parts.append(f"https={redact_credentials(config.https_proxy)}")
        return f"generic ({'; '.join(parts)})" if parts else "generic (no proxy URLs)"
    return "no-proxy"
