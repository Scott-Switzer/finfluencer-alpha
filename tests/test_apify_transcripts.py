from __future__ import annotations

from pathlib import Path

import pytest
import requests
from typer.testing import CliRunner

from finfluencer_alpha.apify_benchmark import benchmark_apify_transcript_actors
from finfluencer_alpha.apify_queue import select_apify_transcript_queue
from finfluencer_alpha.apify_transcripts import (
    ApifyConfigError,
    _build_apify_input,
    _normalize_apify_output,
    _resolve_apify_token,
)
from finfluencer_alpha.cli import app
from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.transcript_fallback import (
    ProviderTier,
    resolve_provider_chain,
)


class FakeResponse:
    def __init__(
        self,
        payload: dict[str, object] | list[dict[str, object]],
        status_code: int = 200,
    ) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self._payload


class FakeRequestTracker:
    requests: list[dict[str, object]] = []

    @classmethod
    def reset(cls) -> None:
        cls.requests = []


def _fake_requests_post_success(url: str, **kwargs: object) -> FakeResponse:
    FakeRequestTracker.requests.append(
        {"method": "POST", "url": str(url), "kwargs": kwargs}
    )
    return FakeResponse({"data": {"id": "test_run_123"}})


def _fake_requests_get_run_status(url: str, **kwargs: object) -> FakeResponse:
    FakeRequestTracker.requests.append(
        {"method": "GET", "url": str(url), "kwargs": kwargs}
    )
    return FakeResponse(
        {
            "id": "test_run_123",
            "status": "SUCCEEDED",
            "finishedAt": "2026-05-12T00:00:00Z",
            "usageTotalUsd": 0.25,
        }
    )


def _fake_requests_get_results(url: str, **kwargs: object) -> FakeResponse:
    FakeRequestTracker.requests.append(
        {"method": "GET", "url": str(url), "kwargs": kwargs}
    )
    return FakeResponse(
        [
            {
                "url": "https://www.youtube.com/watch?v=video000001",
                "transcript": "I am buying Nvidia stock. The stock looks great.",
                "language": "en",
                "segments": [
                    {
                        "text": "I am buying Nvidia stock.",
                        "start": 0.0,
                        "duration": 2.5,
                    },
                    {
                        "text": "The stock looks great.",
                        "start": 2.5,
                        "duration": 2.0,
                    },
                ],
            },
        ]
    )


def _fake_requests_post_error(url: str, **kwargs: object) -> FakeResponse:
    return FakeResponse({"error": "Actor not found"}, status_code=404)


def _use_temp_db(monkeypatch, tmp_path: Path, name: str = "apify_test.db") -> str:
    database_url = f"sqlite:///{tmp_path / name}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    return database_url


def _seed_raw_video(
    database_url: str,
    video_id: str,
    channel_title: str = "Test Creator",
    published_at: str = "2024-06-15T00:00:00Z",
    title: str = "Test Video Title",
    seed_source: str = "data/seeds/youtube_seed_channels.csv",
    creator_category: str | None = None,
) -> None:
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, published_at, title,
              seed_source, excluded_flag, creator_category
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (video_id, video_id, channel_title, published_at, title, seed_source, creator_category),
        )
        conn.commit()


def _seed_existing_transcript(
    database_url: str, video_id: str, status: str = "available"
) -> None:
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO youtube_transcripts (
              video_id, status, full_text, provider_name, transcript_source,
              retrieval_method
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (video_id, status, "Existing transcript." if status == "available" else "",
             "test", "external_provider", "test"),
        )
        conn.commit()


