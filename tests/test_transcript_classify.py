from pathlib import Path

from finfluencer_alpha.config import get_settings
from finfluencer_alpha.db import connect, init_db
from finfluencer_alpha.transcript_classify import build_transcript_recommendation_events
from finfluencer_alpha.youtube_transcripts import (
    TranscriptFetchResult,
    TranscriptSegment,
    store_transcript_result,
)


def _use_temp_db(monkeypatch, tmp_path: Path, name: str) -> str:
    database_url = f"sqlite:///{tmp_path / name}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    init_db(database_url)
    return database_url


def _seed_video_and_transcript(
    database_url: str,
    segments: list[tuple[float, float, str]],
    video_id: str = "video123",
) -> None:
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO raw_youtube_videos (
              video_id, channel_id, channel_title, published_at, title, url
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                "channel123",
                "Test Channel",
                "2026-01-01T00:00:00Z",
                "Test video",
                f"https://www.youtube.com/watch?v={video_id}",
            ),
        )
        result = TranscriptFetchResult(
            video_id=video_id,
            provider_name="youtube_transcript_api",
            provider_version="1.2.4",
            status="available",
            language="English",
            language_code="en",
            is_generated=False,
            is_translatable=True,
            full_text=" ".join(segment[2] for segment in segments),
            full_text_sha256="sha",
            raw_json="[]",
            segments=[
                TranscriptSegment(
                    video_id=video_id,
                    segment_index=index,
                    start_seconds=start,
                    duration_seconds=duration,
                    text=text,
                )
                for index, (start, duration, text) in enumerate(segments)
            ],
        )
        store_transcript_result(conn, result)
        conn.commit()


def _events_and_windows(database_url: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    with connect(database_url) as conn:
        events = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM transcript_recommendation_events ORDER BY ticker"
            ).fetchall()
        ]
        windows = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM transcript_candidate_windows ORDER BY ticker"
            ).fetchall()
        ]
    return events, windows


def test_buying_nvidia_stock_creates_bullish_nvda_event(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "bullish.db")
    _seed_video_and_transcript(database_url, [(10.0, 4.0, "I am buying Nvidia stock")])

    result = build_transcript_recommendation_events(refresh_existing=True)
    events, windows = _events_and_windows(database_url)

    assert result.events == 1
    assert result.candidate_windows == 1
    assert events[0]["ticker"] == "NVDA"
    assert events[0]["stance"] == "bullish"
    assert events[0]["confidence_label"] == "high"
    assert windows[0]["accepted_event_flag"] == 1


def test_avoid_tesla_creates_bearish_tsla_event(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "bearish.db")
    _seed_video_and_transcript(database_url, [(20.0, 4.0, "I would avoid Tesla here")])

    build_transcript_recommendation_events(refresh_existing=True)
    events, _ = _events_and_windows(database_url)

    assert len(events) == 1
    assert events[0]["ticker"] == "TSLA"
    assert events[0]["stance"] == "bearish"


def test_nvidia_reported_earnings_is_rejected_window(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "news.db")
    _seed_video_and_transcript(database_url, [(30.0, 4.0, "Nvidia reported earnings today")])

    build_transcript_recommendation_events(refresh_existing=True)
    events, windows = _events_and_windows(database_url)

    assert events == []
    assert len(windows) == 1
    assert windows[0]["ticker"] == "NVDA"
    assert windows[0]["accepted_event_flag"] == 0
    assert windows[0]["exclusion_reason"] == "news_only"


def test_negated_buy_language_does_not_create_bullish_event(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "negated.db")
    _seed_video_and_transcript(
        database_url,
        [(30.0, 4.0, "I can understand not wanting to buy PayPal because it is murky")],
    )

    build_transcript_recommendation_events(refresh_existing=True)
    events, windows = _events_and_windows(database_url)

    assert events == []
    assert len(windows) == 1
    assert windows[0]["ticker"] == "PYPL"
    assert windows[0]["accepted_event_flag"] == 0
    assert windows[0]["exclusion_reason"] == "negated_action"


def test_follow_me_on_facebook_does_not_create_meta_window(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "facebook.db")
    _seed_video_and_transcript(database_url, [(40.0, 4.0, "Follow me on Facebook")])

    build_transcript_recommendation_events(refresh_existing=True)
    events, windows = _events_and_windows(database_url)

    assert events == []
    assert windows == []


def test_local_action_attribution_creates_amd_only(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "local_action.db")
    _seed_video_and_transcript(
        database_url,
        [(50.0, 4.0, "I like Nvidia but I am buying AMD")],
    )

    build_transcript_recommendation_events(refresh_existing=True)
    events, windows = _events_and_windows(database_url)

    assert [event["ticker"] for event in events] == ["AMD"]
    nvda_window = next(window for window in windows if window["ticker"] == "NVDA")
    assert nvda_window["accepted_event_flag"] == 0
    assert nvda_window["focused_action_text"] == "I like Nvidia"


