from __future__ import annotations

import csv
import importlib
from pathlib import Path

import pytest

from finfluencer_alpha.apify_key_manager import ApifyKeyManager
from finfluencer_alpha.youtube_transcript_provider_registry import (
    build_provider_payload,
    get_all_provider_profiles,
    parse_provider_output_item,
)


class _FakeResult:
    def __init__(self, available_count: int, skipped_existing_count: int = 0, cost_usd: float = 0.01) -> None:
        self.available_count = available_count
        self.skipped_existing_count = skipped_existing_count
        self.cost_usd = cost_usd


def _write_probe_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = [
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
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_provider_registry_has_required_profiles() -> None:
    actor_ids = {p.actor_id for p in get_all_provider_profiles()}
    required = {
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
    }
    assert required.issubset(actor_ids)


def test_payload_builders_for_supreme_and_insight() -> None:
    urls = ["https://www.youtube.com/watch?v=abc123def45"]
    supreme = build_provider_payload(
        "supreme_coder/youtube-transcript-scraper",
        urls,
        languages=["en", "en-US", "en-GB"],
        input_schema=None,
    )
    assert supreme["urls"] == [{"url": urls[0]}]
    assert supreme["languages"] == ["en", "en-US", "en-GB"]
    insight = build_provider_payload(
        "insight_api_labs/youtube-transcript",
        urls,
        languages=["en", "en-US", "en-GB"],
        input_schema=None,
    )
    assert "input" in insight
    assert insight["input"]["video_urls"] == [{"url": urls[0]}]


def test_schema_builder_does_not_leak_unsupported_fields() -> None:
    schema = {"properties": {"videoUrl": {"type": "string"}}}
    payload = build_provider_payload(
        "unknown/provider",
        ["https://www.youtube.com/watch?v=abc123def45"],
        languages=["en"],
        input_schema=schema,
    )
    assert "videoUrl" in payload
    assert "urls" not in payload
    assert "videoUrls" not in payload


def test_parser_accepts_supreme_and_insight_formats() -> None:
    supreme_item = {
        "url": "https://www.youtube.com/watch?v=abc123def45",
        "transcript": "Buy NVDA now",
        "segments": [{"text": "Buy NVDA now", "start": 0.0, "duration": 1.0}],
    }
    parsed_supreme = parse_provider_output_item("supreme_coder/youtube-transcript-scraper", supreme_item)
    assert parsed_supreme["video_id"] == "abc123def45"
    assert "Buy NVDA now" in parsed_supreme["text"]

    insight_item = {
        "url": "https://www.youtube.com/watch?v=xyz987uvw65",
        "transcriptWithTimestamps": [{"text": "Transcript line", "start": 0.0, "duration": 1.0}],
        "videoTitle": "Test",
        "channelName": "Creator",
    }
    parsed_insight = parse_provider_output_item("insight_api_labs/youtube-transcript", insight_item)
    assert parsed_insight["video_id"] == "xyz987uvw65"
    assert "Transcript line" in parsed_insight["text"]


def test_runner_switches_provider_after_credit_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("scripts.run_youtube_multi_provider_transcript_recovery")
    queue = tmp_path / "71.csv"
    queue.write_text("video_id\nabc123def45\nxyz987uvw65\n", encoding="utf-8")
    probe = tmp_path / "75.csv"
    _write_probe_csv(
        probe,
        [
            {
                "provider_key": "supreme",
                "actor_id": "supreme_coder/youtube-transcript-scraper",
                "actor_permission_level": "PUBLIC",
                "token_slot_number": "1",
                "attempted": "3",
                "start_http_status": "200",
                "apify_error_type": "",
                "run_status": "SUCCEEDED",
                "dataset_items": "3",
                "transcripts_importable": "4",
                "permanent_video_failures": "0",
                "transient_video_failures": "0",
                "provider_failures": "0",
                "observed_spend": "0.01",
                "selected_for_recovery": "1",
                "decision": "PROVIDER_PASS",
                "reason": "ok",
                "input_schema_summary": "urls",
                "output_schema_summary": "transcript",
            },
            {
                "provider_key": "insight",
                "actor_id": "insight_api_labs/youtube-transcript",
                "actor_permission_level": "PUBLIC",
                "token_slot_number": "2",
                "attempted": "3",
                "start_http_status": "200",
                "apify_error_type": "",
                "run_status": "SUCCEEDED",
                "dataset_items": "3",
                "transcripts_importable": "3",
                "permanent_video_failures": "0",
                "transient_video_failures": "0",
                "provider_failures": "0",
                "observed_spend": "0.01",
                "selected_for_recovery": "1",
                "decision": "PROVIDER_PASS",
                "reason": "ok",
                "input_schema_summary": "input.video_urls",
                "output_schema_summary": "transcript",
            },
        ],
    )
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "LIVE_MD", tmp_path / "76.md")
    monkeypatch.setattr(mod, "LIVE_CSV", tmp_path / "76.csv")
    monkeypatch.setattr(mod, "FINAL_MD", tmp_path / "77.md")
    monkeypatch.setattr(mod, "FINAL_CSV", tmp_path / "77.csv")
    monkeypatch.setattr(mod, "PROBE_CSV", probe)
    monkeypatch.setattr(mod, "RETRY_QUEUE_CSV", queue)
    monkeypatch.setenv("RUN_YOUTUBE_MULTI_PROVIDER_RECOVERY", "1")
    monkeypatch.setenv("YOUTUBE_MULTI_PROVIDER_RECOVERY_CAP_USD", "1.0")
    monkeypatch.setenv("APIFY_TOKEN_COUNT", "2")
    monkeypatch.setenv("APIFY_TOKEN_1", "tok1")
    monkeypatch.setenv("APIFY_TOKEN_2", "tok2")

    calls: list[str] = []

    def fake_collect(**kwargs):
        calls.append(kwargs["actor_id"])
        if kwargs["actor_id"] == "supreme_coder/youtube-transcript-scraper":
            raise RuntimeError("Apify run start failed (HTTP 403): platform-feature-disabled hard limit exceeded")
        return _FakeResult(available_count=len(kwargs["video_ids"]), cost_usd=0.01)

    monkeypatch.setattr(mod, "collect_apify_transcripts", fake_collect)
    monkeypatch.setattr(mod, "_status_map", lambda _ids: {})
    monkeypatch.setattr(mod, "_transcript_count", lambda: 0)
    manager = ApifyKeyManager.from_env(
        {"APIFY_TOKEN_COUNT": "2", "APIFY_TOKEN_1": "tok1", "APIFY_TOKEN_2": "tok2"},
        ledger_path=tmp_path / "ledger.csv",
    )
    monkeypatch.setattr(mod.ApifyKeyManager, "from_env", lambda: manager)
    mod.main()
    assert "supreme_coder/youtube-transcript-scraper" in calls
    assert "insight_api_labs/youtube-transcript" in calls
    content = (tmp_path / "77.md").read_text(encoding="utf-8")
    assert "provider_token_pair_status" in content


