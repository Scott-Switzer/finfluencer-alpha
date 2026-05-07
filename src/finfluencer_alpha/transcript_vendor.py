from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from .classify import classify_text
from .config import PROJECT_ROOT, ensure_data_dirs, get_settings
from .db import connect, init_db
from .ticker_extract import extract_tickers
from .youtube_transcripts import (
    BLOCKED_TRANSCRIPT_STATUSES,
    TranscriptFetchResult,
    TranscriptSegment,
    _pending_cooldown,
    _priority_score,
    store_transcript_result,
)

TRANSCRIPT_VENDOR_BATCH_COLUMNS = [
    "video_id",
    "url",
    "creator",
    "creator_category",
    "published_at",
    "title",
    "description",
    "priority_score",
    "ticker_signal_count",
    "recommendation_keyword_signal",
    "current_view_count",
    "current_like_count",
    "current_comment_count",
]

STRATIFIED_TRANSCRIPT_VENDOR_BATCH_COLUMNS = [
    "video_id",
    "url",
    "creator",
    "creator_category",
    "published_at",
    "year",
    "title",
    "description",
    "priority_score",
    "ticker_signal_count",
    "recommendation_keyword_signal",
    "current_view_count",
    "current_like_count",
    "current_comment_count",
    "sampling_stratum",
    "sampling_reason",
]

REQUIRED_TRANSCRIPT_IMPORT_COLUMNS = {
    "video_id",
    "transcript_text",
    "transcript_source",
    "provider_name",
    "retrieval_method",
    "is_asr_generated",
    "retrieved_at",
    "notes",
}
RECENT_TRANSCRIPT_BATCH_YEARS = {"2025", "2026"}


@dataclass(frozen=True)
class VendorBatchResult:
    output_path: Path
    row_count: int
    creator_counts: dict[str, int]


@dataclass(frozen=True)
class BatchAuditResult:
    input_path: Path
    row_count: int
    unique_video_count: int
    min_published_at: str
    max_published_at: str
    rows_by_year: dict[str, int]
    rows_by_creator: dict[str, int]
    rows_by_category: dict[str, int]
    rows_by_creator_year: dict[str, int]
    max_single_creator: int
    max_creator_year: int
    top5_creator_share: float
    year_shares: dict[str, float]
    category_shares: dict[str, float]
    year_2026_share: float
    year_2025_2026_share: float
    stock_picker_share: float
    excluded_rows: int
    already_transcribed_rows: int
    blocked_cooldown_rows: int
    missing_published_at_rows: int
    outside_date_rows: int
    pass_fail: dict[str, bool]
    warnings: list[str]

    @property
    def passed(self) -> bool:
        return all(self.pass_fail.values())


@dataclass(frozen=True)
class EligiblePoolAuditResult:
    total_eligible: int
    by_year: dict[str, int]
    by_category: dict[str, int]
    by_creator: dict[str, int]
    by_creator_year: dict[str, int]
    years_represented: int
    older_year_eligible_count: int


@dataclass(frozen=True)
class TranscriptImportResult:
    imported_count: int
    overwritten_count: int
    segment_count: int
    source: str


@dataclass(frozen=True)
class VendorCandidate:
    video_id: str
    url: str
    creator: str
    creator_category: str
    published_at: str
    title: str
    description: str
    priority_score: float
    ticker_signal_count: int
    recommendation_keyword_signal: int
    current_view_count: int | None
    current_like_count: int | None
    current_comment_count: int | None
    sampling_stratum: str = ""
    sampling_reason: str = ""

    @property
    def year(self) -> str:
        return _published_year(self.published_at)

    def as_row(self, include_sampling: bool = False) -> dict[str, object]:
        row: dict[str, object] = {
            "video_id": self.video_id,
            "url": self.url,
            "creator": self.creator,
            "creator_category": self.creator_category,
            "published_at": self.published_at,
            "title": self.title,
            "description": self.description,
            "priority_score": round(self.priority_score, 3),
            "ticker_signal_count": self.ticker_signal_count,
            "recommendation_keyword_signal": self.recommendation_keyword_signal,
            "current_view_count": self.current_view_count,
            "current_like_count": self.current_like_count,
            "current_comment_count": self.current_comment_count,
        }
        if include_sampling:
            row["year"] = self.year
            row["sampling_stratum"] = self.sampling_stratum
            row["sampling_reason"] = self.sampling_reason
        return row


