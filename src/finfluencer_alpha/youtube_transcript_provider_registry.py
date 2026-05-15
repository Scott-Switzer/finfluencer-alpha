from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse


def _clean(value: object) -> str:
    return str(value or "").strip()


def _normalize_youtube_url(value: str) -> str:
    text = _clean(value)
    if not text:
        return text
    if len(text) == 11 and "http" not in text:
        return f"https://www.youtube.com/watch?v={text}"
    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        host = parsed.netloc.lower()
        if "youtu.be" in host:
            vid = parsed.path.strip("/").split("/")[0]
            if len(vid) == 11:
                return f"https://www.youtube.com/watch?v={vid}"
        if "youtube.com" in host:
            qs = parse_qs(parsed.query or "")
            vid = _clean((qs.get("v") or [""])[0])
            if len(vid) == 11:
                return f"https://www.youtube.com/watch?v={vid}"
    return text


def _extract_video_id(value: str) -> str:
    text = _clean(value)
    if not text:
        return ""
    if len(text) == 11 and "http" not in text:
        return text
    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        host = parsed.netloc.lower()
        if "youtu.be" in host:
            vid = parsed.path.strip("/").split("/")[0]
            if len(vid) == 11:
                return vid
        if "youtube.com" in host:
            qs = parse_qs(parsed.query or "")
            vid = _clean((qs.get("v") or [""])[0])
            if len(vid) == 11:
                return vid
    return text


def _default_languages(languages: list[str] | None) -> list[str]:
    vals = [_clean(x) for x in (languages or ["en"]) if _clean(x)]
    return vals or ["en"]


def _build_urls_payload(urls: list[str], languages: list[str] | None) -> dict[str, Any]:
    return {
        "urls": [{"url": _normalize_youtube_url(url)} for url in urls],
        "outputFormat": "json",
        "languages": _default_languages(languages),
    }


def _build_video_urls_payload(urls: list[str], languages: list[str] | None) -> dict[str, Any]:
    return {
        "videoUrls": [{"url": _normalize_youtube_url(url)} for url in urls],
        "languages": _default_languages(languages),
    }


def _build_start_urls_payload(urls: list[str], languages: list[str] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "startUrls": [{"url": _normalize_youtube_url(url)} for url in urls],
    }
    langs = _default_languages(languages)
    if langs:
        payload["languages"] = langs
    return payload


def _build_insight_payload(urls: list[str], languages: list[str] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "input": {
            "video_urls": [{"url": _normalize_youtube_url(url)} for url in urls],
        }
    }
    langs = _default_languages(languages)
    if langs:
        payload["input"]["languages"] = langs
    return payload


def _build_schema_driven_payload(
    urls: list[str], languages: list[str] | None, input_schema: dict[str, Any] | None
) -> dict[str, Any]:
    schema_props = (input_schema or {}).get("properties")
    if not isinstance(schema_props, dict):
        return _build_urls_payload(urls, languages)
    keys = {str(k).lower(): k for k in schema_props}
    normalized_urls = [_normalize_youtube_url(url) for url in urls]
    langs = _default_languages(languages)

    if "input" in keys and isinstance(schema_props.get(keys["input"]), dict):
        nested = schema_props.get(keys["input"]) or {}
        nested_props = nested.get("properties") if isinstance(nested, dict) else {}
        if isinstance(nested_props, dict):
            nested_keys = {str(k).lower(): k for k in nested_props}
            if "video_urls" in nested_keys:
                payload = {"input": {"video_urls": [{"url": u} for u in normalized_urls]}}
                if "languages" in nested_keys:
                    payload["input"]["languages"] = langs
                return payload

    if "urls" in keys:
        payload = {"urls": [{"url": u} for u in normalized_urls]}
        if "outputformat" in keys:
            payload[keys["outputformat"]] = "json"
        if "languages" in keys:
            payload[keys["languages"]] = langs
        return payload
    if "videourls" in keys:
        payload = {"videoUrls": [{"url": u} for u in normalized_urls]}
        if "languages" in keys:
            payload[keys["languages"]] = langs
        return payload
    if "starturls" in keys:
        payload = {"startUrls": [{"url": u} for u in normalized_urls]}
        if "languages" in keys:
            payload[keys["languages"]] = langs
        return payload
    if "videourl" in keys:
        payload = {"videoUrl": normalized_urls[0] if normalized_urls else ""}
        if "language" in keys:
            payload[keys["language"]] = langs[0] if langs else "en"
        return payload
    return _build_urls_payload(urls, languages)