class TestQueueSelection:
    def test_excludes_existing_transcripts(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "queue_exclude.db")
        _seed_raw_video(database_url, "video000001", "Creator A", "2024-01-15T00:00:00Z")
        _seed_raw_video(database_url, "video000002", "Creator B", "2024-02-15T00:00:00Z")
        _seed_existing_transcript(database_url, "video000001")

        result = select_apify_transcript_queue(
            start_date="2020-01-01",
            end_date="2026-05-12",
            max_videos=10,
        )

        selected_ids = {s.video_id for s in result.selected}
        assert "video000001" not in selected_ids
        assert "video000002" in selected_ids
        assert result.already_available == 1

    def test_dry_run_no_db_writes(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "dryrun.db")
        _seed_raw_video(database_url, "video000001", "Creator A", "2024-01-15T00:00:00Z")

        result = select_apify_transcript_queue(
            start_date="2020-01-01",
            end_date="2026-05-12",
            max_videos=10,
            dry_run=True,
        )

        assert len(result.selected) == 1
        with connect(database_url) as conn:
            runs = conn.execute(
                "SELECT COUNT(*) AS n FROM transcript_collection_runs"
            ).fetchone()["n"]
            assert runs == 0

    def test_excludes_permanent_unavailable(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "perm_unavail.db")
        _seed_raw_video(database_url, "video000001", "Creator A", "2024-01-15T00:00:00Z")
        _seed_raw_video(database_url, "video000002", "Creator B", "2024-02-15T00:00:00Z")
        _seed_existing_transcript(database_url, "video000001", "disabled")

        result = select_apify_transcript_queue(
            start_date="2020-01-01",
            end_date="2026-05-12",
            max_videos=10,
            retry_permanent=False,
        )

        selected_ids = {s.video_id for s in result.selected}
        assert "video000001" not in selected_ids
        assert result.excluded_permanent >= 1

    def test_retry_permanent_flag(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "retry_perm.db")
        _seed_raw_video(database_url, "video000001", "Creator A", "2024-01-15T00:00:00Z")
        _seed_existing_transcript(database_url, "video000001", "disabled")

        result = select_apify_transcript_queue(
            start_date="2020-01-01",
            end_date="2026-05-12",
            max_videos=10,
            retry_permanent=True,
        )

        selected_ids = {s.video_id for s in result.selected}
        assert "video000001" in selected_ids

    def test_respects_max_videos(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "max_videos.db")
        for i in range(15):
            _seed_raw_video(
                database_url,
                f"video{i:06d}",
                f"Creator {chr(65 + i % 5)}",
                f"2024-{(i % 12) + 1:02d}-15T00:00:00Z",
                f"Video {i}",
            )

        result = select_apify_transcript_queue(
            start_date="2020-01-01",
            end_date="2026-05-12",
            max_videos=5,
        )

        assert result.selected_count == 5

    def test_creator_filter(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "creator_filter.db")
        _seed_raw_video(database_url, "video000001", "Meet Kevin", "2024-01-15T00:00:00Z")
        _seed_raw_video(database_url, "video000002", "Tom Nash", "2024-02-15T00:00:00Z")

        result = select_apify_transcript_queue(
            start_date="2020-01-01",
            end_date="2026-05-12",
            max_videos=10,
            creator="Meet Kevin",
        )

        creators = {s.creator for s in result.selected}
        assert creators == {"Meet Kevin"}

    def test_year_filter(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "year_filter.db")
        _seed_raw_video(database_url, "video000001", "Creator A", "2023-06-15T00:00:00Z")
        _seed_raw_video(database_url, "video000002", "Creator B", "2024-06-15T00:00:00Z")

        result = select_apify_transcript_queue(
            start_date="2020-01-01",
            end_date="2026-05-12",
            max_videos=10,
            year=2024,
        )

        years = {s.year for s in result.selected}
        assert years == {2024}

    def test_segments_filter(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "segments.db")
        _seed_raw_video(database_url, "v1", "Creator A", "2024-01-15T00:00:00Z", creator_category="stock_picker")
        _seed_raw_video(database_url, "v2", "Creator B", "2024-02-15T00:00:00Z", creator_category="personal_finance")

        result = select_apify_transcript_queue(
            start_date="2020-01-01",
            end_date="2026-05-12",
            max_videos=10,
            segments=["stock_picker"],
        )

        selected_ids = {s.video_id for s in result.selected}
        assert "v1" in selected_ids
        assert "v2" not in selected_ids

    def test_exclude_segments_filter(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "exclude_segments.db")
        _seed_raw_video(database_url, "v1", "Creator A", "2024-01-15T00:00:00Z", creator_category="stock_picker")
        _seed_raw_video(database_url, "v2", "Creator B", "2024-02-15T00:00:00Z", creator_category="personal_finance")

        result = select_apify_transcript_queue(
            start_date="2020-01-01",
            end_date="2026-05-12",
            max_videos=10,
            exclude_segments=["personal_finance"],
        )

        selected_ids = {s.video_id for s in result.selected}
        assert "v1" in selected_ids
        assert "v2" not in selected_ids

    def test_title_keywords_filter(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "title_kw.db")
        _seed_raw_video(database_url, "v1", "Creator A", "2024-01-15T00:00:00Z", title="Top stocks to buy now")
        _seed_raw_video(database_url, "v2", "Creator B", "2024-02-15T00:00:00Z", title="Budgeting 101 for beginners")

        result = select_apify_transcript_queue(
            start_date="2020-01-01",
            end_date="2026-05-12",
            max_videos=10,
            title_keywords=["buy", "stocks"],
        )

        selected_ids = {s.video_id for s in result.selected}
        assert "v1" in selected_ids
        assert "v2" not in selected_ids

    def test_stratified_balance_by_creator(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "stratify.db")
        for i in range(30):
            _seed_raw_video(
                database_url,
                f"video{i:06d}",
                f"Creator {chr(65 + i % 3)}",
                f"2024-{(i % 12) + 1:02d}-15T00:00:00Z",
                f"Video {i}",
            )

        result = select_apify_transcript_queue(
            start_date="2020-01-01",
            end_date="2026-05-12",
            max_videos=12,
        )

        # Should have all 3 creators represented
        assert len(result.by_creator) > 1
        counts = list(result.by_creator.values())
        # No single creator should dominate excessively
        assert max(counts) <= 8


