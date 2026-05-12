from __future__ import annotations

import csv
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .classify import STRONG_RETROSPECTIVE_KEYWORDS, classify_text
from .config import EXPORTS_DIR, get_settings
from .db import connect, init_db
from .ticker_extract import COMPANY_ALIAS_TO_TICKER, extract_tickers

EVIDENCE_WINDOW_SECONDS = 30.0
LOCAL_ACTION_WORD_RADIUS = 12
TRANSCRIPT_EXPORT_DIR = EXPORTS_DIR / "transcripts"
DEFAULT_NEW_EXTRACTION_SUMMARY_CSV = (
    TRANSCRIPT_EXPORT_DIR / "new_transcript_event_extraction_summary.csv"
)
DEFAULT_NEW_EXTRACTION_SUMMARY_MD = (
    TRANSCRIPT_EXPORT_DIR / "new_transcript_event_extraction_summary.md"
)

EXPLICIT_ACTION_RE = re.compile(
    r"(?<![a-z0-9])("
    r"buy|buying|bought|adding|added|long|own\s+it|calls|"
    r"sell|selling|short|avoid|puts|price\s+target|pt|target"
    r")(?![a-z0-9])",
    re.IGNORECASE,
)
NEGATED_ACTION_RE = re.compile(
    r"(?<![a-z0-9])("
    r"not\s+(?:want(?:ing)?\s+to\s+|going\s+to\s+)?(?:buy|own|add|long)|"
    r"(?:do\s+not|don't|cannot|can't|won't)\s+(?:want\s+to\s+)?(?:buy|own|add|go\s+long)"
    r")(?![a-z0-9])",
    re.IGNORECASE,
)

CANONICAL_COMPANY_NAMES = {
    "TSLA": "Tesla",
    "NVDA": "Nvidia",
    "AAPL": "Apple",
    "AMZN": "Amazon",
    "GOOGL": "Alphabet",
    "META": "Meta",
    "PLTR": "Palantir",
    "SOFI": "SoFi",
    "MSFT": "Microsoft",
    "COIN": "Coinbase",
    "HOOD": "Robinhood",
    "UBER": "Uber",
    "NFLX": "Netflix",
    "DIS": "Disney",
    "PYPL": "PayPal",
    "SHOP": "Shopify",
    "ROKU": "Roku",
    "SMCI": "Super Micro",
    "MSTR": "MicroStrategy",
}

TICKER_TO_ALIASES: dict[str, list[str]] = {}
for alias, ticker in COMPANY_ALIAS_TO_TICKER.items():
    TICKER_TO_ALIASES.setdefault(ticker, []).append(alias)


@dataclass(frozen=True)
class TranscriptSegmentRow:
    video_id: str
    segment_index: int
    start_seconds: float | None
    duration_seconds: float | None
    text: str

    @property
    def end_seconds(self) -> float | None:
        if self.start_seconds is None:
            return None
        return self.start_seconds + (self.duration_seconds or 0)


@dataclass(frozen=True)
class TranscriptMention:
    video_id: str
    ticker: str
    mention_text: str
    segment_index: int
    anchor_seconds: float | None


@dataclass(frozen=True)
class TranscriptWindow:
    video_id: str
    transcript_source: str
    provider_name: str
    transcript_collected_at: str
    ticker: str
    company_name: str
    mention_text: str
    evidence_start_seconds: float | None
    evidence_end_seconds: float | None
    evidence_window: str
    focused_action_text: str


@dataclass(frozen=True)
class TranscriptBuildResult:
    candidate_windows: int
    events: int


@dataclass(frozen=True)
class IncrementalTranscriptExtractionResult:
    summary_csv_path: Path
    summary_md_path: Path
    transcripts_scanned: int
    transcripts_skipped_already_processed: int
    new_ticker_mentions_found: int
    new_candidate_windows_found: int
    new_events_found: int
    new_excluded_windows: int
    creators_represented: int
    years_represented: int


