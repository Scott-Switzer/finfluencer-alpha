from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from .classify import classify_text
from .config import get_settings
from .db import connect, init_db
from .ticker_extract import COMPANY_ALIAS_TO_TICKER, extract_tickers

EVIDENCE_WINDOW_SECONDS = 30.0
LOCAL_ACTION_WORD_RADIUS = 12

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
        if label in {"news_only", "retrospective_claim", "portfolio_disclosure", "non_actionable_hype"}:
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
    if result_label == "news_only":
        return "news_only"
    if result_label == "retrospective_claim":
        return "retrospective"
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
          video_id, ticker, company_name, stance, detected_action,
          actionability_score, confidence_score, confidence_label,
          evidence_start_seconds, evidence_end_seconds, evidence_window,
          classifier_version, exclusion_reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            window.video_id,
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
          video_id, ticker, company_name, mention_text, evidence_start_seconds,
          evidence_end_seconds, evidence_window, focused_action_text, stance,
          detected_action, actionability_score, confidence_score, confidence_label,
          accepted_event_flag, transcript_event_id, classifier_version, exclusion_reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            window.video_id,
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
        ),
    )


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
            SELECT video_id
            FROM youtube_transcripts
            WHERE status = 'available'
            ORDER BY retrieved_at DESC, video_id
            """
        ).fetchall()
        for row in video_rows:
            segments = _load_segments(conn, row["video_id"])
            mentions = _dedupe_mentions(_segment_mentions(segments))
            for mention in mentions:
                window = _window_for_mention(mention, segments)
                focused_result = classify_text(window.focused_action_text)
                negated_action = NEGATED_ACTION_RE.search(window.focused_action_text) is not None
                accepted = (
                    _contains_ticker(window.evidence_window, window.ticker)
                    and _contains_ticker(window.focused_action_text, window.ticker)
                    and focused_result.stance in {"bullish", "bearish"}
                    and focused_result.actionability_score >= 2
                    and focused_result.label not in {"news_only", "retrospective_claim"}
                    and not negated_action
                )
                confidence_label = _confidence_label(
                    focused_result.label,
                    focused_result.actionability_score,
                    window.focused_action_text,
                    accepted,
                )
                exclusion_reason = _exclusion_reason(
                    focused_result.label,
                    accepted,
                    window.focused_action_text,
                    window.ticker,
                    negated_action,
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
        conn.commit()
    return TranscriptBuildResult(candidate_windows=candidate_count, events=event_count)