class TestApifyNormalization:
    def test_normalize_successful_result(self) -> None:
        raw = [
            {
                "url": "https://www.youtube.com/watch?v=video000001",
                "transcript": "Buy Nvidia stock now. It is undervalued.",
                "language": "en",
                "segments": [
                    {"text": "Buy Nvidia stock now.", "start": 0.0, "duration": 2.5},
                    {"text": "It is undervalued.", "start": 2.5, "duration": 1.5},
                ],
            }
        ]

        results, failures = _normalize_apify_output(
            raw, {"video000001"}, actor_id="test/actor", retrieved_at="2026-01-01T00:00:00Z"
        )

        assert len(results) == 1
        assert len(failures) == 0
        r = results[0]
        assert r.video_id == "video000001"
        assert r.status == "available"
        assert r.retrieval_method == "provider_apify_actor"
        assert r.provider_name == "apify/test/actor"
        assert r.segment_count == 2
        assert "Buy Nvidia stock now" in (r.full_text or "")

    def test_normalize_failed_result(self) -> None:
        raw = [
            {
                "url": "https://www.youtube.com/watch?v=video000002",
                "error": "captions_unavailable: No captions found for this video.",
            }
        ]

        results, failures = _normalize_apify_output(
            raw, {"video000002"}, actor_id="test/actor", retrieved_at="2026-01-01T00:00:00Z"
        )

        assert len(results) == 0
        assert len(failures) == 1
        f = failures[0]
        assert f["video_id"] == "video000002"
        assert f["error_type"] == "no_transcript"

    def test_normalize_missing_result(self) -> None:
        results, failures = _normalize_apify_output(
            [], {"video000003"}, actor_id="test/actor", retrieved_at="2026-01-01T00:00:00Z"
        )

        assert len(results) == 0
        assert len(failures) == 1
        assert failures[0]["error_type"] == "missing_result"

    def test_normalize_age_restricted(self) -> None:
        raw = [
            {
                "url": "https://www.youtube.com/watch?v=video000004",
                "error": "age_restricted: Video requires age verification.",
            }
        ]

        results, failures = _normalize_apify_output(
            raw, {"video000004"}, actor_id="test/actor", retrieved_at="2026-01-01T00:00:00Z"
        )

        assert len(results) == 0
        assert failures[0]["error_type"] == "unavailable"

    def test_normalize_no_transcript_text(self) -> None:
        raw = [
            {
                "url": "https://www.youtube.com/watch?v=video000005",
            }
        ]

        results, failures = _normalize_apify_output(
            raw, {"video000005"}, actor_id="test/actor", retrieved_at="2026-01-01T00:00:00Z"
        )

        assert len(results) == 0
        assert len(failures) == 1
        assert failures[0]["error_type"] == "no_transcript"

    def test_extract_video_id_from_various_url_formats(self) -> None:
        from finfluencer_alpha.apify_transcripts import _extract_video_id

        assert _extract_video_id("https://www.youtube.com/watch?v=abc123def45") == "abc123def45"
        assert _extract_video_id("https://youtu.be/abc123def45") == "abc123def45"
        assert _extract_video_id("https://www.youtube.com/watch?v=abc123def45&t=30") == "abc123def45"