def _clean_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _mention_terms(ticker: str) -> list[str]:
    terms = [rf"\${re.escape(ticker)}", re.escape(ticker)]
    terms.extend(re.escape(alias) for alias in TICKER_TO_ALIASES.get(ticker, []))
    return terms


def _ticker_pattern(ticker: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9])(" + "|".join(_mention_terms(ticker)) + r")(?![A-Za-z0-9])")


def _contains_ticker(text: str, ticker: str) -> bool:
    return _ticker_pattern(ticker).search(text) is not None


def _focused_action_text(evidence_window: str, ticker: str) -> str:
    match = _ticker_pattern(ticker).search(evidence_window)
    if not match:
        return ""
    clause_start = 0
    clause_end = len(evidence_window)
    for separator in [".", "?", "!", ";", "\n"]:
        index = evidence_window.rfind(separator, 0, match.start())
        if index >= 0:
            clause_start = max(clause_start, index + 1)
    for separator in [".", "?", "!", ";", "\n"]:
        index = evidence_window.find(separator, match.end())
        if index >= 0:
            clause_end = min(clause_end, index)

    clause = evidence_window[clause_start:clause_end]
    local_parts = re.split(r"\b(?:but|however|although|while|whereas)\b|,", clause, flags=re.I)
    for part in local_parts:
        if _contains_ticker(part, ticker):
            return _clean_text(part)

    words = list(re.finditer(r"\S+", evidence_window))
    mention_word_index = 0
    for index, word in enumerate(words):
        if word.start() <= match.start() < word.end():
            mention_word_index = index
            break
    start = max(0, mention_word_index - LOCAL_ACTION_WORD_RADIUS)
    end = min(len(words), mention_word_index + LOCAL_ACTION_WORD_RADIUS + 1)
    return _clean_text(" ".join(word.group(0) for word in words[start:end]))


def _confidence_label(
    label: str,
    actionability_score: int,
    focused_action_text: str,
    accepted: bool,
) -> str:
    if not accepted:
        exclude_labels = {
            "news_only", "retrospective_claim", "portfolio_disclosure",
            "non_actionable_hype", "third_party_attribution", "ambiguous_reference",
        }
        if label in exclude_labels:
            return "exclude"
        return "low"
    if actionability_score >= 3 and EXPLICIT_ACTION_RE.search(focused_action_text):
        return "high"
    return "medium"


def _exclusion_reason(
    result_label: str,
    accepted: bool,
    focused_text: str,
    ticker: str,
    negated_action: bool = False,
) -> str | None:
    if accepted:
        return None
    if not focused_text or not _contains_ticker(focused_text, ticker):
        return "cross_attributed_action"
    if negated_action:
        return "negated_action"
    if result_label == "third_party_attribution":
        return "third_party_attribution"
    if result_label == "ambiguous_reference":
        return "ambiguous_reference"
    if result_label == "news_only":
        return "news_only"
    if result_label == "retrospective_claim":
        return "retrospective_claim"
    if result_label == "portfolio_disclosure":
        return "disclosure_only"
    if result_label == "non_actionable_hype":
        return "non_actionable_hype"
    return "no_actionable_recommendation"


def _load_segments(conn: sqlite3.Connection, video_id: str) -> list[TranscriptSegmentRow]:
    rows = conn.execute(
        """
        SELECT video_id, segment_index, start_seconds, duration_seconds, text
        FROM youtube_transcript_segments
        WHERE video_id = ?
        ORDER BY segment_index
        """,
        (video_id,),
    ).fetchall()
    return [
        TranscriptSegmentRow(
            video_id=row["video_id"],
            segment_index=row["segment_index"],
            start_seconds=row["start_seconds"],
            duration_seconds=row["duration_seconds"],
            text=row["text"] or "",
        )
        for row in rows
    ]