def test_duplicate_mentions_in_nearby_window_create_one_event(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "dedupe.db")
    _seed_video_and_transcript(
        database_url,
        [
            (10.0, 4.0, "I am buying Nvidia stock"),
            (20.0, 4.0, "Nvidia stock is still a buy"),
        ],
    )

    build_transcript_recommendation_events(refresh_existing=True)
    events, windows = _events_and_windows(database_url)

    assert len(events) == 1
    assert len(windows) == 1
    assert events[0]["ticker"] == "NVDA"


def test_transcript_event_includes_timestamp_window(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "timestamps.db")
    _seed_video_and_transcript(
        database_url,
        [
            (0.0, 3.0, "Market overview"),
            (20.0, 4.0, "I am buying Nvidia stock"),
            (45.0, 5.0, "More valuation discussion"),
        ],
    )

    build_transcript_recommendation_events(refresh_existing=True)
    events, _ = _events_and_windows(database_url)

    assert events[0]["evidence_start_seconds"] == 0.0
    assert events[0]["evidence_end_seconds"] == 50.0
    assert "I am buying Nvidia stock" in events[0]["evidence_window"]


def test_retrospective_buy_signal_is_rejected(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "retro_signal.db")
    _seed_video_and_transcript(
        database_url,
        [(30.0, 4.0, "I sent a course member signal to buy Nvidia and that investment turned into multi-millions")],
    )

    build_transcript_recommendation_events(refresh_existing=True)
    events, windows = _events_and_windows(database_url)

    assert events == []
    assert len(windows) == 1
    assert windows[0]["ticker"] == "NVDA"
    assert windows[0]["accepted_event_flag"] == 0
    assert windows[0]["exclusion_reason"] == "retrospective_claim"


def test_we_have_been_bullish_since_is_retrospective(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "bullish_since.db")
    _seed_video_and_transcript(
        database_url,
        [(30.0, 4.0, "We've been bullish since the beginning of April on Apple")],
    )

    build_transcript_recommendation_events(refresh_existing=True)
    events, windows = _events_and_windows(database_url)

    assert events == []
    assert len(windows) == 1
    assert windows[0]["ticker"] == "AAPL"
    assert windows[0]["accepted_event_flag"] == 0
    assert windows[0]["exclusion_reason"] == "retrospective_claim"


def test_third_party_attribution_is_rejected(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "thirdparty.db")
    _seed_video_and_transcript(
        database_url,
        [(30.0, 4.0, "Mutual funds and investors have suggested selling Tesla to fund purchases of SpaceX")],
    )

    build_transcript_recommendation_events(refresh_existing=True)
    events, windows = _events_and_windows(database_url)

    assert events == []
    assert len(windows) == 1
    assert windows[0]["ticker"] == "TSLA"
    assert windows[0]["accepted_event_flag"] == 0
    assert windows[0]["exclusion_reason"] == "third_party_attribution"


def test_ambiguous_not_even_talking_about_buy_is_rejected(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "ambiguous.db")
    _seed_video_and_transcript(
        database_url,
        [(30.0, 4.0, "we're not even talking about that Apple buy, that's a whole other story")],
    )

    build_transcript_recommendation_events(refresh_existing=True)
    events, windows = _events_and_windows(database_url)

    assert events == []
    assert len(windows) == 1
    assert windows[0]["ticker"] == "AAPL"
    assert windows[0]["accepted_event_flag"] == 0
    assert windows[0]["exclusion_reason"] == "ambiguous_reference"


def test_sofi_buy_zone_is_valid_bullish_event(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "sofi_valid.db")
    _seed_video_and_transcript(
        database_url,
        [(30.0, 4.0, "SoFi under $15 is a great buy zone for this company")],
    )

    build_transcript_recommendation_events(refresh_existing=True)
    events, _ = _events_and_windows(database_url)

    assert len(events) == 1
    assert events[0]["ticker"] == "SOFI"
    assert events[0]["stance"] == "bullish"
    assert events[0]["confidence_label"] in ("high", "medium")


def test_sofi_100_plus_stock_is_valid_bullish_thesis(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "sofi_thesis.db")
    _seed_video_and_transcript(
        database_url,
        [(30.0, 4.0, "SoFi has a great opportunity to be a $100 plus stock long term")],
    )

    build_transcript_recommendation_events(refresh_existing=True)
    events, _ = _events_and_windows(database_url)

    assert len(events) == 1
    assert events[0]["ticker"] == "SOFI"
    assert events[0]["stance"] == "bullish"
    assert events[0]["confidence_label"] in ("high", "medium")


def test_googl_window_retrospective_is_rejected(monkeypatch, tmp_path: Path) -> None:
    database_url = _use_temp_db(monkeypatch, tmp_path, "googl_edge.db")
    _seed_video_and_transcript(
        database_url,
        [
            (0.0, 3.0, "We literally just hit our triple Q's price target."),
            (3.0, 4.0, "We've been bullish since the beginning of April."),
            (7.0, 3.0, "And we're even seeing the breakout on Google right now."),
        ],
    )

    build_transcript_recommendation_events(refresh_existing=True)
    events, windows = _events_and_windows(database_url)

    googl_windows = [w for w in windows if w["ticker"] == "GOOGL"]
    assert len(googl_windows) <= 1
    if googl_windows:
        assert googl_windows[0]["accepted_event_flag"] == 0
        assert googl_windows[0]["exclusion_reason"] == "retrospective_claim"