class TestSecondActorNormalization:
    def test_normalize_scrape_creators_output(self) -> None:
        raw = [
            {
                "video_url": "https://www.youtube.com/watch?v=test123abcd",
                "transcript_only_text": "This stock is a strong buy right now.",
                "videoId": "test123abcd",
                "language": "en",
                "title": "Best Stocks 2024",
            }
        ]

        results, failures = _normalize_apify_output(
            raw, {"test123abcd"}, actor_id="scrape-creators/best-youtube-transcripts-scraper",
            retrieved_at="2026-01-01T00:00:00Z"
        )

        assert len(results) == 1
        assert len(failures) == 0
        r = results[0]
        assert r.video_id == "test123abcd"
        assert r.status == "available"
        assert "strong buy" in (r.full_text or "")

    def test_normalize_scrape_creators_from_videoId(self) -> None:
        raw = [
            {
                "videoId": "test123abcd",
                "transcript_only_text": "I'm buying NVDA at this level.",
            }
        ]

        results, failures = _normalize_apify_output(
            raw, {"test123abcd"}, actor_id="scrape-creators/best-youtube-transcripts-scraper",
            retrieved_at="2026-01-01T00:00:00Z"
        )

        assert len(results) == 1
        assert results[0].video_id == "test123abcd"

    def test_normalize_scrape_creators_with_timestamps(self) -> None:
        raw = [
            {
                "video_url": "https://www.youtube.com/watch?v=test123abcd",
                "transcript_only_text": "Buy now.",
                "timestamps": [
                    {"text": "We like this stock.", "start": 0.0, "duration": 2.5},
                    {"text": "Buy now.", "start": 2.5, "duration": 1.5},
                ],
            }
        ]

        results, failures = _normalize_apify_output(
            raw, {"test123abcd"}, actor_id="scrape-creators/best-youtube-transcripts-scraper",
            retrieved_at="2026-01-01T00:00:00Z"
        )

        assert len(results) == 1
        assert results[0].segment_count == 2

    def test_normalize_scrape_creators_empty_output(self) -> None:
        raw: list[dict[str, object]] = []

        results, failures = _normalize_apify_output(
            raw, {"test123abcd"}, actor_id="scrape-creators/best-youtube-transcripts-scraper",
            retrieved_at="2026-01-01T00:00:00Z"
        )

        assert len(results) == 0
        assert len(failures) == 1
        assert failures[0]["error_type"] == "missing_result"

    def test_normalize_scrape_creators_no_transcript(self) -> None:
        raw = [
            {
                "video_url": "https://www.youtube.com/watch?v=test123abcd",
            }
        ]

        results, failures = _normalize_apify_output(
            raw, {"test123abcd"}, actor_id="scrape-creators/best-youtube-transcripts-scraper",
            retrieved_at="2026-01-01T00:00:00Z"
        )

        assert len(results) == 0
        assert failures[0]["error_type"] == "no_transcript"