def test_classifiers_and_dry_run_safety(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    recovery_mod = importlib.import_module("scripts.run_youtube_multi_provider_transcript_recovery")
    assert recovery_mod._classify_actor_failure("TranscriptNotFound: no subtitles") == "VIDEO_LEVEL"
    assert recovery_mod._classify_actor_failure("dataset empty") == "ACTOR"

    probe_mod = importlib.import_module("scripts.probe_youtube_transcript_providers")
    assert probe_mod._classify_start_failure(403, "actor-is-not-rented", "not rented")[0] == "START_FAILED_RENTAL_REQUIRED"
    assert probe_mod._classify_start_failure(400, "invalid-input", "field required")[0] == "START_FAILED_SCHEMA"

    queue = tmp_path / "71.csv"
    queue.write_text("video_id\nabc123def45\n", encoding="utf-8")
    probe = tmp_path / "75.csv"
    _write_probe_csv(
        probe,
        [
            {
                "provider_key": "supreme",
                "actor_id": "supreme_coder/youtube-transcript-scraper",
                "actor_permission_level": "PUBLIC",
                "token_slot_number": "1",
                "attempted": "3",
                "start_http_status": "200",
                "apify_error_type": "",
                "run_status": "SUCCEEDED",
                "dataset_items": "3",
                "transcripts_importable": "3",
                "permanent_video_failures": "0",
                "transient_video_failures": "0",
                "provider_failures": "0",
                "observed_spend": "0.01",
                "selected_for_recovery": "1",
                "decision": "PROVIDER_PASS",
                "reason": "ok",
                "input_schema_summary": "urls",
                "output_schema_summary": "transcript",
            }
        ],
    )
    monkeypatch.setattr(recovery_mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(recovery_mod, "LIVE_MD", tmp_path / "76.md")
    monkeypatch.setattr(recovery_mod, "LIVE_CSV", tmp_path / "76.csv")
    monkeypatch.setattr(recovery_mod, "FINAL_MD", tmp_path / "77.md")
    monkeypatch.setattr(recovery_mod, "FINAL_CSV", tmp_path / "77.csv")
    monkeypatch.setattr(recovery_mod, "PROBE_CSV", probe)
    monkeypatch.setattr(recovery_mod, "RETRY_QUEUE_CSV", queue)
    monkeypatch.setenv("RUN_YOUTUBE_MULTI_PROVIDER_RECOVERY", "0")
    monkeypatch.setenv("APIFY_TOKEN", "SUPER_SECRET_TOKEN")
    called = {"n": 0}
    monkeypatch.setattr(recovery_mod, "collect_apify_transcripts", lambda **kwargs: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setattr(recovery_mod, "_status_map", lambda _ids: {})
    monkeypatch.setattr(recovery_mod, "_transcript_count", lambda: 0)
    recovery_mod.main()
    assert called["n"] == 0
    assert "SUPER_SECRET_TOKEN" not in (tmp_path / "76.md").read_text(encoding="utf-8")
    assert "SUPER_SECRET_TOKEN" not in (tmp_path / "77.md").read_text(encoding="utf-8")


def test_probe_tries_all_token_slots_when_credit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe_mod = importlib.import_module("scripts.probe_youtube_transcript_providers")
    queue = tmp_path / "71.csv"
    queue.write_text("video_id\nabc123def45\nxyz987uvw65\n", encoding="utf-8")
    monkeypatch.setattr(probe_mod, "ROOT", tmp_path)
    monkeypatch.setattr(probe_mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(probe_mod, "PROBE_CSV", tmp_path / "75.csv")
    monkeypatch.setattr(probe_mod, "PROBE_MD", tmp_path / "75.md")
    monkeypatch.setattr(
        probe_mod,
        "CANDIDATES",
        ["supreme_coder/youtube-transcript-scraper"],
    )
    monkeypatch.setenv("YOUTUBE_RETRY_QUEUE_PATH", str(queue))
    monkeypatch.setenv("RUN_YOUTUBE_PROVIDER_PROBE", "1")
    monkeypatch.setenv("YOUTUBE_PROVIDER_PROBE_REQUIRE_ALL_SLOTS", "1")

    manager = ApifyKeyManager.from_env(
        {
            "APIFY_TOKEN_COUNT": "3",
            "APIFY_TOKEN_1": "tok1",
            "APIFY_TOKEN_1_LABEL": "slot_alpha",
            "APIFY_TOKEN_2": "tok2",
            "APIFY_TOKEN_2_LABEL": "slot_beta",
            "APIFY_TOKEN_3": "tok3",
            "APIFY_TOKEN_3_LABEL": "slot_gamma",
        },
        ledger_path=tmp_path / "ledger.csv",
    )
    monkeypatch.setattr(probe_mod.ApifyKeyManager, "from_env", lambda: manager)

    class _Resp:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_get(url: str, **kwargs):  # noqa: ANN001
        if "/acts/" in url:
            return _Resp(
                200,
                {
                    "data": {
                        "actorPermissionLevel": "LIMITED_PERMISSIONS",
                        "inputSchema": {"properties": {"urls": {"type": "array"}}},
                    }
                },
            )
        return _Resp(404, {"error": {"type": "not-found", "message": "not found"}})

    def fake_post(url: str, **kwargs):  # noqa: ANN001
        return _Resp(
            403,
            {
                "error": {
                    "type": "platform-feature-disabled",
                    "message": "Monthly usage hard limit exceeded",
                }
            },
        )

    monkeypatch.setattr(probe_mod.requests, "get", fake_get)
    monkeypatch.setattr(probe_mod.requests, "post", fake_post)
    probe_mod.main()
    rows = list(csv.DictReader((tmp_path / "75.csv").open(newline="", encoding="utf-8")))
    assert len(rows) == 3
    assert {row["token_slot_number"] for row in rows} == {"1", "2", "3"}
    assert all(row["decision"] == "START_FAILED_CREDIT" for row in rows)