def _extract_segments(item: dict[str, Any], timestamp_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    for field in timestamp_fields:
        v = item.get(field)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    return []


def _extract_text(item: dict[str, Any], text_fields: tuple[str, ...], segments: list[dict[str, Any]]) -> str:
    for field in text_fields:
        v = item.get(field)
        if isinstance(v, str) and v.strip():
            return v.strip()
    if segments:
        parts: list[str] = []
        for seg in segments:
            text = _clean(seg.get("text") or seg.get("subtitle") or seg.get("snippet"))
            if text:
                parts.append(text)
        if parts:
            return " ".join(parts)
    return ""


def _parse_generic_item(profile: YoutubeTranscriptProviderProfile, item: dict[str, Any]) -> dict[str, Any]:
    url = ""
    video_id = ""
    for field in profile.video_id_fields:
        v = _clean(item.get(field))
        if not v:
            continue
        if "http" in v:
            url = v
            video_id = _extract_video_id(v)
        else:
            video_id = v
        if video_id:
            break
    if url:
        url = _normalize_youtube_url(url)
    elif video_id and len(video_id) == 11:
        url = f"https://www.youtube.com/watch?v={video_id}"

    segments = _extract_segments(item, profile.transcript_timestamp_fields)
    text = _extract_text(item, profile.transcript_text_fields, segments)
    error_text = _clean(item.get("error") or item.get("errorMessage") or item.get("message") or item.get("status"))
    permanent = any(
        token in error_text.lower() for token in profile.permanent_error_fields
    ) if error_text else False
    return {
        "video_id": video_id,
        "url": url,
        "text": text,
        "segments": segments,
        "error_text": error_text,
        "is_permanent_error": permanent,
    }


@dataclass(frozen=True)
class YoutubeTranscriptProviderProfile:
    provider_key: str
    actor_id: str
    input_payload_builder: Callable[[list[str], list[str] | None, dict[str, Any] | None], dict[str, Any]]
    output_parser: Callable[[dict[str, Any]], dict[str, Any]]
    supports_batch: bool
    supports_timestamps: bool
    supports_language_fallback: bool
    requires_rental_or_subscription_unknown: bool
    known_cost_model_if_available: str
    permanent_error_fields: tuple[str, ...]
    transcript_text_fields: tuple[str, ...]
    transcript_timestamp_fields: tuple[str, ...]
    video_id_fields: tuple[str, ...]
    title_channel_date_fields: tuple[str, ...]
    probe_only: bool = False


def _profile(
    *,
    provider_key: str,
    actor_id: str,
    payload_builder: Callable[[list[str], list[str] | None, dict[str, Any] | None], dict[str, Any]],
    supports_batch: bool,
    supports_timestamps: bool,
    supports_language_fallback: bool,
    cost_model: str,
    probe_only: bool = False,
) -> YoutubeTranscriptProviderProfile:
    profile = YoutubeTranscriptProviderProfile(
        provider_key=provider_key,
        actor_id=actor_id,
        input_payload_builder=payload_builder,
        output_parser=lambda item: _parse_generic_item(profile, item),  # type: ignore[name-defined]
        supports_batch=supports_batch,
        supports_timestamps=supports_timestamps,
        supports_language_fallback=supports_language_fallback,
        requires_rental_or_subscription_unknown=True,
        known_cost_model_if_available=cost_model,
        permanent_error_fields=(
            "transcriptnotfound",
            "transcriptsdisabled",
            "agerestricted",
            "videounavailable",
            "url_not_supported",
            "video_id_not_found",
        ),
        transcript_text_fields=(
            "transcript",
            "transcriptText",
            "transcript_only_text",
            "fullTranscript",
            "caption",
            "subtitles",
            "transcriptWithTimestamps",
        ),
        transcript_timestamp_fields=(
            "transcriptWithTimestamps",
            "timestamps",
            "segments",
            "transcript",
            "searchResult",
        ),
        video_id_fields=(
            "videoId",
            "videoID",
            "id",
            "url",
            "inputUrl",
            "videoUrl",
            "video_url",
        ),
        title_channel_date_fields=(
            "videoTitle",
            "title",
            "channelName",
            "channel_title",
            "videoPostDate",
            "publishedAt",
            "url",
        ),
        probe_only=probe_only,
    )
    return profile


def _build_profiles() -> dict[str, YoutubeTranscriptProviderProfile]:
    return {
        "supreme_coder/youtube-transcript-scraper": _profile(
            provider_key="supreme_coder",
            actor_id="supreme_coder/youtube-transcript-scraper",
            payload_builder=lambda urls, languages, _schema: _build_urls_payload(urls, languages),
            supports_batch=True,
            supports_timestamps=True,
            supports_language_fallback=True,
            cost_model="pay-per-result",
        ),
        "insight_api_labs/youtube-transcript": _profile(
            provider_key="insight_api_labs",
            actor_id="insight_api_labs/youtube-transcript",
            payload_builder=lambda urls, languages, _schema: _build_insight_payload(urls, languages),
            supports_batch=True,
            supports_timestamps=True,
            supports_language_fallback=True,
            cost_model="unknown",
        ),
        "topaz_sharingan/Youtube-Transcript-Scraper-1": _profile(
            provider_key="topaz_sharingan_1",
            actor_id="topaz_sharingan/Youtube-Transcript-Scraper-1",
            payload_builder=lambda urls, languages, schema: _build_schema_driven_payload(urls, languages, schema),
            supports_batch=True,
            supports_timestamps=True,
            supports_language_fallback=True,
            cost_model="unknown",
            probe_only=True,
        ),
        "topaz_sharingan/Youtube-Transcript-Scraper": _profile(
            provider_key="topaz_sharingan",
            actor_id="topaz_sharingan/Youtube-Transcript-Scraper",
            payload_builder=lambda urls, languages, schema: _build_schema_driven_payload(urls, languages, schema),
            supports_batch=True,
            supports_timestamps=True,
            supports_language_fallback=True,
            cost_model="unknown",
            probe_only=True,
        ),
        "starvibe/youtube-video-transcript": _profile(
            provider_key="starvibe",
            actor_id="starvibe/youtube-video-transcript",
            payload_builder=lambda urls, languages, schema: _build_schema_driven_payload(urls, languages, schema),
            supports_batch=True,
            supports_timestamps=True,
            supports_language_fallback=True,
            cost_model="unknown",
            probe_only=True,
        ),
        "scrape-creators/best-youtube-transcripts-scraper": _profile(
            provider_key="scrape_creators",
            actor_id="scrape-creators/best-youtube-transcripts-scraper",
            payload_builder=lambda urls, languages, _schema: _build_video_urls_payload(urls, languages),
            supports_batch=True,
            supports_timestamps=True,
            supports_language_fallback=True,
            cost_model="unknown",
        ),
        "zerohour/yt-transcript": _profile(
            provider_key="zerohour",
            actor_id="zerohour/yt-transcript",
            payload_builder=lambda urls, languages, schema: _build_schema_driven_payload(urls, languages, schema),
            supports_batch=True,
            supports_timestamps=True,
            supports_language_fallback=True,
            cost_model="unknown",
            probe_only=True,
        ),
        "optimus-fulcria/youtube-transcript-extractor": _profile(
            provider_key="optimus_fulcria",
            actor_id="optimus-fulcria/youtube-transcript-extractor",
            payload_builder=lambda urls, languages, schema: _build_schema_driven_payload(urls, languages, schema),
            supports_batch=True,
            supports_timestamps=True,
            supports_language_fallback=True,
            cost_model="unknown",
            probe_only=True,
        ),
        "akash9078/youtube-transcript-extractor": _profile(
            provider_key="akash9078",
            actor_id="akash9078/youtube-transcript-extractor",
            payload_builder=lambda urls, languages, schema: _build_schema_driven_payload(urls, languages, schema),
            supports_batch=True,
            supports_timestamps=True,
            supports_language_fallback=True,
            cost_model="unknown",
            probe_only=True,
        ),
        "johnvc/YoutubeTranscripts": _profile(
            provider_key="johnvc",
            actor_id="johnvc/YoutubeTranscripts",
            payload_builder=lambda urls, languages, schema: _build_schema_driven_payload(urls, languages, schema),
            supports_batch=True,
            supports_timestamps=True,
            supports_language_fallback=True,
            cost_model="unknown",
            probe_only=True,
        ),
    }


PROVIDER_PROFILES = _build_profiles()


def get_provider_profile(actor_id: str) -> YoutubeTranscriptProviderProfile | None:
    return PROVIDER_PROFILES.get(actor_id)


def get_all_provider_profiles() -> list[YoutubeTranscriptProviderProfile]:
    return list(PROVIDER_PROFILES.values())


def build_provider_payload(
    actor_id: str,
    video_urls: list[str],
    *,
    languages: list[str] | None = None,
    input_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = get_provider_profile(actor_id)
    if profile is None:
        return _build_schema_driven_payload(video_urls, languages, input_schema)
    return profile.input_payload_builder(video_urls, languages, input_schema)


def parse_provider_output_item(actor_id: str, item: dict[str, Any]) -> dict[str, Any]:
    profile = get_provider_profile(actor_id)
    if profile is None:
        fallback = _profile(
            provider_key="generic_probe",
            actor_id=actor_id,
            payload_builder=lambda urls, languages, schema: _build_schema_driven_payload(urls, languages, schema),
            supports_batch=True,
            supports_timestamps=True,
            supports_language_fallback=True,
            cost_model="unknown",
            probe_only=True,
        )
        return _parse_generic_item(fallback, item)
    return profile.output_parser(item)


def schema_summary(input_schema: dict[str, Any] | None) -> str:
    if not isinstance(input_schema, dict):
        return "missing"
    props = input_schema.get("properties")
    if not isinstance(props, dict):
        return "missing_properties"
    keys = sorted(str(k) for k in props.keys())
    return ",".join(keys[:25]) if keys else "empty_properties"