class TestSecondActorInputFormat:
    def test_supreme_coder_uses_urls_shape(self) -> None:
        from finfluencer_alpha.apify_transcripts import _start_apify_run

        intercepted: list[dict[str, object]] = []
        original_post = requests.post

        def fake_post(url, **kwargs):
            intercepted.append({"url": str(url), "json": kwargs.get("json", {})})
            return FakeResponse({"data": {"id": "run_123"}})

        import finfluencer_alpha.apify_transcripts as mod
        mod.requests.post = fake_post
        try:
            _start_apify_run(
                "supreme_coder/youtube-transcript-scraper",
                ["https://www.youtube.com/watch?v=vid1"],
                "fake-token",
            )
            assert len(intercepted) == 1
            payload = intercepted[0]["json"]
            assert payload["urls"] == [{"url": "https://www.youtube.com/watch?v=vid1"}]
            assert payload["outputFormat"] == "json"
            assert payload["languages"] == ["en"]
            assert "videoUrls" not in payload
            assert "startUrls" not in payload
            assert "searchTerms" not in payload
            assert "urlList" not in payload
            assert "videos" not in payload
        finally:
            mod.requests.post = original_post

    def test_scrape_creators_uses_videoUrls(self) -> None:
        from finfluencer_alpha.apify_transcripts import _start_apify_run

        intercepted: list[dict[str, object]] = []
        original_post = requests.post

        def fake_post(url, **kwargs):
            intercepted.append({"url": str(url), "json": kwargs.get("json", {})})
            return FakeResponse({"data": {"id": "run_456"}})

        import finfluencer_alpha.apify_transcripts as mod
        mod.requests.post = fake_post
        try:
            _start_apify_run(
                "scrape-creators/best-youtube-transcripts-scraper",
                ["https://www.youtube.com/watch?v=vid1"],
                "fake-token",
            )
            assert len(intercepted) == 1
            assert "videoUrls" in intercepted[0]["json"]
            assert intercepted[0]["json"]["videoUrls"] == ["https://www.youtube.com/watch?v=vid1"]
        finally:
            mod.requests.post = original_post

    def test_supported_fallback_actor_input_builders(self) -> None:
        video_urls = ["https://www.youtube.com/watch?v=vid1"]

        assert _build_apify_input(
            "seemuapps/youtube-transcript-scraper", video_urls
        ) == {"videoUrls": video_urls, "languages": ["en"]}
        assert _build_apify_input(
            "curious_coder/youtube-transcript-scraper", video_urls
        ) == {
            "urls": [{"url": video_urls[0]}],
            "languages": ["en"],
            "outputFormat": "json",
        }
        assert _build_apify_input(
            "muhammad_noman_riaz/youtube-video-transcript-super-scraper",
            video_urls,
        ) == {
            "startUrls": [{"url": video_urls[0]}],
            "includeTranscript": True,
            "language": "en",
        }
        assert _build_apify_input(
            "powerai/youtube-transcript-scraper", video_urls
        ) == {"videoUrls": [{"url": video_urls[0]}]}
        assert _build_apify_input(
            "pintostudio/youtube-transcript-scraper", video_urls
        ) == {"videoUrl": video_urls[0], "language": "en"}

    def test_supreme_coder_language_fallback_payload(self) -> None:
        video_urls = ["https://www.youtube.com/watch?v=vid1"]
        payload = _build_apify_input(
            "supreme_coder/youtube-transcript-scraper",
            video_urls,
            languages=["en", "en-US", "en-GB"],
        )
        assert payload["urls"] == [{"url": video_urls[0]}]
        assert payload["languages"] == ["en", "en-US", "en-GB"]


