from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Literal

ProxyMode = Literal["auto", "no-proxy", "webshare", "generic"]


@dataclass(frozen=True)
class ProxyConfig:
    mode: str
    http_proxy: str | None = None
    https_proxy: str | None = None
    webshare_username: str | None = None
    webshare_password: str | None = None

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
    return None


def proxymode_summary(config: ProxyConfig) -> str:
    if config.mode == "webshare":
        return "webshare (credentials present)" if config.webshare_username else "webshare (no credentials)"
    if config.mode == "generic":
        parts = []
        if config.http_proxy:
            parts.append(f"http={redact_credentials(config.http_proxy)}")
        if config.https_proxy:
            parts.append(f"https={redact_credentials(config.https_proxy)}")
        return f"generic ({'; '.join(parts)})" if parts else "generic (no proxy URLs)"
    return "no-proxy"