def _resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _clean(value: object) -> str:
    return str(value or "").strip()


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    normalized = _clean(value).lower()
    confidence_labels = {"high": 0.95, "medium": 0.80, "low": 0.60}
    if normalized in confidence_labels:
        return confidence_labels[normalized]
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_from_csv(value: object) -> bool:
    normalized = _clean(value).lower()
    if normalized in {"1", "true", "t", "yes", "y", "asr", "generated"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "manual", "human"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _validate_retrieved_at(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("retrieved_at is required")
    datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    return cleaned


def _published_timestamp(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _published_date(value: str) -> str:
    return value[:10] if len(value) >= 10 else ""


def _date_in_range(value: str, start_date: str | None, end_date: str | None) -> bool:
    date_value = _published_date(value)
    if not date_value:
        return False
    if start_date and date_value < start_date:
        return False
    if end_date and date_value > end_date:
        return False
    return True


def _recommendation_signal(text: str) -> int:
    result = classify_text(text)
    return int(
        result.stance in {"bullish", "bearish"}
        and result.actionability_score >= 2
        and result.label not in {"retrospective_claim", "news_only"}
    )


def _engagement_score(view_count: int | None, like_count: int | None, comment_count: int | None) -> float:
    views = math.log1p(max(view_count or 0, 0)) / 6
    likes = math.log1p(max(like_count or 0, 0)) / 5
    comments = math.log1p(max(comment_count or 0, 0)) / 4
    return min(4.0, views + likes + comments)


def _candidate_from_row(row: Any) -> VendorCandidate:
    text = f"{row['title'] or ''} {row['description'] or ''}"
    base_score, _reason = _priority_score(row["title"], row["description"], row["channel_title"])
    ticker_count = len({mention.ticker for mention in extract_tickers(text)})
    rec_signal = _recommendation_signal(text)
    view_count = _int_or_none(row["current_view_count"])
    like_count = _int_or_none(row["current_like_count"])
    comment_count = _int_or_none(row["current_comment_count"])
    priority_score = (
        base_score
        + min(ticker_count, 5) * 2.0
        + rec_signal * 5.0
        + _engagement_score(view_count, like_count, comment_count)
    )
    return VendorCandidate(
        video_id=row["video_id"],
        url=row["url"] or f"https://www.youtube.com/watch?v={row['video_id']}",
        creator=row["channel_title"] or row["channel_id"] or "unknown",
        creator_category=row["creator_category"] or "unknown",
        published_at=row["published_at"] or "",
        title=row["title"] or "",
        description=row["description"] or "",
        priority_score=priority_score,
        ticker_signal_count=ticker_count,
        recommendation_keyword_signal=rec_signal,
        current_view_count=view_count,
        current_like_count=like_count,
        current_comment_count=comment_count,
    )


def _eligible_vendor_candidates(
    include_blocked: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[VendorCandidate]:
    init_db()
    cooldown_hours = get_settings().transcript_queue_cooldown_hours
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              y.video_id,
              y.url,
              y.channel_id,
              y.channel_title,
              y.creator_category,
              y.published_at,
              y.title,
              y.description,
              y.current_view_count,
              y.current_like_count,
              y.current_comment_count,
              yt.status AS transcript_status,
              yt.full_text,
              tfq.transcript_status AS queue_status,
              tfq.next_eligible_attempt_at
            FROM raw_youtube_videos y
            LEFT JOIN youtube_transcripts yt
              ON yt.video_id = y.video_id
            LEFT JOIN transcript_fetch_queue tfq
              ON tfq.video_id = y.video_id
            WHERE COALESCE(y.excluded_flag, 0) = 0
            ORDER BY y.published_at DESC, y.video_id
            """
        ).fetchall()

    candidates: list[VendorCandidate] = []
    for row in rows:
        if not _clean(row["video_id"]):
            continue
        if not _clean(row["channel_title"]) and not _clean(row["channel_id"]):
            continue
        if start_date or end_date:
            if not _date_in_range(row["published_at"] or "", start_date, end_date):
                continue
        if row["transcript_status"] == "available" and _clean(row["full_text"]):
            continue
        if row["queue_status"] in {"available", "excluded"}:
            continue
        if not include_blocked:
            if row["queue_status"] in BLOCKED_TRANSCRIPT_STATUSES:
                continue
            if row["transcript_status"] in BLOCKED_TRANSCRIPT_STATUSES:
                continue
            if _pending_cooldown(row, cooldown_hours):
                continue
        candidates.append(_candidate_from_row(row))

    candidates.sort(
        key=lambda item: (
            -item.priority_score,
            -_published_timestamp(item.published_at),
            item.video_id,
        )
    )
    return candidates


def select_transcript_vendor_batch(
    limit: int,
    include_blocked: bool = False,
) -> list[VendorCandidate]:
    candidates = _eligible_vendor_candidates(include_blocked=include_blocked)
    grouped: dict[str, deque[VendorCandidate]] = defaultdict(deque)
    for candidate in candidates:
        grouped[candidate.creator].append(candidate)

    creator_order = sorted(
        grouped,
        key=lambda creator: (
            -grouped[creator][0].priority_score,
            -len(grouped[creator]),
            creator.lower(),
        ),
    )

    selected: list[VendorCandidate] = []
    while len(selected) < limit and creator_order:
        next_order: list[str] = []
        for creator in creator_order:
            if len(selected) >= limit:
                break
            queue = grouped[creator]
            if not queue:
                continue
            selected.append(queue.popleft())
            if queue:
                next_order.append(creator)
        creator_order = next_order
    return selected


def _parse_category_shares(values: list[str]) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for value in values:
        if ":" not in value:
            raise ValueError(f"Invalid category share cap: {value}")
        category, share = value.split(":", 1)
        parsed[category.strip()] = float(share)
    return parsed


def _category_allowed(
    candidate: VendorCandidate,
    category_counts: Counter[str],
    limit: int,
    category_share_caps: dict[str, float],
) -> bool:
    cap = category_share_caps.get(candidate.creator_category)
    if cap is None or limit <= 0:
        return True
    return category_counts[candidate.creator_category] + 1 <= math.floor(limit * cap)


def _candidate_sort_key(candidate: VendorCandidate) -> tuple[float, float, str, str]:
    return (
        -candidate.priority_score,
        -_published_timestamp(candidate.published_at),
        candidate.creator.lower(),
        candidate.video_id,
    )


def _creator_capacity(
    candidates: list[VendorCandidate],
    *,
    max_per_creator: int,
    max_per_creator_year: int,
    years: set[str] | None = None,
) -> dict[str, int]:
    creator_year_counts = Counter(
        (candidate.creator, candidate.year)
        for candidate in candidates
        if years is None or candidate.year in years
    )
    creators = {creator for creator, _year in creator_year_counts}
    capacities: dict[str, int] = {}
    for creator in creators:
        capacity = sum(
            min(max_per_creator_year, count)
            for (candidate_creator, _year), count in creator_year_counts.items()
            if candidate_creator == creator
        )
        capacities[creator] = min(max_per_creator, capacity)
    return capacities


def _effective_creator_cap_for_top5_share(
    capacities: dict[str, int],
    *,
    max_per_creator: int,
    max_top5_creator_share: float,
) -> int:
    if not capacities or max_top5_creator_share >= 1:
        return max_per_creator
    for cap in range(max_per_creator, 0, -1):
        capped_counts = sorted((min(capacity, cap) for capacity in capacities.values()), reverse=True)
        total_capacity = sum(capped_counts)
        if not total_capacity:
            return cap
        top5_share = sum(capped_counts[:5]) / total_capacity
        if top5_share <= max_top5_creator_share:
            return cap
    return 1


def _select_stratified_transcript_vendor_batch(
    *,
    limit: int,
    start_date: str,
    end_date: str,
    include_blocked: bool = False,
    max_per_creator: int = 40,
    max_per_creator_year: int = 10,
    max_year_share: float = 0.35,
    max_top5_creator_share: float = 0.25,
    max_recent_year_share: float = 0.55,
    category_share_caps: dict[str, float] | None = None,
    min_years: int = 5,
    priority_weight: float = 0.60,
    balance_weight: float = 0.40,
) -> list[VendorCandidate]:
    candidates = _eligible_vendor_candidates(
        include_blocked=include_blocked,
        start_date=start_date,
        end_date=end_date,
    )
    category_share_caps = category_share_caps or {}
    creator_capacities = _creator_capacity(
        candidates,
        max_per_creator=max_per_creator,
        max_per_creator_year=max_per_creator_year,
    )
    effective_max_per_creator = _effective_creator_cap_for_top5_share(
        creator_capacities,
        max_per_creator=max_per_creator,
        max_top5_creator_share=max_top5_creator_share,
    )
    effective_capacities = {
        creator: min(capacity, effective_max_per_creator)
        for creator, capacity in creator_capacities.items()
    }
    effective_limit = min(limit, sum(effective_capacities.values()))
    older_years = {
        candidate.year for candidate in candidates if candidate.year not in RECENT_TRANSCRIPT_BATCH_YEARS
    }
    older_capacity = sum(
        _creator_capacity(
            candidates,
            max_per_creator=effective_max_per_creator,
            max_per_creator_year=max_per_creator_year,
            years=older_years,
        ).values()
    )
    if older_capacity and max_recent_year_share < 1:
        recent_capped_limit = math.floor(older_capacity / (1 - max_recent_year_share))
        effective_limit = min(effective_limit, recent_capped_limit)
        recent_year_limit = math.floor(effective_limit * max_recent_year_share)
    else:
        recent_year_limit = effective_limit

    by_year_creator: dict[tuple[str, str], deque[VendorCandidate]] = defaultdict(deque)
    years = sorted({candidate.year for candidate in candidates if candidate.year != "unknown"})
    for candidate in sorted(candidates, key=_candidate_sort_key):
        by_year_creator[(candidate.year, candidate.creator)].append(candidate)

    year_counts: Counter[str] = Counter()
    creator_counts: Counter[str] = Counter()
    creator_year_counts: Counter[tuple[str, str]] = Counter()
    category_counts: Counter[str] = Counter()
    selected: list[VendorCandidate] = []
    selected_ids: set[str] = set()
    max_year_count = max(1, math.floor(effective_limit * max_year_share))
    target_year_count = max(1, math.ceil(effective_limit / max(len(years), 1)))

    def can_select(candidate: VendorCandidate) -> bool:
        if candidate.video_id in selected_ids:
            return False
        if creator_counts[candidate.creator] >= effective_max_per_creator:
            return False
        if creator_year_counts[(candidate.creator, candidate.year)] >= max_per_creator_year:
            return False
        if year_counts[candidate.year] >= max_year_count:
            return False
        if (
            candidate.year in RECENT_TRANSCRIPT_BATCH_YEARS
            and sum(year_counts[year] for year in RECENT_TRANSCRIPT_BATCH_YEARS) >= recent_year_limit
        ):
            return False
        if not _category_allowed(candidate, category_counts, effective_limit, category_share_caps):
            return False
        return True

    def add_candidate(candidate: VendorCandidate, reason: str) -> None:
        selected_ids.add(candidate.video_id)
        year_counts[candidate.year] += 1
        creator_counts[candidate.creator] += 1
        creator_year_counts[(candidate.creator, candidate.year)] += 1
        category_counts[candidate.creator_category] += 1
        selected.append(
            replace(
                candidate,
                sampling_stratum=f"year={candidate.year};creator={candidate.creator}",
                sampling_reason=reason,
            )
        )

    def next_from_bucket(year: str, creator: str, reason: str) -> bool:
        bucket = by_year_creator[(year, creator)]
        while bucket:
            candidate = bucket.popleft()
            if can_select(candidate):
                add_candidate(candidate, reason)
                return True
        return False

    creators_by_year: dict[str, list[str]] = {}
    for year in years:
        creators_by_year[year] = sorted(
            {candidate.creator for candidate in candidates if candidate.year == year},
            key=lambda creator: (
                -len(by_year_creator[(year, creator)]),
                creator.lower(),
            ),
        )

    while len(selected) < effective_limit and years:
        made_progress = False
        years_by_need = sorted(
            years,
            key=lambda year: (
                year_counts[year] >= target_year_count,
                year_counts[year],
                year,
            ),
        )
        for year in years_by_need:
            if len(selected) >= effective_limit:
                break
            if year_counts[year] >= target_year_count and len([y for y in years if year_counts[y] < target_year_count]) > 0:
                continue
            for creator in creators_by_year[year]:
                if len(selected) >= effective_limit:
                    break
                if next_from_bucket(
                    year,
                    creator,
                    (
                        f"stratified_round_robin;priority_weight={priority_weight:.2f};"
                        f"balance_weight={balance_weight:.2f}"
                    ),
                ):
                    made_progress = True
                    break
        if not made_progress:
            break

    if len(selected) < effective_limit:
        remaining = [
            candidate
            for candidate in sorted(candidates, key=_candidate_sort_key)
            if candidate.video_id not in selected_ids
        ]
        for candidate in remaining:
            if len(selected) >= effective_limit:
                break
            if can_select(candidate):
                add_candidate(candidate, "reallocated_unused_year_quota")

    represented_years = {candidate.year for candidate in selected}
    if len(selected) >= effective_limit and len(represented_years) < min_years:
        raise ValueError("Stratified export could not satisfy minimum represented years.")

    return selected[:effective_limit]


def export_transcript_vendor_batch(
    limit: int,
    output_path: Path,
    include_blocked: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    stratify_by: str | None = None,
    max_per_creator: int = 40,
    max_per_creator_year: int = 10,
    max_year_share: float = 0.35,
    max_top5_creator_share: float = 0.25,
    max_recent_year_share: float = 0.55,
    max_category_share: list[str] | None = None,
    min_years: int = 5,
    diversify_creators: bool = False,
    priority_weight: float = 0.60,
    balance_weight: float = 0.40,
) -> VendorBatchResult:
    ensure_data_dirs()
    output_path = _resolve_project_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stratified = bool(stratify_by)
    if stratified:
        if not start_date or not end_date:
            raise ValueError("Stratified export requires --start-date and --end-date.")
        selected = _select_stratified_transcript_vendor_batch(
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            include_blocked=include_blocked,
            max_per_creator=max_per_creator,
            max_per_creator_year=max_per_creator_year,
            max_year_share=max_year_share,
            max_top5_creator_share=max_top5_creator_share,
            max_recent_year_share=max_recent_year_share,
            category_share_caps=_parse_category_shares(max_category_share or []),
            min_years=min_years,
            priority_weight=priority_weight,
            balance_weight=balance_weight,
        )
    else:
        selected = select_transcript_vendor_batch(limit=limit, include_blocked=include_blocked)
    columns = (
        STRATIFIED_TRANSCRIPT_VENDOR_BATCH_COLUMNS if stratified else TRANSCRIPT_VENDOR_BATCH_COLUMNS
    )
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for candidate in selected:
            writer.writerow(candidate.as_row(include_sampling=stratified))
    creator_counts: dict[str, int] = {}
    for candidate in selected:
        creator_counts[candidate.creator] = creator_counts.get(candidate.creator, 0) + 1
    return VendorBatchResult(output_path, len(selected), creator_counts)


def audit_eligible_transcript_vendor_pool(
    start_date: str,
    end_date: str,
) -> EligiblePoolAuditResult:
    candidates = _eligible_vendor_candidates(
        include_blocked=False,
        start_date=start_date,
        end_date=end_date,
    )
    by_year = Counter(candidate.year for candidate in candidates)
    by_category = Counter(candidate.creator_category for candidate in candidates)
    by_creator = Counter(candidate.creator for candidate in candidates)
    by_creator_year = Counter(f"{candidate.creator} | {candidate.year}" for candidate in candidates)
    older_years = [year for year in by_year if year < "2025"]
    return EligiblePoolAuditResult(
        total_eligible=len(candidates),
        by_year=dict(sorted(by_year.items())),
        by_category=dict(by_category.most_common()),
        by_creator=dict(by_creator.most_common()),
        by_creator_year=dict(by_creator_year.most_common()),
        years_represented=sum(1 for count in by_year.values() if count > 0),
        older_year_eligible_count=sum(by_year[year] for year in older_years),
    )


def _batch_rows(input_path: Path) -> list[dict[str, str]]:
    input_path = _resolve_project_path(input_path)
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _batch_db_flags(video_ids: list[str]) -> tuple[int, int, int]:
    if not video_ids:
        return 0, 0, 0
    with connect() as conn:
        placeholders = ",".join("?" for _ in video_ids)
        excluded = conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM raw_youtube_videos
            WHERE video_id IN ({placeholders})
              AND COALESCE(excluded_flag, 0) = 1
            """,
            video_ids,
        ).fetchone()["n"]
        covered = conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM youtube_transcripts
            WHERE video_id IN ({placeholders})
              AND status = 'available'
              AND COALESCE(full_text, '') != ''
            """,
            video_ids,
        ).fetchone()["n"]
        blocked = conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM transcript_fetch_queue
            WHERE video_id IN ({placeholders})
              AND (
                transcript_status IN ('ip_blocked', 'request_blocked')
                OR (
                  next_eligible_attempt_at IS NOT NULL
                  AND next_eligible_attempt_at > datetime('now')
                )
              )
            """,
            video_ids,
        ).fetchone()["n"]
    return int(excluded), int(covered), int(blocked)


def audit_transcript_vendor_batch(
    input_path: Path,
    *,
    start_date: str,
    end_date: str,
    min_years: int = 5,
    max_year_share: float = 0.35,
    max_recent_year_share: float = 0.55,
    max_per_creator: int = 45,
    max_per_creator_year: int = 12,
    max_top5_creator_share: float = 0.25,
    max_stock_picker_share: float = 0.75,
) -> BatchAuditResult:
    init_db()
    input_path = _resolve_project_path(input_path)
    rows = _batch_rows(input_path)
    video_ids = [_clean(row.get("video_id")) for row in rows if _clean(row.get("video_id"))]
    published_values = [_clean(row.get("published_at")) for row in rows if _clean(row.get("published_at"))]
    missing_dates = sum(1 for row in rows if not _clean(row.get("published_at")))
    outside_dates = sum(
        1
        for row in rows
        if _clean(row.get("published_at"))
        and not _date_in_range(_clean(row.get("published_at")), start_date, end_date)
    )
    year_counts = Counter(_published_year(row.get("published_at") or "") for row in rows)
    creator_counts = Counter(_clean(row.get("creator")) or "unknown" for row in rows)
    category_counts = Counter(_clean(row.get("creator_category")) or "unknown" for row in rows)
    creator_year_counts = Counter(
        f"{_clean(row.get('creator')) or 'unknown'} | {_published_year(row.get('published_at') or '')}"
        for row in rows
    )
    excluded, covered, blocked = _batch_db_flags(video_ids)
    row_count = len(rows)
    top5_share = (
        sum(count for _, count in creator_counts.most_common(5)) / row_count if row_count else 0.0
    )
    year_shares = {
        year: count / row_count if row_count else 0.0 for year, count in year_counts.items()
    }
    category_shares = {
        category: count / row_count if row_count else 0.0
        for category, count in category_counts.items()
    }
    represented_years = {
        year for year, count in year_counts.items() if count > 0 and year != "unknown"
    }
    eligible_pool = audit_eligible_transcript_vendor_pool(start_date, end_date)
    older_needed_for_recent_cap = math.ceil(row_count * (1 - max_recent_year_share))
    older_unavailable = eligible_pool.older_year_eligible_count < older_needed_for_recent_cap
    warnings: list[str] = []
    if older_unavailable:
        warnings.append(
            "Older eligible videos are insufficient to enforce the 2025-2026 share cap."
        )
    if eligible_pool.years_represented < min_years:
        warnings.append("Eligible pool has fewer years than the requested minimum.")

    pass_fail = {
        "date_range": outside_dates == 0,
        "min_years": len(represented_years) >= min_years
        or eligible_pool.years_represented < min_years,
        "max_year_share": all(share <= max_year_share for share in year_shares.values()),
        "max_2025_2026_share": (
            year_shares.get("2025", 0.0) + year_shares.get("2026", 0.0)
            <= max_recent_year_share
        )
        or older_unavailable,
        "max_per_creator": (max(creator_counts.values()) if creator_counts else 0)
        <= max_per_creator,
        "max_per_creator_year": (
            max(creator_year_counts.values()) if creator_year_counts else 0
        )
        <= max_per_creator_year,
        "max_top5_creator_share": top5_share <= max_top5_creator_share,
        "max_stock_picker_share": category_shares.get("stock_picker", 0.0)
        <= max_stock_picker_share,
        "no_excluded_rows": excluded == 0,
        "no_already_transcribed_rows": covered == 0,
        "no_blocked_cooldown_rows": blocked == 0,
        "no_missing_published_at": missing_dates == 0,
    }
    return BatchAuditResult(
        input_path=input_path,
        row_count=row_count,
        unique_video_count=len(set(video_ids)),
        min_published_at=min(published_values) if published_values else "",
        max_published_at=max(published_values) if published_values else "",
        rows_by_year=dict(sorted(year_counts.items())),
        rows_by_creator=dict(creator_counts.most_common()),
        rows_by_category=dict(category_counts.most_common()),
        rows_by_creator_year=dict(creator_year_counts.most_common()),
        max_single_creator=max(creator_counts.values()) if creator_counts else 0,
        max_creator_year=max(creator_year_counts.values()) if creator_year_counts else 0,
        top5_creator_share=top5_share,
        year_shares=year_shares,
        category_shares=category_shares,
        year_2026_share=year_shares.get("2026", 0.0),
        year_2025_2026_share=year_shares.get("2025", 0.0) + year_shares.get("2026", 0.0),
        stock_picker_share=category_shares.get("stock_picker", 0.0),
        excluded_rows=excluded,
        already_transcribed_rows=covered,
        blocked_cooldown_rows=blocked,
        missing_published_at_rows=missing_dates,
        outside_date_rows=outside_dates,
        pass_fail=pass_fail,
        warnings=warnings,
    )


def audit_output_paths(input_path: Path) -> tuple[Path, Path]:
    input_path = _resolve_project_path(input_path)
    return (
        input_path.with_name(f"{input_path.stem}_audit.csv"),
        input_path.with_name(f"{input_path.stem}_audit.txt"),
    )


def _audit_rows_for_csv(audit: BatchAuditResult) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {"section": "summary", "label": "rows", "value": audit.row_count},
        {"section": "summary", "label": "unique_video_ids", "value": audit.unique_video_count},
        {"section": "summary", "label": "min_published_at", "value": audit.min_published_at},
        {"section": "summary", "label": "max_published_at", "value": audit.max_published_at},
        {"section": "summary", "label": "max_single_creator", "value": audit.max_single_creator},
        {"section": "summary", "label": "max_creator_year", "value": audit.max_creator_year},
        {"section": "summary", "label": "top5_creator_share", "value": audit.top5_creator_share},
        {"section": "summary", "label": "2026_share", "value": audit.year_2026_share},
        {
            "section": "summary",
            "label": "2025_2026_share",
            "value": audit.year_2025_2026_share,
        },
        {"section": "summary", "label": "stock_picker_share", "value": audit.stock_picker_share},
        {"section": "summary", "label": "excluded_rows", "value": audit.excluded_rows},
        {
            "section": "summary",
            "label": "already_transcribed_rows",
            "value": audit.already_transcribed_rows,
        },
        {
            "section": "summary",
            "label": "blocked_cooldown_rows",
            "value": audit.blocked_cooldown_rows,
        },
        {
            "section": "summary",
            "label": "missing_published_at_rows",
            "value": audit.missing_published_at_rows,
        },
        {"section": "summary", "label": "outside_date_rows", "value": audit.outside_date_rows},
        {"section": "summary", "label": "passed", "value": int(audit.passed)},
    ]
    for year, count in audit.rows_by_year.items():
        rows.append({"section": "rows_by_year", "label": year, "value": count})
    for creator, count in audit.rows_by_creator.items():
        rows.append({"section": "rows_by_creator", "label": creator, "value": count})
    for category, count in audit.rows_by_category.items():
        rows.append({"section": "rows_by_category", "label": category, "value": count})
    for creator_year, count in audit.rows_by_creator_year.items():
        rows.append(
            {"section": "rows_by_creator_year", "label": creator_year, "value": count}
        )
    for criterion, passed in audit.pass_fail.items():
        rows.append({"section": "pass_fail", "label": criterion, "value": int(passed)})
    for warning in audit.warnings:
        rows.append({"section": "warning", "label": warning, "value": ""})
    return rows


def _audit_text(audit: BatchAuditResult) -> str:
    lines = [
        f"Input: {audit.input_path}",
        f"Rows: {audit.row_count}",
        f"Unique video IDs: {audit.unique_video_count}",
        f"Published range: {audit.min_published_at} to {audit.max_published_at}",
        f"Max single creator: {audit.max_single_creator}",
        f"Max creator-year cell: {audit.max_creator_year}",
        f"Top 5 creator share: {audit.top5_creator_share:.1%}",
        f"2026 share: {audit.year_2026_share:.1%}",
        f"2025-2026 share: {audit.year_2025_2026_share:.1%}",
        f"Stock-picker share: {audit.stock_picker_share:.1%}",
        f"Excluded rows: {audit.excluded_rows}",
        f"Already-transcribed rows: {audit.already_transcribed_rows}",
        f"Blocked/cooldown rows: {audit.blocked_cooldown_rows}",
        f"Missing published_at rows: {audit.missing_published_at_rows}",
        f"Outside date rows: {audit.outside_date_rows}",
        f"PASS: {audit.passed}",
        "",
        "Rows by year:",
    ]
    lines.extend(f"  {year}: {count}" for year, count in audit.rows_by_year.items())
    lines.append("")
    lines.append("Rows by category:")
    lines.extend(f"  {category}: {count}" for category, count in audit.rows_by_category.items())
    lines.append("")
    lines.append("Top creators:")
    lines.extend(
        f"  {creator}: {count}" for creator, count in list(audit.rows_by_creator.items())[:20]
    )
    lines.append("")
    lines.append("Top creator-year cells:")
    lines.extend(
        f"  {creator_year}: {count}"
        for creator_year, count in list(audit.rows_by_creator_year.items())[:20]
    )
    lines.append("")
    lines.append("Criteria:")
    lines.extend(
        f"  {criterion}: {'PASS' if passed else 'FAIL'}"
        for criterion, passed in audit.pass_fail.items()
    )
    if audit.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  {warning}" for warning in audit.warnings)
    return "\n".join(lines) + "\n"


def write_transcript_vendor_batch_audit(audit: BatchAuditResult) -> tuple[Path, Path]:
    csv_path, text_path = audit_output_paths(audit.input_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["section", "label", "value"])
        writer.writeheader()
        writer.writerows(_audit_rows_for_csv(audit))
    text_path.write_text(_audit_text(audit), encoding="utf-8")
    return csv_path, text_path


def _load_import_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Transcript CSV is missing a header row")
        missing = REQUIRED_TRANSCRIPT_IMPORT_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError("Transcript CSV is missing required columns: " + ", ".join(sorted(missing)))
        return [dict(row) for row in reader]


def _segments_from_json(video_id: str, raw_json: str) -> list[TranscriptSegment]:
    data = json.loads(raw_json)
    if not isinstance(data, list):
        raise ValueError("segments_json must be a JSON list")
    segments: list[TranscriptSegment] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError("segments_json entries must be objects")
        text = _clean(item.get("text") or item.get("segment_text"))
        if not text:
            continue
        start = _float_or_none(item.get("start_seconds", item.get("start")))
        duration = _float_or_none(item.get("duration_seconds", item.get("duration")))
        end = _float_or_none(item.get("end_seconds", item.get("end")))
        if duration is None and start is not None and end is not None:
            duration = max(0.0, end - start)
        segments.append(TranscriptSegment(video_id, index, start, duration, text))
    return segments


def _segments_from_import_rows(
    video_id: str,
    rows: list[dict[str, str]],
    full_text: str,
) -> list[TranscriptSegment]:
    first = rows[0]
    segment_json = _clean(first.get("segment_json")) or _clean(first.get("segments_json"))
    if segment_json:
        segments = _segments_from_json(video_id, segment_json)
        if segments:
            return segments

    has_segment_columns = any(
        _clean(row.get(column))
        for row in rows
        for column in ("segment_text", "start_seconds", "duration_seconds", "end_seconds")
    )
    if has_segment_columns:
        segments: list[TranscriptSegment] = []
        for index, row in enumerate(rows):
            text = _clean(row.get("segment_text")) or (_clean(row.get("transcript_text")) if len(rows) == 1 else "")
            if not text:
                continue
            start = _float_or_none(row.get("start_seconds"))
            duration = _float_or_none(row.get("duration_seconds"))
            end = _float_or_none(row.get("end_seconds"))
            if duration is None and start is not None and end is not None:
                duration = max(0.0, end - start)
            segments.append(TranscriptSegment(video_id, index, start, duration, text))
        if segments:
            return segments

    return [TranscriptSegment(video_id, 0, 0.0, None, full_text)]


def import_transcripts_csv(
    path: Path,
    source: str,
    overwrite: bool = False,
) -> TranscriptImportResult:
    init_db()
    path = _resolve_project_path(path)
    rows = _load_import_rows(path)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[_clean(row.get("video_id"))].append(row)

    errors: list[str] = []
    imported: list[tuple[TranscriptFetchResult, bool]] = []
    with connect() as conn:
        for video_id, group in grouped.items():
            first = group[0]
            if not video_id:
                errors.append("missing video_id")
                continue
            video_exists = conn.execute(
                "SELECT 1 FROM raw_youtube_videos WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            if not video_exists:
                errors.append(f"{video_id}: unknown video_id")
                continue

            full_text = _clean(first.get("transcript_text"))
            if not full_text:
                errors.append(f"{video_id}: empty transcript_text")
                continue

            existing = conn.execute(
                """
                SELECT status, full_text
                FROM youtube_transcripts
                WHERE video_id = ?
                """,
                (video_id,),
            ).fetchone()
            existing_available = bool(
                existing and existing["status"] == "available" and _clean(existing["full_text"])
            )
            if existing_available and not overwrite:
                errors.append(f"{video_id}: transcript already exists; pass --overwrite to replace it")
                continue

            transcript_source = _clean(first.get("transcript_source"))
            provider_name = _clean(first.get("provider_name"))
            retrieval_method = _clean(first.get("retrieval_method"))
            if not transcript_source:
                errors.append(f"{video_id}: transcript_source is required")
                continue
            if not provider_name:
                errors.append(f"{video_id}: provider_name is required")
                continue
            if not retrieval_method:
                errors.append(f"{video_id}: retrieval_method is required")
                continue
            try:
                is_asr_generated = _bool_from_csv(first.get("is_asr_generated"))
                retrieved_at = _validate_retrieved_at(_clean(first.get("retrieved_at")))
                segments = _segments_from_import_rows(video_id, group, full_text)
            except (ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{video_id}: {exc}")
                continue
            if not segments:
                errors.append(f"{video_id}: no transcript segments could be created")
                continue

            normalized_segments = [
                {
                    "text": segment.text,
                    "start": segment.start_seconds,
                    "duration": segment.duration_seconds,
                }
                for segment in segments
            ]
            text_for_hash = " ".join(segment.text for segment in segments if segment.text).strip()
            if not text_for_hash:
                text_for_hash = full_text
            source_confidence = _float_or_none(first.get("source_confidence"))
            if source_confidence is None:
                source_confidence = 0.80 if is_asr_generated else 0.90
            result = TranscriptFetchResult(
                video_id=video_id,
                provider_name=provider_name,
                provider_version=_clean(first.get("provider_version")),
                status="available",
                transcript_source=transcript_source,
                retrieval_method=retrieval_method,
                retrieval_status="available",
                retrieved_at=retrieved_at,
                provider_notes=_clean(first.get("notes")),
                is_generated=is_asr_generated,
                is_asr_generated=is_asr_generated,
                is_translatable=None,
                full_text=full_text,
                full_text_sha256=hashlib.sha256(text_for_hash.encode("utf-8")).hexdigest(),
                raw_json=json.dumps(normalized_segments, ensure_ascii=False),
                segments=segments,
                source_confidence=source_confidence,
            )
            imported.append((result, existing_available))

        if errors:
            raise ValueError("Transcript CSV validation failed: " + "; ".join(errors[:10]))

        overwritten = 0
        segment_count = 0
        for result, existing_available in imported:
            store_transcript_result(conn, result)
            conn.execute(
                """
                UPDATE transcript_fetch_queue
                SET transcript_status = 'available',
                    last_attempted_at = ?,
                    next_eligible_attempt_at = ?
                WHERE video_id = ?
                """,
                (result.retrieved_at, result.retrieved_at, result.video_id),
            )
            overwritten += int(existing_available)
            segment_count += len(result.segments)
        conn.commit()

    return TranscriptImportResult(
        imported_count=len(imported),
        overwritten_count=overwritten,
        segment_count=segment_count,
        source=source,
    )


def _covered(value: dict[str, object]) -> bool:
    return bool(value["covered"])


def _metric_bucket(value: int | None) -> str:
    if value is None:
        return "unknown"
    if value < 1_000:
        return "0-999"
    if value < 10_000:
        return "1k-9.9k"
    if value < 100_000:
        return "10k-99k"
    if value < 1_000_000:
        return "100k-999k"
    return "1M+"


def _published_year(value: str) -> str:
    return value[:4] if len(value) >= 4 and value[:4].isdigit() else "unknown"


def _coverage_records() -> list[dict[str, object]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              y.video_id,
              y.channel_title,
              y.creator_category,
              y.published_at,
              y.title,
              y.description,
              y.current_view_count,
              y.current_like_count,
              y.current_comment_count,
              yt.status,
              yt.full_text
            FROM raw_youtube_videos y
            LEFT JOIN youtube_transcripts yt
              ON yt.video_id = y.video_id
            WHERE COALESCE(y.excluded_flag, 0) = 0
            """
        ).fetchall()
    records: list[dict[str, object]] = []
    for row in rows:
        text = f"{row['title'] or ''} {row['description'] or ''}"
        records.append(
            {
                "video_id": row["video_id"],
                "creator": row["channel_title"] or "unknown",
                "creator_category": row["creator_category"] or "unknown",
                "year": _published_year(row["published_at"] or ""),
                "view_count_bucket": _metric_bucket(_int_or_none(row["current_view_count"])),
                "like_count_bucket": _metric_bucket(_int_or_none(row["current_like_count"])),
                "comment_count_bucket": _metric_bucket(_int_or_none(row["current_comment_count"])),
                "title_keyword_signal": "high_signal" if _recommendation_signal(text) else "low_signal",
                "covered": row["status"] == "available" and bool(_clean(row["full_text"])),
            }
        )
    return records


def _summarize(records: list[dict[str, object]], key: str) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"covered": 0, "uncovered": 0})
    for record in records:
        label = _clean(record.get(key)) or "unknown"
        grouped[label]["covered" if _covered(record) else "uncovered"] += 1
    rows: list[dict[str, object]] = []
    for label, counts in grouped.items():
        total = counts["covered"] + counts["uncovered"]
        rows.append(
            {
                key: label,
                "covered": counts["covered"],
                "uncovered": counts["uncovered"],
                "total": total,
                "coverage_rate": round(counts["covered"] / total, 3) if total else 0,
            }
        )
    rows.sort(key=lambda row: (-int(row["total"]), str(row[key])))
    return rows


def build_transcript_coverage_bias_report() -> dict[str, list[dict[str, object]]]:
    records = _coverage_records()
    return {
        "creator": _summarize(records, "creator"),
        "creator_category": _summarize(records, "creator_category"),
        "year": _summarize(records, "year"),
        "view_count_bucket": _summarize(records, "view_count_bucket"),
        "like_count_bucket": _summarize(records, "like_count_bucket"),
        "comment_count_bucket": _summarize(records, "comment_count_bucket"),
        "title_keyword_signal": _summarize(records, "title_keyword_signal"),
    }


def build_transcript_priority_report(limit: int = 1000) -> dict[str, object]:
    candidates = _eligible_vendor_candidates(include_blocked=False)
    selected = select_transcript_vendor_batch(limit=limit, include_blocked=False)
    creator_counts: dict[str, int] = defaultdict(int)
    category_counts: dict[str, int] = defaultdict(int)
    for candidate in selected:
        creator_counts[candidate.creator] += 1
        category_counts[candidate.creator_category] += 1
    top_creator_share = (
        max(creator_counts.values()) / len(selected) if selected and creator_counts else 0.0
    )
    with connect() as conn:
        observed = conn.execute(
            """
            SELECT
              COUNT(DISTINCT yt.video_id) AS available_count,
              COUNT(tre.transcript_event_id) AS event_count
            FROM youtube_transcripts yt
            LEFT JOIN transcript_recommendation_events tre
              ON tre.video_id = yt.video_id
            WHERE yt.status = 'available'
              AND COALESCE(yt.full_text, '') != ''
            """
        ).fetchone()
    available_count = int(observed["available_count"] or 0)
    event_count = int(observed["event_count"] or 0)
    observed_event_rate = event_count / available_count if available_count else 0.0
    fallback_rate = 0.08
    estimated_rate = observed_event_rate or fallback_rate
    high_signal_count = sum(
        1
        for candidate in selected
        if candidate.recommendation_keyword_signal or candidate.ticker_signal_count
    )
    estimated_candidate_yield = round(high_signal_count * estimated_rate, 1)
    recommended_size = min(limit, len(candidates))
    return {
        "eligible_count": len(candidates),
        "selected_count": len(selected),
        "top_creators": sorted(
            [{"creator": key, "count": value} for key, value in creator_counts.items()],
            key=lambda row: (-int(row["count"]), str(row["creator"])),
        )[:10],
        "top_categories": sorted(
            [{"creator_category": key, "count": value} for key, value in category_counts.items()],
            key=lambda row: (-int(row["count"]), str(row["creator_category"])),
        )[:10],
        "top_high_signal_videos": [
            candidate.as_row()
            for candidate in sorted(selected, key=lambda item: -item.priority_score)[:20]
        ],
        "creator_concentration": {
            "distinct_creators": len(creator_counts),
            "top_creator_share": round(top_creator_share, 3),
        },
        "estimated_candidate_yield": {
            "observed_event_rate": round(observed_event_rate, 3),
            "estimated_events": estimated_candidate_yield,
            "high_signal_videos": high_signal_count,
        },
        "recommended_provider_batch_size": recommended_size,
    }