class TestFallbackActorNormalization:
    def test_normalize_seemuapps_output(self) -> None:
        raw = [
            {
                "inputUrl": "https://www.youtube.com/watch?v=video000006",
                "videoId": "video000006",
                "language": "en",
                "isAutoGenerated": False,
                "transcript": "Buy Apple stock after earnings.",
                "segments": [
                    {"startMs": 0, "durationMs": 2000, "text": "Buy Apple stock"},
                    {"startMs": 2000, "durationMs": 1500, "text": "after earnings."},
                ],
                "status": "success",
            }
        ]
        results, failures = _normalize_apify_output(
            raw,
            {"video000006"},
            actor_id="seemuapps/youtube-transcript-scraper",
            retrieved_at="2026-01-01T00:00:00Z",
            provider_run_id="run_seemu",
        )
        assert not failures
        assert results[0].provider_actor_id == "seemuapps/youtube-transcript-scraper"
        assert results[0].provider_run_id == "run_seemu"
        assert results[0].segment_count == 2
        assert results[0].segments[0].start_seconds == 0.0

    def test_normalize_curious_coder_output(self) -> None:
        raw = [
            {
                "inputUrl": "https://www.youtube.com/watch?v=video000007",
                "languageCode": "en",
                "isGenerated": True,
                "transcript": [
                    {"text": "I am buying Tesla.", "start": 0.04, "duration": 2.5},
                    {"text": "Price target goes higher.", "start": 2.54, "duration": 2.0},
                ],
            }
        ]
        results, failures = _normalize_apify_output(
            raw,
            {"video000007"},
            actor_id="curious_coder/youtube-transcript-scraper",
            retrieved_at="2026-01-01T00:00:00Z",
        )
        assert not failures
        assert "buying Tesla" in (results[0].full_text or "")
        assert results[0].is_asr_generated is True

    def test_normalize_mnr_output(self) -> None:
        raw = [
            {
                "videoId": "video000008",
                "transcript_only_text": "Semiconductor stocks are rallying.",
                "transcript": [
                    {"text": "Semiconductor stocks", "startMs": 0, "endMs": 1200},
                    {"text": "are rallying.", "startMs": 1200, "endMs": 2300},
                ],
            }
        ]
        results, failures = _normalize_apify_output(
            raw,
            {"video000008"},
            actor_id="muhammad_noman_riaz/youtube-video-transcript-super-scraper",
            retrieved_at="2026-01-01T00:00:00Z",
        )
        assert not failures
        assert results[0].segment_count == 2
        assert results[0].segments[1].duration_seconds == 1.1

    def test_normalize_powerai_output(self) -> None:
        raw = [
            {
                "videoUrl": "https://www.youtube.com/watch?v=video000009",
                "videoId": "video000009",
                "transcript": [
                    {"text": "This is my position.", "timestamp": "0:05"},
                    {"text": "I am selling half.", "timestamp": "0:09"},
                ],
            }
        ]
        results, failures = _normalize_apify_output(
            raw,
            {"video000009"},
            actor_id="powerai/youtube-transcript-scraper",
            retrieved_at="2026-01-01T00:00:00Z",
        )
        assert not failures
        assert results[0].segments[0].start_seconds == 5.0
        assert "selling half" in (results[0].full_text or "")

    def test_normalize_pintostudio_output(self) -> None:
        raw = [
            {
                "searchResult": [
                    {"start": "0.320", "dur": "4.080", "text": "Undervalued stock."},
                    {"start": "4.400", "dur": "3.000", "text": "Buying more."},
                ]
            }
        ]
        results, failures = _normalize_apify_output(
            raw,
            {"video000010"},
            actor_id="pintostudio/youtube-transcript-scraper",
            retrieved_at="2026-01-01T00:00:00Z",
        )
        assert not failures
        assert results[0].video_id == "video000010"
        assert results[0].segment_count == 2


