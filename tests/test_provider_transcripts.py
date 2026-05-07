from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from finfluencer_alpha.capstone_summary import export_capstone_summary
from finfluencer_alpha.cli import app
from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.provider_transcripts import (
    ProviderConfigError,
    collect_provider_transcripts,
)
from finfluencer_alpha.transcript_vendor import import_transcripts_csv


class FakeResponse:
    def __init__(
        self,
        payload: dict[str, object],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = str(payload)

    def json(self) -> dict[str, object]:
        return self.payload


class FakeSession:
    requests: list[dict[str, object]] = []
    response_payload: dict[str, object] = {}

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        self.__class__.requests.append({"method": method, "url": url, **kwargs})
        return FakeResponse(self.__class__.response_payload)


def _use_temp_db(monkeypatch, tmp_path: Path, name: str = "provider.db") -> str:
    database_url = f"sqlite:///{tmp_path / name}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    return database_url


def _write_vendor_batch(path: Path, video_ids: list[str]) -> None:
    path.write_text(
        "video_id,url,creator,creator_category,published_at,title,description,"
        "priority_score,ticker_signal_count,recommendation_keyword_signal,"
        "current_view_count,current_like_count,current_comment_count\n"
        + "".join(
            f"{video_id},https://www.youtube.com/watch?v={video_id},Creator,stock_picker,"
            "2026-01-01T00:00:00Z,Buy Nvidia,Buying Nvidia stock,10,1,1,100,10,1\n"
            for video_id in video_ids
        ),
        encoding="utf-8",
    )


def _provider_payload(video_ids: list[str]) -> dict[str, object]:
    return {
        "batch_id": "batch_1",
        "status": "completed",
        "results": [
            {
                "request_id": f"request_{video_id}",
                "status": "completed",
                "data": {
                    "video_id": video_id,
                    "transcript": {
                        "text": "I am buying Nvidia stock",
                        "language": "en",
                        "source": "manual",
                        "segments": [
                            {"text": "I am buying Nvidia stock", "start": 0, "end": 2500}
                        ],
                    },
                },
            }
            for video_id in video_ids
        ],
    }


def _patch_fake_session(monkeypatch, video_ids: list[str]) -> None:
    FakeSession.requests = []
    FakeSession.response_payload = _provider_payload(video_ids)
    monkeypatch.setattr("finfluencer_alpha.provider_transcripts.requests.Session", FakeSession)


def test_provider_command_fails_if_api_key_missing(monkeypatch, tmp_path: Path) -> None:
    _use_temp_db(monkeypatch, tmp_path, "missing_key.db")
    batch_path = tmp_path / "batch.csv"
    _write_vendor_batch(batch_path, ["video000001"])
    get_settings.cache_clear()

    result = CliRunner().invoke(
        app,
        [
            "collect-provider-transcripts",
            "--provider",
            "youtubetranscript_dev",
            "--input",
            str(batch_path),
            "--output",
            str(tmp_path / "out.csv"),
            "--confirm-provider-run",
        ],
        env={"DATABASE_URL": f"sqlite:///{tmp_path / 'missing_key.db'}"},
    )

    assert result.exit_code == 1
    assert "Missing YOUTUBETRANSCRIPT_DEV_API_KEY" in result.output


def test_provider_command_writes_import_compatible_csv(monkeypatch, tmp_path: Path) -> None:
    _use_temp_db(monkeypatch, tmp_path, "write_csv.db")
    monkeypatch.setenv("YOUTUBETRANSCRIPT_DEV_API_KEY", "fake-key")
    get_settings.cache_clear()
    batch_path = tmp_path / "batch.csv"
    output_path = tmp_path / "provider.csv"
    _write_vendor_batch(batch_path, ["video000001"])
    _patch_fake_session(monkeypatch, ["video000001"])

    result = collect_provider_transcripts(
        provider="youtubetranscript_dev",
        input_path=batch_path,
        output_path=output_path,
        limit=1,
        batch_size=100,
        language="en",
        timestamps=True,
        captions_only=True,
        allow_asr=False,
        confirm_provider_run=True,
    )
    df = pd.read_csv(output_path)

    assert result.successful_count == 1
    assert set(
        [
            "video_id",
            "transcript_text",
            "transcript_source",
            "provider_name",
            "retrieval_method",
            "is_asr_generated",
            "retrieved_at",
            "notes",
            "language",
            "raw_provider_source",
            "segment_json",
        ]
    ) <= set(df.columns)
    assert df.loc[0, "transcript_source"] == "external_provider"
    assert df.loc[0, "provider_name"] == "YouTubeTranscript.dev"


def test_provider_command_caps_limit_correctly(monkeypatch, tmp_path: Path) -> None:
    _use_temp_db(monkeypatch, tmp_path, "limit.db")
    monkeypatch.setenv("YOUTUBETRANSCRIPT_DEV_API_KEY", "fake-key")
    get_settings.cache_clear()
    batch_path = tmp_path / "batch.csv"
    _write_vendor_batch(batch_path, ["video000001", "video000002", "video000003"])
    _patch_fake_session(monkeypatch, ["video000001", "video000002"])

    collect_provider_transcripts(
        provider="youtubetranscript_dev",
        input_path=batch_path,
        output_path=tmp_path / "provider.csv",
        limit=2,
        batch_size=100,
        language="en",
        timestamps=True,
        captions_only=True,
        allow_asr=False,
        confirm_provider_run=True,
    )

    payload = FakeSession.requests[0]["json"]
    assert payload["video_ids"] == ["video000001", "video000002"]


def test_provider_command_respects_batch_size_limit(tmp_path: Path) -> None:
    batch_path = tmp_path / "batch.csv"
    _write_vendor_batch(batch_path, ["video000001"])

    with pytest.raises(ProviderConfigError, match="batch-size must be <= 100"):
        collect_provider_transcripts(
            provider="youtubetranscript_dev",
            input_path=batch_path,
            output_path=tmp_path / "provider.csv",
            limit=1,
            batch_size=101,
            language="en",
            timestamps=True,
            captions_only=True,
            allow_asr=False,
            confirm_provider_run=True,
        )


def test_provider_command_does_not_request_asr_unless_allowed(monkeypatch, tmp_path: Path) -> None:
    _use_temp_db(monkeypatch, tmp_path, "asr.db")
    monkeypatch.setenv("YOUTUBETRANSCRIPT_DEV_API_KEY", "fake-key")
    get_settings.cache_clear()
    batch_path = tmp_path / "batch.csv"
    _write_vendor_batch(batch_path, ["video000001"])
    _patch_fake_session(monkeypatch, ["video000001"])

    collect_provider_transcripts(
        provider="youtubetranscript_dev",
        input_path=batch_path,
        output_path=tmp_path / "provider.csv",
        limit=1,
        batch_size=100,
        language="en",
        timestamps=True,
        captions_only=True,
        allow_asr=False,
        confirm_provider_run=True,
    )

    assert FakeSession.requests[0]["json"]["allow_asr"] is False


def test_import_preserves_provider_name_and_segment_json(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "import_segments.db")
    monkeypatch.setenv("YOUTUBETRANSCRIPT_DEV_API_KEY", "fake-key")
    get_settings.cache_clear()
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (video_id, channel_id, channel_title, published_at, title)
            VALUES ('video000001', 'channel1', 'Creator', '2026-01-01T00:00:00Z', 'Buy Nvidia')
            """
        )
        conn.commit()
    batch_path = tmp_path / "batch.csv"
    output_path = tmp_path / "provider.csv"
    _write_vendor_batch(batch_path, ["video000001"])
    _patch_fake_session(monkeypatch, ["video000001"])
    collect_provider_transcripts(
        provider="youtubetranscript_dev",
        input_path=batch_path,
        output_path=output_path,
        limit=1,
        batch_size=100,
        language="en",
        timestamps=True,
        captions_only=True,
        allow_asr=False,
        confirm_provider_run=True,
    )

    import_transcripts_csv(output_path, source="external_provider")

    with connect(database_url) as conn:
        transcript = conn.execute(
            "SELECT provider_name, transcript_source FROM youtube_transcripts"
        ).fetchone()
        segment = conn.execute(
            "SELECT start_seconds, duration_seconds, text FROM youtube_transcript_segments"
        ).fetchone()
    assert transcript["provider_name"] == "YouTubeTranscript.dev"
    assert transcript["transcript_source"] == "external_provider"
    assert segment["start_seconds"] == 0.0
    assert segment["duration_seconds"] == 2.5
    assert segment["text"] == "I am buying Nvidia stock"


def test_capstone_summary_export_runs_on_fixture_db(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "summary.db")
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, creator_category, published_at, title
            )
            VALUES ('video000001', 'channel1', 'Creator', 'stock_picker',
                    '2026-01-01T00:00:00Z', 'Buy Nvidia')
            """
        )
        conn.execute(
            """
            INSERT INTO youtube_transcripts (
              video_id, transcript_source, retrieval_method, retrieval_status,
              provider_name, status, full_text, segment_count, source_confidence
            )
            VALUES ('video000001', 'external_provider', 'provider_caption_api',
                    'available', 'YouTubeTranscript.dev', 'available',
                    'I am buying Nvidia stock', 1, 0.95)
            """
        )
        conn.execute(
            """
            INSERT INTO transcript_candidate_windows (
              video_id, transcript_source, provider_name, ticker, evidence_window,
              accepted_event_flag, exclusion_reason
            )
            VALUES ('video000001', 'external_provider', 'YouTubeTranscript.dev',
                    'NVDA', 'I am buying Nvidia stock', 1, NULL)
            """
        )
        conn.execute(
            """
            INSERT INTO transcript_recommendation_events (
              video_id, transcript_source, provider_name, ticker, stance,
              confidence_label
            )
            VALUES ('video000001', 'external_provider', 'YouTubeTranscript.dev',
                    'NVDA', 'bullish', 'high')
            """
        )
        conn.commit()

    result = export_capstone_summary(tmp_path / "summary")

    assert result.paths["metadata_universe_summary"].exists()
    assert result.paths["transcript_collection_summary"].exists()
    assert result.paths["recommendation_event_summary"].exists()
    assert result.paths["coverage_bias_summary"].exists()
    assert "transcript evidence is available" in result.paths[
        "paper_methods_numbers"
    ].read_text(encoding="utf-8").lower()