def _segment_mentions(segments: list[TranscriptSegmentRow]) -> list[TranscriptMention]:
    mentions: list[TranscriptMention] = []
    for segment in segments:
        seen_tickers: set[str] = set()
        for mention in extract_tickers(segment.text):
            if mention.ticker in seen_tickers:
                continue
            seen_tickers.add(mention.ticker)
            mentions.append(
                TranscriptMention(
                    video_id=segment.video_id,
                    ticker=mention.ticker,
                    mention_text=mention.mention_text,
                    segment_index=segment.segment_index,
                    anchor_seconds=segment.start_seconds,
                )
            )
    return mentions


def _dedupe_mentions(mentions: list[TranscriptMention]) -> list[TranscriptMention]:
    deduped: list[TranscriptMention] = []
    grouped: dict[tuple[str, str], list[TranscriptMention]] = {}
    for mention in mentions:
        grouped.setdefault((mention.video_id, mention.ticker), []).append(mention)
    for group in grouped.values():
        group.sort(
            key=lambda mention: (
                mention.anchor_seconds is None,
                mention.anchor_seconds if mention.anchor_seconds is not None else mention.segment_index,
            )
        )
        cluster_anchor: float | int | None = None
        for mention in group:
            anchor = mention.anchor_seconds if mention.anchor_seconds is not None else mention.segment_index
            threshold = EVIDENCE_WINDOW_SECONDS if mention.anchor_seconds is not None else 3
            if cluster_anchor is None or abs(float(anchor) - float(cluster_anchor)) > threshold:
                deduped.append(mention)
                cluster_anchor = anchor
    return deduped


def _window_for_mention(
    mention: TranscriptMention,
    segments: list[TranscriptSegmentRow],
    transcript_source: str,
    provider_name: str,
    transcript_collected_at: str,
) -> TranscriptWindow:
    if mention.anchor_seconds is not None:
        window_segments = [
            segment
            for segment in segments
            if segment.start_seconds is not None
            and segment.start_seconds <= mention.anchor_seconds + EVIDENCE_WINDOW_SECONDS
            and (segment.end_seconds or segment.start_seconds)
            >= mention.anchor_seconds - EVIDENCE_WINDOW_SECONDS
        ]
    else:
        window_segments = [
            segment
            for segment in segments
            if abs(segment.segment_index - mention.segment_index) <= 1
        ]
    if not window_segments:
        window_segments = [
            segment for segment in segments if segment.segment_index == mention.segment_index
        ]
    evidence = _clean_text(" ".join(segment.text for segment in window_segments))
    starts = [segment.start_seconds for segment in window_segments if segment.start_seconds is not None]
    ends = [segment.end_seconds for segment in window_segments if segment.end_seconds is not None]
    return TranscriptWindow(
        video_id=mention.video_id,
        transcript_source=transcript_source,
        provider_name=provider_name,
        transcript_collected_at=transcript_collected_at,
        ticker=mention.ticker,
        company_name=CANONICAL_COMPANY_NAMES.get(mention.ticker, ""),
        mention_text=mention.mention_text,
        evidence_start_seconds=min(starts) if starts else None,
        evidence_end_seconds=max(ends) if ends else None,
        evidence_window=evidence,
        focused_action_text=_focused_action_text(evidence, mention.ticker),
    )