class TestApifyCLI:
    def test_dry_run_command(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "cli_dryrun.db")
        monkeypatch.setenv("APIFY_TOKEN", "test-token")
        _seed_raw_video(database_url, "video000001", "Creator A", "2024-01-15T00:00:00Z")
        _seed_raw_video(database_url, "video000002", "Creator B", "2024-02-15T00:00:00Z")
        get_settings.cache_clear()

        result = CliRunner().invoke(
            app,
            [
                "collect-apify-transcripts",
                "--dry-run",
                "--max-videos",
                "5",
            ],
            env={
                "DATABASE_URL": database_url,
                "APIFY_TOKEN": "test-token",
            },
        )

        assert result.exit_code == 0
        assert "Dry run complete" in result.output

    def test_dry_run_no_token_needed(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "cli_notok.db")
        monkeypatch.setenv("APIFY_TOKEN", "")
        _seed_raw_video(database_url, "video000001", "Creator A", "2024-01-15T00:00:00Z")
        get_settings.cache_clear()

        result = CliRunner().invoke(
            app,
            [
                "collect-apify-transcripts",
                "--dry-run",
                "--max-videos",
                "1",
            ],
            env={
                "DATABASE_URL": database_url,
            },
        )

        assert result.exit_code == 0
        assert "Dry run complete" in result.output

    def test_live_run_missing_token(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "cli_missing.db")
        monkeypatch.setenv("APIFY_TOKEN", "")
        _seed_raw_video(database_url, "video000001", "Creator A", "2024-01-15T00:00:00Z")
        get_settings.cache_clear()

        result = CliRunner().invoke(
            app,
            [
                "collect-apify-transcripts",
                "--max-videos",
                "1",
            ],
            env={
                "DATABASE_URL": database_url,
            },
        )

        assert result.exit_code == 1
        assert "Missing APIFY_TOKEN" in result.output

    def test_cli_filter_flags(self, monkeypatch, tmp_path: Path) -> None:
        database_url = _use_temp_db(monkeypatch, tmp_path, "cli_filter_flags.db")
        monkeypatch.setenv("APIFY_TOKEN", "test-token")
        _seed_raw_video(database_url, "v1", "Creator A", "2024-01-15T00:00:00Z", title="Top stocks to buy now", creator_category="stock_picker")
        _seed_raw_video(database_url, "v2", "Creator B", "2024-02-15T00:00:00Z", title="Budgeting 101", creator_category="personal_finance")
        get_settings.cache_clear()

        result = CliRunner().invoke(
            app,
            [
                "collect-apify-transcripts",
                "--dry-run",
                "--segments", "stock_picker",
                "--exclude-segments", "personal_finance",
                "--title-keywords", "buy,stocks",
                "--only-missing-transcripts",
                "--max-videos", "10",
            ],
            env={
                "DATABASE_URL": database_url,
                "APIFY_TOKEN": "test-token",
            },
        )

        assert result.exit_code == 0
        assert "v1" in result.output
        assert "v2" not in result.output


class TestTokenSafety:
    def test_token_not_printed_in_logs(self, monkeypatch) -> None:
        monkeypatch.setenv("APIFY_TOKEN", "my-secret-token-123")
        get_settings.cache_clear()

        token = _resolve_apify_token()
        assert token == "my-secret-token-123"

        settings = get_settings()
        assert settings.apify_token == "my-secret-token-123"

        monkeypatch.setenv("APIFY_TOKEN", "")
        get_settings.cache_clear()

    def test_missing_token_raises_gracefully(self, monkeypatch) -> None:
        monkeypatch.setenv("APIFY_TOKEN", "")
        get_settings.cache_clear()

        with pytest.raises(ApifyConfigError, match="Missing APIFY_TOKEN"):
            _resolve_apify_token()


class TestFallbackRouting:
    def test_provider_order(self, monkeypatch) -> None:
        monkeypatch.setenv("TRANSCRIPTAPI_KEY", "test-key")
        monkeypatch.setenv("APIFY_TOKEN", "test-token")
        get_settings.cache_clear()

        chain = resolve_provider_chain(video_id="video000001")

        tiers = [t.value for t in chain]
        assert "paid_api" in tiers
        assert "apify" in tiers
        assert "native_package" in tiers
        assert "yt_dlp" in tiers


