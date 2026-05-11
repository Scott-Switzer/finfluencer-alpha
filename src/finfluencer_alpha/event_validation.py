from __future__ import annotations

import csv
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .classify import classify_text
from .config import EXPORTS_DIR, ensure_data_dirs
from .db import connect, init_db
from .ticker_extract import extract_tickers
from .utils import configure_csv_field_size_limit

VALIDATION_DIR = EXPORTS_DIR / "validation"
DEFAULT_SAMPLE_PATH = VALIDATION_DIR / "event_validation_sample.csv"
DEFAULT_LABELED_PATH = VALIDATION_DIR / "event_validation_sample_labeled.csv"
DEFAULT_README_PATH = VALIDATION_DIR / "README.md"
DEFAULT_SUMMARY_MD_PATH = VALIDATION_DIR / "event_validation_summary.md"
DEFAULT_SUMMARY_CSV_PATH = VALIDATION_DIR / "event_validation_summary.csv"

LABEL_COLUMNS = [
    "is_true_recommendation",
    "recommendation_type",
    "direction",
    "time_horizon",
    "conviction",
    "evidence_quality",
    "labeler_notes",
]

EVENT_VALIDATION_SAMPLE_COLUMNS = [
    "event_id",
    "candidate_window_id",
    "video_id",
    "creator",
    "title",
    "published_at",
    "video_url",
    "ticker",
    "company_name",
    "detected_signal",
    "detected_direction",
    "detected_action",
    "classifier_version",
    "transcript_window_text",
    "context_before",
    "context_after",
    "candidate_event_score",
    "actionability_score",
    "confidence_score",
    "confidence_label",
    "source_transcript_type",
    "transcript_source",
    "provider_name",
    "year",
    "creator_category",
    "title_keyword_signal",
    "engagement_bucket",
    "sampling_stratum",
    "sampling_reason",
    *LABEL_COLUMNS,
]

SUMMARY_COLUMNS = [
    "section",
    "segment",
    "sample_size",
    "labeled_count",
    "true_count",
    "false_positive_count",
    "unclear_count",
    "precision",
    "true_recommendation_rate",
    "false_positive_rate",
    "unclear_rate",
]

TRUE_LABEL_VALUES = {"yes", "no", "unclear"}
RECOMMENDATION_TYPE_VALUES = [
    "buy",
    "sell",
    "short",
    "hold",
    "avoid",
    "portfolio_update",
    "price_target",
    "earnings_reaction",
    "news_reaction",
    "macro_commentary",
    "casual_mention",
    "false_positive",
    "unclear",
]
DIRECTION_VALUES = ["positive", "negative", "neutral", "unclear"]
TIME_HORIZON_VALUES = ["short_term", "medium_term", "long_term", "unclear"]
CONVICTION_VALUES = ["low", "medium", "high", "unclear"]
EVIDENCE_QUALITY_VALUES = ["strong", "medium", "weak"]


@dataclass(frozen=True)
class EventValidationSampleResult:
    sample_path: Path
    readme_path: Path
    row_count: int
    total_events: int


@dataclass(frozen=True)
class EventValidationSummaryResult:
    markdown_path: Path
    csv_path: Path
    source_path: Path
    sample_size: int
    labeled_count: int


def _clean(value: object) -> str:
    return str(value or "").strip()