def _insert_event(
    conn: sqlite3.Connection,
    window: TranscriptWindow,
    result_label: str,
    stance: str,
    actionability_score: int,
    confidence_score: float,
    confidence_label: str,
    classifier_version: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO transcript_recommendation_events (
          video_id, transcript_source, provider_name, ticker, company_name, stance, detected_action,
          actionability_score, confidence_score, confidence_label,
          evidence_start_seconds, evidence_end_seconds, evidence_window,
          classifier_version, exclusion_reason, transcript_collected_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        (
            window.video_id,
            window.transcript_source,
            window.provider_name,
            window.ticker,
            window.company_name,
            stance,
            result_label,
            actionability_score,
            confidence_score,
            confidence_label,
            window.evidence_start_seconds,
            window.evidence_end_seconds,
            window.evidence_window,
            classifier_version,
            window.transcript_collected_at,
        ),
    )
    return int(cursor.lastrowid)


def _insert_candidate_window(
    conn: sqlite3.Connection,
    window: TranscriptWindow,
    result_label: str,
    stance: str,
    actionability_score: int,
    confidence_score: float,
    confidence_label: str,
    accepted: bool,
    transcript_event_id: int | None,
    classifier_version: str,
    exclusion_reason: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO transcript_candidate_windows (
          video_id, transcript_source, provider_name, ticker, company_name, mention_text,
          evidence_start_seconds, evidence_end_seconds, evidence_window, focused_action_text, stance,
          detected_action, actionability_score, confidence_score, confidence_label,
          accepted_event_flag, transcript_event_id, classifier_version, exclusion_reason,
          transcript_collected_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            window.video_id,
            window.transcript_source,
            window.provider_name,
            window.ticker,
            window.company_name,
            window.mention_text,
            window.evidence_start_seconds,
            window.evidence_end_seconds,
            window.evidence_window,
            window.focused_action_text,
            stance,
            result_label,
            actionability_score,
            confidence_score,
            confidence_label,
            int(accepted),
            transcript_event_id,
            classifier_version,
            exclusion_reason,
            window.transcript_collected_at,
        ),
    )


def _process_transcript_row(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    classifier_version: str,
) -> tuple[int, int, int]:
    segments = _load_segments(conn, row["video_id"])
    mentions = _dedupe_mentions(_segment_mentions(segments))
    candidate_count = 0
    event_count = 0
    transcript_collected_at = _clean_text(
        row["transcript_collected_at"]
        if "transcript_collected_at" in row.keys()
        else row["retrieved_at"]
        if "retrieved_at" in row.keys()
        else ""
    )
    for mention in mentions:
        window = _window_for_mention(
            mention,
            segments,
            row["transcript_source"],
            row["provider_name"],
            transcript_collected_at,
        )
        focused_result = classify_text(window.focused_action_text)
        negated_action = NEGATED_ACTION_RE.search(window.focused_action_text) is not None
        window_retrospective = any(
            kw in window.evidence_window.lower() for kw in STRONG_RETROSPECTIVE_KEYWORDS
        )
        accepted = (
            _contains_ticker(window.evidence_window, window.ticker)
            and _contains_ticker(window.focused_action_text, window.ticker)
            and focused_result.stance in {"bullish", "bearish"}
            and focused_result.actionability_score >= 2
            and focused_result.label
            not in {
                "news_only",
                "retrospective_claim",
                "third_party_attribution",
                "ambiguous_reference",
            }
            and not window_retrospective
            and not negated_action
        )
        if window_retrospective and not accepted:
            exclusion_reason = "retrospective_claim"
        else:
            exclusion_reason = _exclusion_reason(
                focused_result.label,
                accepted,
                window.focused_action_text,
                window.ticker,
                negated_action,
            )
        confidence_label = _confidence_label(
            focused_result.label,
            focused_result.actionability_score,
            window.focused_action_text,
            accepted,
        )
        transcript_event_id = None
        if accepted:
            transcript_event_id = _insert_event(
                conn,
                window,
                focused_result.recommendation_type,
                focused_result.stance,
                focused_result.actionability_score,
                focused_result.classifier_confidence,
                confidence_label,
                classifier_version,
            )
            event_count += 1
        _insert_candidate_window(
            conn,
            window,
            focused_result.recommendation_type,
            focused_result.stance,
            focused_result.actionability_score,
            focused_result.classifier_confidence,
            confidence_label,
            accepted,
            transcript_event_id,
            classifier_version,
            exclusion_reason,
        )
        candidate_count += 1
    return len(mentions), candidate_count, event_count


def build_transcript_recommendation_events(refresh_existing: bool = False) -> TranscriptBuildResult:
    init_db()
    settings = get_settings()
    classifier_version = settings.transcript_classifier_version
    candidate_count = 0
    event_count = 0
    with connect() as conn:
        if refresh_existing:
            conn.execute("DELETE FROM transcript_candidate_windows")
            conn.execute("DELETE FROM transcript_recommendation_events")
        video_rows = conn.execute(
            """
            SELECT video_id,
                   COALESCE(transcript_source, provider_name, 'unknown') AS transcript_source,
                   COALESCE(provider_name, '') AS provider_name,
                   COALESCE(collected_at, retrieved_at, '') AS transcript_collected_at,
                   retrieved_at
            FROM youtube_transcripts
            WHERE status = 'available'
            ORDER BY retrieved_at DESC, video_id
            """
        ).fetchall()
        for row in video_rows:
            _mentions, candidates, events = _process_transcript_row(
                conn,
                row,
                classifier_version=classifier_version,
            )
            candidate_count += candidates
            event_count += events
        conn.commit()
    return TranscriptBuildResult(candidate_windows=candidate_count, events=event_count)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_incremental_summary_md(
    path: Path,
    *,
    rows: list[dict[str, Any]],
    transcripts_available: int,
    transcripts_skipped: int,
    creator_count: int,
    year_count: int,
) -> Path:
    scanned = len(rows)
    ticker_mentions = sum(int(row["ticker_mentions_found"]) for row in rows)
    candidates = sum(int(row["candidate_windows_found"]) for row in rows)
    events = sum(int(row["events_found"]) for row in rows)
    excluded = candidates - events
    source_counts = Counter(str(row["transcript_source"] or "unknown") for row in rows)
    lines = [
        "# New Transcript Event Extraction Summary",
        "",
        f"- Available transcripts: {transcripts_available}",
        f"- Transcripts scanned: {scanned}",
        f"- Transcripts skipped because already processed: {transcripts_skipped}",
        f"- New ticker mentions found: {ticker_mentions}",
        f"- New candidate windows found: {candidates}",
        f"- New candidate recommendation events found: {events}",
        f"- New clean/review-needed/excluded counts: clean={events}, review_needed=0, excluded={excluded}",
        f"- Creators represented: {creator_count}",
        f"- Years represented: {year_count}",
        "",
        "## Scanned Transcripts by Source",
        "",
    ]
    if source_counts:
        lines.extend(
            f"- {source}: {count}" for source, count in sorted(source_counts.items())
        )
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "This command uses the deterministic transcript rules pipeline and records each "
            "processed transcript in `transcript_event_extraction_status` so reruns do not "
            "duplicate candidate windows or events.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def extract_events_from_new_transcripts(
    *,
    summary_csv_path: Path = DEFAULT_NEW_EXTRACTION_SUMMARY_CSV,
    summary_md_path: Path = DEFAULT_NEW_EXTRACTION_SUMMARY_MD,
) -> IncrementalTranscriptExtractionResult:
    init_db()
    settings = get_settings()
    classifier_version = settings.transcript_classifier_version
    processed_at = _utc_now_iso()
    summary_columns = [
        "video_id",
        "creator",
        "year",
        "transcript_source",
        "provider_name",
        "transcript_collected_at",
        "ticker_mentions_found",
        "candidate_windows_found",
        "events_found",
        "status",
    ]
    summary_rows: list[dict[str, Any]] = []
    with connect() as conn:
        available_rows = conn.execute(
            """
            SELECT
              yt.video_id,
              COALESCE(y.channel_title, y.channel_id, 'unknown') AS creator,
              COALESCE(y.published_at, '') AS published_at,
              COALESCE(yt.transcript_source, yt.provider_name, 'unknown') AS transcript_source,
              COALESCE(yt.provider_name, '') AS provider_name,
              COALESCE(yt.collected_at, yt.retrieved_at, '') AS transcript_collected_at,
              COALESCE(yt.full_text_sha256, '') AS transcript_hash,
              yt.retrieved_at
            FROM youtube_transcripts yt
            LEFT JOIN raw_youtube_videos y
              ON y.video_id = yt.video_id
            WHERE yt.status = 'available'
              AND COALESCE(yt.full_text, '') != ''
            ORDER BY yt.retrieved_at DESC, yt.video_id
            """
        ).fetchall()
        processed_ids = {
            row["video_id"]
            for row in conn.execute(
                "SELECT video_id FROM transcript_event_extraction_status"
            ).fetchall()
        }
        existing_pipeline_ids = {
            row["video_id"]
            for row in conn.execute(
                """
                SELECT DISTINCT video_id FROM transcript_candidate_windows
                UNION
                SELECT DISTINCT video_id FROM transcript_recommendation_events
                """
            ).fetchall()
        }
        skipped_ids = processed_ids | existing_pipeline_ids
        for row in available_rows:
            if row["video_id"] in skipped_ids:
                continue
            mentions, candidates, events = _process_transcript_row(
                conn,
                row,
                classifier_version=classifier_version,
            )
            conn.execute(
                """
                INSERT INTO transcript_event_extraction_status (
                  video_id, transcript_source, provider_name, transcript_collected_at,
                  transcript_hash, classifier_version, processed_at,
                  ticker_mentions_found, candidate_windows_found, events_found
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                  transcript_source = excluded.transcript_source,
                  provider_name = excluded.provider_name,
                  transcript_collected_at = excluded.transcript_collected_at,
                  transcript_hash = excluded.transcript_hash,
                  classifier_version = excluded.classifier_version,
                  processed_at = excluded.processed_at,
                  ticker_mentions_found = excluded.ticker_mentions_found,
                  candidate_windows_found = excluded.candidate_windows_found,
                  events_found = excluded.events_found
                """,
                (
                    row["video_id"],
                    row["transcript_source"],
                    row["provider_name"],
                    row["transcript_collected_at"],
                    row["transcript_hash"],
                    classifier_version,
                    processed_at,
                    mentions,
                    candidates,
                    events,
                ),
            )
            year = row["published_at"][:4] if len(row["published_at"] or "") >= 4 else "unknown"
            summary_rows.append(
                {
                    "video_id": row["video_id"],
                    "creator": row["creator"],
                    "year": year,
                    "transcript_source": row["transcript_source"],
                    "provider_name": row["provider_name"],
                    "transcript_collected_at": row["transcript_collected_at"],
                    "ticker_mentions_found": mentions,
                    "candidate_windows_found": candidates,
                    "events_found": events,
                    "status": "processed",
                }
            )
        conn.commit()

    creators = {_clean_text(row["creator"]) for row in summary_rows if _clean_text(row["creator"])}
    years = {_clean_text(row["year"]) for row in summary_rows if _clean_text(row["year"])}
    summary_csv_path = _write_csv(summary_csv_path, summary_rows, summary_columns)
    summary_md_path = _write_incremental_summary_md(
        summary_md_path,
        rows=summary_rows,
        transcripts_available=len(available_rows),
        transcripts_skipped=len(skipped_ids & {row["video_id"] for row in available_rows}),
        creator_count=len(creators),
        year_count=len(years),
    )
    candidate_windows = sum(int(row["candidate_windows_found"]) for row in summary_rows)
    events = sum(int(row["events_found"]) for row in summary_rows)
    return IncrementalTranscriptExtractionResult(
        summary_csv_path=summary_csv_path,
        summary_md_path=summary_md_path,
        transcripts_scanned=len(summary_rows),
        transcripts_skipped_already_processed=len(
            skipped_ids & {row["video_id"] for row in available_rows}
        ),
        new_ticker_mentions_found=sum(int(row["ticker_mentions_found"]) for row in summary_rows),
        new_candidate_windows_found=candidate_windows,
        new_events_found=events,
        new_excluded_windows=candidate_windows - events,
        creators_represented=len(creators),
        years_represented=len(years),
    )