def test_apify_actor_benchmark_is_measurement_only(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "apify_benchmark.db")
    monkeypatch.setenv("APIFY_TOKEN", "test-token")
    get_settings.cache_clear()
    _seed_raw_video(database_url, "video000011", "Creator A", "2025-01-15T00:00:00Z")

    monkeypatch.setattr(
        "finfluencer_alpha.apify_benchmark._start_apify_run",
        lambda *args, **kwargs: {"data": {"id": "bench_run_1"}},
    )
    monkeypatch.setattr(
        "finfluencer_alpha.apify_benchmark._wait_for_run",
        lambda *args, **kwargs: {"status": "SUCCEEDED", "usageTotalUsd": 0.01},
    )
    monkeypatch.setattr(
        "finfluencer_alpha.apify_benchmark._fetch_run_results",
        lambda *args, **kwargs: [
            {
                "inputUrl": "https://www.youtube.com/watch?v=video000011",
                "videoId": "video000011",
                "transcript": "Buying the stock on weakness.",
                "segments": [{"text": "Buying the stock on weakness.", "startMs": 0, "durationMs": 1000}],
                "status": "success",
            }
        ],
    )

    result = benchmark_apify_transcript_actors(
        actors=["seemuapps/youtube-transcript-scraper"],
        start_date="2024-01-01",
        end_date="2026-05-12",
        max_videos_per_actor=1,
        batch_size=1,
        max_total_charge_usd=0.10,
        only_missing_transcripts=True,
    )

    assert result.actor_rows[0]["successful_transcripts"] == 1
    assert result.actor_rows[0]["cost_per_success_usd"] == 0.01
    with connect(database_url) as conn:
        stored = conn.execute(
            "SELECT COUNT(*) AS n FROM youtube_transcripts"
        ).fetchone()["n"]
    assert stored == 0


def test_benchmark_cli_accepts_workflow_actor_syntax(monkeypatch) -> None:
    from pathlib import Path as _Path
    from types import SimpleNamespace

    captured: dict[str, object] = {}

    def fake_benchmark(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            actor_rows=[
                {
                    "actor_id": "seemuapps/youtube-transcript-scraper",
                    "successful_transcripts": 1,
                    "attempted": 1,
                    "success_rate": 1.0,
                    "cost_usd": 0.01,
                    "cost_per_success_usd": 0.01,
                }
            ],
            selected_video_ids=["video000012"],
            csv_path=_Path("data/exports/transcripts/bench.csv"),
            markdown_path=_Path("data/exports/transcripts/bench.md"),
        )

    monkeypatch.setattr(
        "finfluencer_alpha.apify_benchmark.benchmark_apify_transcript_actors",
        fake_benchmark,
    )

    result = CliRunner().invoke(
        app,
        [
            "benchmark-apify-transcript-actors",
            "--actors",
            "seemuapps/youtube-transcript-scraper",
            "curious_coder/youtube-transcript-scraper",
            "--only-missing-transcripts",
            "--max-total-charge-usd",
            "0.50",
        ],
    )

    assert result.exit_code == 0
    assert captured["actors"] == [
        "seemuapps/youtube-transcript-scraper",
        "curious_coder/youtube-transcript-scraper",
    ]

    def test_provider_order_no_apify_token(self, monkeypatch) -> None:
        monkeypatch.setenv("TRANSCRIPTAPI_KEY", "test-key")
        monkeypatch.setenv("APIFY_TOKEN", "")
        get_settings.cache_clear()

        chain = resolve_provider_chain(video_id="video000001")

        tiers = [t.value for t in chain]
        assert "apify" not in tiers

    def test_excludes_attempted_tiers(self, monkeypatch) -> None:
        monkeypatch.setenv("APIFY_TOKEN", "test-token")
        get_settings.cache_clear()

        chain = resolve_provider_chain(
            video_id="video000001",
            attempted_tiers=frozenset({ProviderTier.APIFY}),
        )

        tiers = [t.value for t in chain]
        assert "apify" not in tiers

    def test_no_free_tiers_returns_empty(self, monkeypatch) -> None:
        monkeypatch.setenv("TRANSCRIPTAPI_KEY", "")
        monkeypatch.setenv("YOUTUBETRANSCRIPT_DEV_API_KEY", "")
        monkeypatch.setenv("APIFY_TOKEN", "")
        get_settings.cache_clear()

        chain = resolve_provider_chain(
            video_id="video000001",
            attempted_tiers=frozenset(
                {ProviderTier.NATIVE_PACKAGE, ProviderTier.YT_DLP}
            ),
        )

        assert len(chain) == 0