def _float_or_zero(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _year(value: object) -> str:
    text = _clean(value)
    return text[:4] if len(text) >= 4 and text[:4].isdigit() else "unknown"


def _engagement_bucket(view_count: object) -> str:
    try:
        views = int(view_count or 0)
    except (TypeError, ValueError):
        return "unknown"
    return "high" if views >= 100_000 else "low"


def _title_keyword_signal(title: str, description: str) -> str:
    text = f"{title or ''} {description or ''}".strip()
    if not text:
        return "unknown"
    result = classify_text(text)
    has_ticker = bool(extract_tickers(text))
    if (
        result.stance in {"bullish", "bearish"}
        and result.actionability_score >= 2
        and result.label not in {"retrospective_claim", "news_only"}
    ) or has_ticker:
        return "high_signal"
    return "low_signal"


def _trim_context(value: str, limit: int = 500) -> str:
    text = " ".join(_clean(value).split())
    return text[:limit]


def _context_around_window(
    full_text: str,
    window_text: str,
    *,
    context_chars: int = 500,
) -> tuple[str, str]:
    full = _clean(full_text)
    window = _clean(window_text)
    if not full or not window:
        return "", ""
    index = full.lower().find(window.lower())
    if index < 0:
        return "", ""
    before = full[max(0, index - context_chars) : index]
    after_start = index + len(window)
    after = full[after_start : after_start + context_chars]
    return _trim_context(before), _trim_context(after)


def _source_transcript_type(row: Any) -> str:
    source = _clean(row["transcript_source"]) or "unknown"
    provider = _clean(row["provider_name"])
    return f"{source}:{provider}" if provider else source


def _event_rows() -> list[dict[str, object]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              tre.transcript_event_id AS event_id,
              tcw.candidate_window_id,
              tre.video_id,
              y.channel_title AS creator,
              y.title,
              y.description,
              y.published_at,
              y.url AS video_url,
              y.current_view_count,
              tre.ticker,
              tre.company_name,
              tre.stance AS detected_direction,
              tre.detected_action,
              tre.actionability_score,
              tre.confidence_score,
              tre.confidence_label,
              tre.transcript_source,
              tre.provider_name,
              tre.classifier_version,
              COALESCE(tcw.evidence_window, tre.evidence_window) AS transcript_window_text,
              COALESCE(tcw.confidence_score, tre.confidence_score) AS candidate_confidence_score,
              COALESCE(tcw.actionability_score, tre.actionability_score) AS candidate_actionability_score,
              COALESCE(y.creator_category, c.category, ct.initial_category, 'unknown')
                AS creator_category,
              yt.full_text
            FROM transcript_recommendation_events tre
            LEFT JOIN transcript_candidate_windows tcw
              ON tcw.transcript_event_id = tre.transcript_event_id
            LEFT JOIN raw_youtube_videos y
              ON y.video_id = tre.video_id
            LEFT JOIN creators c
              ON c.platform = 'youtube'
             AND c.handle IN (y.channel_id, y.channel_title)
            LEFT JOIN creator_taxonomy ct
              ON ct.platform = 'youtube'
             AND ct.handle_or_channel IN (y.channel_id, y.channel_title)
            LEFT JOIN youtube_transcripts yt
              ON yt.video_id = tre.video_id
            ORDER BY y.published_at DESC, tre.video_id, tre.ticker, tre.transcript_event_id
            """
        ).fetchall()

    records: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for row in rows:
        event_id = _clean(row["event_id"])
        video_id = _clean(row["video_id"])
        ticker = _clean(row["ticker"])
        key = (event_id, video_id, ticker)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        window_text = _clean(row["transcript_window_text"])
        context_before, context_after = _context_around_window(
            _clean(row["full_text"]),
            window_text,
        )
        actionability_score = row["candidate_actionability_score"] or row["actionability_score"]
        confidence_score = row["candidate_confidence_score"] or row["confidence_score"]
        candidate_event_score = _float_or_zero(actionability_score) + _float_or_zero(confidence_score)
        year = _year(row["published_at"])
        creator = _clean(row["creator"]) or "unknown"
        creator_category = _clean(row["creator_category"]) or "unknown"
        title_signal = _title_keyword_signal(_clean(row["title"]), _clean(row["description"]))
        engagement = _engagement_bucket(row["current_view_count"])
        detected_action = _clean(row["detected_action"])
        detected_direction = _clean(row["detected_direction"])
        detected_signal = detected_action or detected_direction or _clean(row["confidence_label"])
        sampling_stratum = (
            f"creator={creator};year={year};category={creator_category};"
            f"title_signal={title_signal};signal={detected_signal or 'unknown'};"
            f"engagement={engagement}"
        )
        records.append(
            {
                "event_id": event_id,
                "candidate_window_id": _clean(row["candidate_window_id"]),
                "video_id": video_id,
                "creator": creator,
                "title": _clean(row["title"]),
                "published_at": _clean(row["published_at"]),
                "video_url": _clean(row["video_url"]) or f"https://www.youtube.com/watch?v={video_id}",
                "ticker": ticker,
                "company_name": _clean(row["company_name"]),
                "detected_signal": detected_signal,
                "detected_direction": detected_direction,
                "detected_action": detected_action,
                "classifier_version": _clean(row["classifier_version"]),
                "transcript_window_text": window_text,
                "context_before": context_before,
                "context_after": context_after,
                "candidate_event_score": round(candidate_event_score, 3),
                "actionability_score": actionability_score,
                "confidence_score": confidence_score,
                "confidence_label": _clean(row["confidence_label"]),
                "source_transcript_type": _source_transcript_type(row),
                "transcript_source": _clean(row["transcript_source"]),
                "provider_name": _clean(row["provider_name"]),
                "year": year,
                "creator_category": creator_category,
                "title_keyword_signal": title_signal,
                "engagement_bucket": engagement,
                "sampling_stratum": sampling_stratum,
                "sampling_reason": "",
                **{column: "" for column in LABEL_COLUMNS},
            }
        )
    return records


def _creator_coverage_rates() -> dict[str, float]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              COALESCE(y.channel_title, 'unknown') AS creator,
              COUNT(*) AS total,
              SUM(
                CASE
                  WHEN yt.status = 'available' AND COALESCE(yt.full_text, '') != ''
                  THEN 1 ELSE 0
                END
              ) AS covered
            FROM raw_youtube_videos y
            LEFT JOIN youtube_transcripts yt
              ON yt.video_id = y.video_id
            WHERE COALESCE(y.excluded_flag, 0) = 0
            GROUP BY COALESCE(y.channel_title, 'unknown')
            """
        ).fetchall()
    rates: dict[str, float] = {}
    for row in rows:
        total = int(row["total"] or 0)
        rates[row["creator"]] = (float(row["covered"] or 0) / total) if total else 0.0
    return rates


def _low_coverage_creators(rows: list[dict[str, object]]) -> set[str]:
    coverage = _creator_coverage_rates()
    creators = sorted({_clean(row["creator"]) for row in rows})
    if not creators:
        return set()
    ranked = sorted(creators, key=lambda creator: (coverage.get(creator, 0.0), creator.lower()))
    return set(ranked[: max(1, len(ranked) // 4)])


def _recent_years(rows: list[dict[str, object]]) -> set[str]:
    years = sorted(
        {str(row["year"]) for row in rows if str(row["year"]).isdigit()},
        reverse=True,
    )
    return set(years[:2])


def _dedupe_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (_clean(row["event_id"]), _clean(row["video_id"]), _clean(row["ticker"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _select_rows(
    rows: list[dict[str, object]],
    *,
    sample_size: int,
    seed: int,
) -> list[dict[str, object]]:
    rows = _dedupe_rows(rows)
    if len(rows) <= sample_size:
        return [dict(row, sampling_reason="all_available_events") for row in rows]
    rng = random.Random(seed)
    low_coverage = _low_coverage_creators(rows)
    recent_years = _recent_years(rows)
    selected: list[dict[str, object]] = []
    selected_keys: set[tuple[str, str, str]] = set()

    def key_for(row: dict[str, object]) -> tuple[str, str, str]:
        return (_clean(row["event_id"]), _clean(row["video_id"]), _clean(row["ticker"]))

    def add(row: dict[str, object], reason: str) -> bool:
        key = key_for(row)
        if key in selected_keys:
            return False
        selected_keys.add(key)
        selected.append(dict(row, sampling_reason=reason))
        return True

    def shuffled(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
        candidates = list(candidates)
        candidates.sort(
            key=lambda row: (
                str(row["sampling_stratum"]),
                -_float_or_zero(row["candidate_event_score"]),
                str(row["event_id"]),
            )
        )
        rng.shuffle(candidates)
        return candidates

    low_coverage_quota = min(
        sum(1 for row in rows if _clean(row["creator"]) in low_coverage),
        max(1, sample_size // 5),
    )
    for row in shuffled([row for row in rows if _clean(row["creator"]) in low_coverage]):
        if len([r for r in selected if r["sampling_reason"] == "low_coverage_creator"]) >= low_coverage_quota:
            break
        add(row, "low_coverage_creator")

    recent_quota = min(
        sum(1 for row in rows if _clean(row["year"]) in recent_years),
        max(1, sample_size // 4),
    )
    for row in shuffled([row for row in rows if _clean(row["year"]) in recent_years]):
        if len([r for r in selected if r["sampling_reason"] == "recent_year"]) >= recent_quota:
            break
        add(row, "recent_year")

    buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        buckets[str(row["sampling_stratum"])].append(row)
    bucket_keys = sorted(buckets)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    while len(selected) < sample_size and bucket_keys:
        progressed = False
        for bucket_key in list(bucket_keys):
            bucket = buckets[bucket_key]
            while bucket:
                row = bucket.pop(0)
                if add(row, "stratified_round_robin"):
                    progressed = True
                    break
            if not bucket:
                bucket_keys.remove(bucket_key)
            if len(selected) >= sample_size:
                break
        if not progressed:
            break
    selected.sort(
        key=lambda row: (
            not str(row["event_id"]).isdigit(),
            int(row["event_id"]) if str(row["event_id"]).isdigit() else 0,
            str(row["event_id"]),
        )
    )
    return selected[:sample_size]


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_readme(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Event Validation Labeling Guide",
        "",
        "Use `event_validation_sample.csv` for human review. Fill the blank label columns, "
        "then save a labeled copy as `event_validation_sample_labeled.csv`.",
        "",
        "## Label Values",
        "",
        "- `is_true_recommendation`: yes, no, unclear",
        "- `recommendation_type`: " + ", ".join(RECOMMENDATION_TYPE_VALUES),
        "- `direction`: " + ", ".join(DIRECTION_VALUES),
        "- `time_horizon`: " + ", ".join(TIME_HORIZON_VALUES),
        "- `conviction`: " + ", ".join(CONVICTION_VALUES),
        "- `evidence_quality`: " + ", ".join(EVIDENCE_QUALITY_VALUES),
        "- `labeler_notes`: free text",
        "",
        "Treat an event as `yes` only when the transcript window or surrounding context "
        "contains a concrete stock view or portfolio action attributable to the creator.",
        "Use `no` for casual ticker mentions, news-only discussion, third-party attribution, "
        "or false-positive ticker extraction. Use `unclear` when the context is insufficient.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_event_validation_sample(
    *,
    sample_size: int = 150,
    seed: int = 496,
    output_path: Path = DEFAULT_SAMPLE_PATH,
    readme_path: Path = DEFAULT_README_PATH,
) -> EventValidationSampleResult:
    if sample_size < 1:
        raise ValueError("sample_size must be at least 1")
    ensure_data_dirs()
    rows = _event_rows()
    selected = _select_rows(rows, sample_size=sample_size, seed=seed)
    sample_path = _write_csv(output_path, selected, EVENT_VALIDATION_SAMPLE_COLUMNS)
    readme = _write_readme(readme_path)
    return EventValidationSampleResult(
        sample_path=sample_path,
        readme_path=readme,
        row_count=len(selected),
        total_events=len(rows),
    )


def _read_validation_rows(path: Path) -> list[dict[str, str]]:
    configure_csv_field_size_limit()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        rows = [dict(row) for row in reader]
    for row in rows:
        for column in EVENT_VALIDATION_SAMPLE_COLUMNS:
            row.setdefault(column, "")
    return rows


def _validation_source_path(
    labeled_path: Path = DEFAULT_LABELED_PATH,
    sample_path: Path = DEFAULT_SAMPLE_PATH,
) -> Path:
    if labeled_path.exists():
        return labeled_path
    if sample_path.exists():
        return sample_path
    raise FileNotFoundError(
        f"No validation file found at {labeled_path} or {sample_path}."
    )


def _normalized_label(row: dict[str, str]) -> str:
    value = _clean(row.get("is_true_recommendation")).lower()
    return value if value in TRUE_LABEL_VALUES else ""


def _rate(count: int, denominator: int) -> float:
    return round(count / denominator, 3) if denominator else 0.0


def _summary_row(
    *,
    section: str,
    segment: str,
    rows: list[dict[str, str]],
) -> dict[str, object]:
    labels = [_normalized_label(row) for row in rows]
    labeled_count = sum(1 for label in labels if label)
    true_count = labels.count("yes")
    false_count = labels.count("no")
    unclear_count = labels.count("unclear")
    precision_denominator = true_count + false_count
    return {
        "section": section,
        "segment": segment,
        "sample_size": len(rows),
        "labeled_count": labeled_count,
        "true_count": true_count,
        "false_positive_count": false_count,
        "unclear_count": unclear_count,
        "precision": _rate(true_count, precision_denominator),
        "true_recommendation_rate": _rate(true_count, labeled_count),
        "false_positive_rate": _rate(false_count, labeled_count),
        "unclear_rate": _rate(unclear_count, labeled_count),
    }


def _group_summary_rows(
    rows: list[dict[str, str]],
    *,
    key: str,
    section: str,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[_clean(row.get(key)) or "unknown"].append(row)
    return [
        _summary_row(section=section, segment=segment, rows=group_rows)
        for segment, group_rows in sorted(grouped.items())
    ]


def _false_positive_categories(rows: list[dict[str, str]]) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for row in rows:
        if _normalized_label(row) != "no":
            continue
        category = _clean(row.get("recommendation_type")) or "unspecified"
        counter[category] += 1
    return counter.most_common()


def _example_sort_key(row: dict[str, str]) -> tuple[int, int, float]:
    quality_rank = {"weak": 1, "medium": 2, "strong": 3}
    conviction_rank = {"low": 1, "medium": 2, "high": 3}
    return (
        quality_rank.get(_clean(row.get("evidence_quality")).lower(), 0),
        conviction_rank.get(_clean(row.get("conviction")).lower(), 0),
        _float_or_zero(row.get("candidate_event_score")),
    )


def _examples(
    rows: list[dict[str, str]],
    *,
    label: str,
    limit: int = 5,
) -> list[dict[str, str]]:
    matching = [row for row in rows if _normalized_label(row) == label]
    matching.sort(key=_example_sort_key, reverse=True)
    return matching[:limit]


def _example_lines(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return ["- None labeled yet."]
    lines: list[str] = []
    for row in rows:
        snippet = _trim_context(row.get("transcript_window_text", ""), limit=180)
        lines.append(
            "- "
            f"{row.get('event_id')} | {row.get('creator')} | {row.get('ticker')} | "
            f"{row.get('recommendation_type') or 'untyped'} | {snippet}"
        )
    return lines


def _write_summary_markdown(
    path: Path,
    *,
    source_path: Path,
    summary_rows: list[dict[str, object]],
    rows: list[dict[str, str]],
) -> Path:
    overall = summary_rows[0]
    false_categories = _false_positive_categories(rows)
    lines = [
        "# Event Validation Summary",
        "",
        f"- Source file: `{source_path}`",
        f"- Sample size: {overall['sample_size']}",
        f"- Labeled rows: {overall['labeled_count']}",
        f"- True recommendation rate: {float(overall['true_recommendation_rate']):.1%}",
        f"- False positive rate: {float(overall['false_positive_rate']):.1%}",
        f"- Unclear rate: {float(overall['unclear_rate']):.1%}",
        "",
        "## Most Common False-Positive Categories",
        "",
    ]
    if false_categories:
        lines.extend(f"- {category}: {count}" for category, count in false_categories[:10])
    else:
        lines.append("- None labeled yet.")
    lines.extend(
        [
            "",
            "## Strongest True Positives",
            "",
            *_example_lines(_examples(rows, label="yes")),
            "",
            "## Likely False Positives",
            "",
            *_example_lines(_examples(rows, label="no")),
            "",
            "## Precision Tables",
            "",
            "See `event_validation_summary.csv` for precision by creator, year, "
            "title signal, and recommendation type.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def summarize_event_validation(
    *,
    labeled_path: Path = DEFAULT_LABELED_PATH,
    sample_path: Path = DEFAULT_SAMPLE_PATH,
    markdown_path: Path = DEFAULT_SUMMARY_MD_PATH,
    csv_path: Path = DEFAULT_SUMMARY_CSV_PATH,
) -> EventValidationSummaryResult:
    source_path = _validation_source_path(labeled_path=labeled_path, sample_path=sample_path)
    rows = _read_validation_rows(source_path)
    summary_rows: list[dict[str, object]] = [_summary_row(section="overall", segment="all", rows=rows)]
    summary_rows.extend(_group_summary_rows(rows, key="creator", section="precision_by_creator"))
    summary_rows.extend(_group_summary_rows(rows, key="year", section="precision_by_year"))
    summary_rows.extend(
        _group_summary_rows(
            rows,
            key="title_keyword_signal",
            section="precision_by_title_keyword_signal",
        )
    )
    summary_rows.extend(
        _group_summary_rows(
            rows,
            key="recommendation_type",
            section="precision_by_recommendation_type",
        )
    )
    _write_csv(csv_path, summary_rows, SUMMARY_COLUMNS)
    _write_summary_markdown(
        markdown_path,
        source_path=source_path,
        summary_rows=summary_rows,
        rows=rows,
    )
    overall = summary_rows[0]
    return EventValidationSummaryResult(
        markdown_path=markdown_path,
        csv_path=csv_path,
        source_path=source_path,
        sample_size=int(overall["sample_size"]),
        labeled_count=int(overall["labeled_count"]),
    )
