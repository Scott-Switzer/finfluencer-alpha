from __future__ import annotations

import csv
import json
import os
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import requests

from .config import EXPORTS_DIR, ensure_data_dirs
from .event_validation import (
    CONVICTION_VALUES,
    DIRECTION_VALUES,
    EVENT_VALIDATION_SAMPLE_COLUMNS,
    EVIDENCE_QUALITY_VALUES,
    RECOMMENDATION_TYPE_VALUES,
    TIME_HORIZON_VALUES,
    TRUE_LABEL_VALUES,
)
from .utils import configure_csv_field_size_limit

VALIDATION_DIR = EXPORTS_DIR / "validation"
DEFAULT_AUTO_LABEL_INPUT_PATH = VALIDATION_DIR / "event_validation_sample.csv"
DEFAULT_AUTO_LABEL_OUTPUT_PATH = VALIDATION_DIR / "event_validation_sample_auto_labeled.csv"
DEFAULT_REVIEW_OUTPUT_PATH = VALIDATION_DIR / "event_validation_review_needed.csv"
DEFAULT_AUTO_SUMMARY_MD_PATH = VALIDATION_DIR / "auto_labeling_summary.md"
DEFAULT_AUTO_SUMMARY_CSV_PATH = VALIDATION_DIR / "auto_labeling_summary.csv"
DEFAULT_CLEAN_EVENTS_OUTPUT_PATH = VALIDATION_DIR / "clean_auto_labeled_events.csv"
DEFAULT_CLEAN_EVENTS_EXCLUSIONS_PATH = VALIDATION_DIR / "clean_auto_labeled_events_exclusions.csv"
DEFAULT_CLEAN_EVENTS_SUMMARY_PATH = VALIDATION_DIR / "clean_auto_labeled_events_summary.md"
DEFAULT_TRANSCRIPT_EVENTS_EXPORT_PATH = EXPORTS_DIR / "transcript_recommendation_events.csv"

PROMPT_VERSION = "auto_event_labeling_v1"
DEFAULT_LLM_MODEL = "gpt-4o-mini"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"

AUDIT_COLUMNS = [
    "auto_label_method",
    "auto_label_confidence",
    "auto_label_needs_review",
    "auto_label_reason",
    "auto_label_evidence_quote",
    "auto_label_model",
    "auto_label_timestamp_utc",
    "auto_label_prompt_version",
    "rule_flags",
    "llm_raw_json",
]

AUTO_LABEL_SUMMARY_COLUMNS = [
    "section",
    "segment",
    "count",
    "share",
    "average_confidence",
]

CLEAN_EVENT_COLUMNS = [
    "event_id",
    "video_id",
    "creator",
    "title",
    "published_at",
    "event_date_utc",
    "ticker",
    "company_name",
    "recommendation_type",
    "direction",
    "confidence",
    "evidence_quality",
    "source_transcript_type",
    "transcript_source",
    "provider_name",
    "video_url",
    "transcript_window_text",
    "context_before",
    "context_after",
    "auto_label_reason",
    "auto_label_evidence_quote",
]

CLEAN_EXCLUSION_COLUMNS = [*CLEAN_EVENT_COLUMNS, "clean_event_exclusion_reason"]

AMBIGUOUS_TICKERS = {
    "ALL",
    "ARE",
    "BE",
    "BIG",
    "BY",
    "CAN",
    "CASH",
    "FOR",
    "GOOD",
    "LIFE",
    "LOVE",
    "LOW",
    "NOW",
    "ON",
    "OPEN",
    "OUT",
    "REAL",
    "SO",
    "TRUE",
    "UP",
    "VERY",
    "WELL",
    "YOU",
}

THIRD_PARTY_PATTERN = re.compile(
    r"\b("
    r"analysts?|wall street|warren buffett|berkshire|cathie wood|ark invest|"
    r"the fed|federal reserve|vanguard|blackrock|state street|congress|senator|"
    r"nancy pelosi|insiders?|shareholders?|investors?|hedge funds?|"
    r"nvidia|microsoft|apple|google|alphabet|amazon|meta|tesla"
    r")\b.{0,80}\b("
    r"bought|buying|sold|selling|trimmed|added|loading up|recommend|upgraded|downgraded|"
    r"raised|lowered|invested|stake|holding|holdings"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)

NEWS_PATTERN = re.compile(
    r"\b("
    r"reported|announced|earnings|revenue|guidance|lawsuit|investigation|"
    r"merger|acquisition|partnership|clearance|approval|customer|supplier|"
    r"competitor|comparable|compared to|reacts? to|in the news"
    r")\b",
    re.IGNORECASE,
)

MACRO_PATTERN = re.compile(
    r"\b("
    r"inflation|interest rates?|rate cuts?|rate hikes?|recession|tariffs?|"
    r"the economy|macro|s&p 500|index funds?|etfs?|benchmark|yield curve|"
    r"dividend investors?|passive investors?"
    r")\b",
    re.IGNORECASE,
)

HISTORICAL_PATTERN = re.compile(
    r"\b("
    r"used to|last year|last quarter|previously|historically|back in|"
    r"in 20\d{2}|was buying|were buying|was selling|were selling|"
    r"shares are held|held by|largest shareholders?"
    r")\b",
    re.IGNORECASE,
)

FALSE_TICKER_CONTEXT_PATTERN = re.compile(
    r"\b("
    r"you should|you know|you can|if you|when you|what you|how you|why you|"
    r"that you|and you|for you|with you|to you|of you|do you|thank you|"
    r"are you|did you|on the other hand|all of|right now|so that"
    r")\b",
    re.IGNORECASE,
)

TRUE_SIGNAL_PATTERNS: list[tuple[re.Pattern[str], str, str, str, str, float]] = [
    (
        re.compile(
            r"\b("
            r"i am|i'm|im|we are|we're|i would|we would|i will|we will|"
            r"i'm going to|i am going to|i'm gonna|we're going to"
            r")\s+(start\s+)?(buy|buying|add|adding|accumulate|accumulating)\b",
            re.IGNORECASE,
        ),
        "buy",
        "positive",
        "high",
        "first_person_buy",
        0.93,
    ),
    (
        re.compile(r"\b(i bought|we bought|i just bought|i've bought|we've bought)\b", re.IGNORECASE),
        "buy",
        "positive",
        "medium",
        "creator_bought",
        0.91,
    ),
    (
        re.compile(r"\b(i own|we own|i still own|we still own|my position|our position)\b", re.IGNORECASE),
        "portfolio_update",
        "positive",
        "medium",
        "creator_owns_position",
        0.88,
    ),
    (
        re.compile(
            r"\b(i recommend|we recommend|my top stock|our top stock|"
            r"best stocks? to buy|top stocks? to buy|you may want to buy|worth buying)\b",
            re.IGNORECASE,
        ),
        "buy",
        "positive",
        "high",
        "direct_recommendation_language",
        0.90,
    ),
    (
        re.compile(
            r"\b(i am|i'm|im|we are|we're|i would|we would|i will|we will)\s+"
            r"(sell|selling|trim|trimming|reduce|reducing)\b|\b(i sold|we sold|i trimmed|we trimmed)\b",
            re.IGNORECASE,
        ),
        "sell",
        "negative",
        "medium",
        "creator_sell_action",
        0.92,
    ),
    (
        re.compile(
            r"\b(i am|i'm|im|we are|we're|i would|we would)\s+"
            r"(short|shorting)\b|\b(short this|would short)\b",
            re.IGNORECASE,
        ),
        "short",
        "negative",
        "medium",
        "creator_short_action",
        0.92,
    ),
    (
        re.compile(r"\b(avoid|stay away from|do not buy|don't buy)\b", re.IGNORECASE),
        "avoid",
        "negative",
        "medium",
        "avoid_language",
        0.86,
    ),
    (
        re.compile(r"\b(price target|my target|our target|target price)\b", re.IGNORECASE),
        "price_target",
        "neutral",
        "medium",
        "price_target_language",
        0.84,
    ),
    (
        re.compile(r"\b(undervalued|cheap at these levels|trading below intrinsic value)\b", re.IGNORECASE),
        "buy",
        "positive",
        "medium",
        "valuation_positive",
        0.82,
    ),
    (
        re.compile(r"\b(overvalued|too expensive|trading above intrinsic value)\b", re.IGNORECASE),
        "avoid",
        "negative",
        "medium",
        "valuation_negative",
        0.82,
    ),
    (
        re.compile(
            r"\b(i am|i'm|im|we are|we're|i would|we would)\s+"
            r"(hold|holding)\b|\b(i'm holding|i am holding|we're holding|we are holding)\b",
            re.IGNORECASE,
        ),
        "hold",
        "neutral",
        "medium",
        "creator_hold_action",
        0.86,
    ),
]


@dataclass(frozen=True)
class AutoLabelDecision:
    is_true_recommendation: str
    recommendation_type: str
    direction: str
    time_horizon: str
    conviction: str
    evidence_quality: str
    labeler_notes: str
    auto_label_method: str
    auto_label_confidence: float
    auto_label_needs_review: bool
    auto_label_reason: str
    auto_label_evidence_quote: str
    auto_label_model: str = ""
    auto_label_prompt_version: str = PROMPT_VERSION
    rule_flags: tuple[str, ...] = ()
    llm_raw_json: str = ""


@dataclass(frozen=True)
class AutoLabelingResult:
    output_path: Path
    review_output_path: Path
    summary_md_path: Path
    summary_csv_path: Path
    total_rows: int
    rows_labeled_yes: int
    rows_labeled_no: int
    rows_labeled_unclear: int
    rows_labeled_by_rules: int
    rows_labeled_by_llm: int
    rows_needing_review: int
    dry_run: bool


@dataclass(frozen=True)
class CleanAutoLabeledEventsResult:
    output_path: Path
    exclusions_output_path: Path
    summary_md_path: Path
    included_rows: int
    excluded_rows: int
    dry_run: bool


def _clean(value: object) -> str:
    return str(value or "").strip()


def _normalize_space(value: object) -> str:
    return " ".join(_clean(value).split())


def _combined_text(row: dict[str, Any]) -> str:
    return _normalize_space(
        " ".join(
            [
                _clean(row.get("context_before")),
                _clean(row.get("transcript_window_text")),
                _clean(row.get("context_after")),
            ]
        )
    )


def _target_regex(ticker: str) -> re.Pattern[str] | None:
    if not ticker:
        return None
    return re.compile(rf"(?<![A-Za-z0-9])\$?{re.escape(ticker)}(?![A-Za-z0-9])", re.IGNORECASE)


def _target_is_mentioned(row: dict[str, Any], text: str) -> bool:
    ticker = _clean(row.get("ticker")).upper()
    company = _clean(row.get("company_name")).lower()
    if not ticker and not company:
        return True
    ticker_pattern = _target_regex(ticker)
    if ticker_pattern and ticker_pattern.search(text):
        return True
    if company and len(company) >= 4 and company in text.lower():
        return True
    company_head = company.split(",", maxsplit=1)[0].split(" inc", maxsplit=1)[0].strip()
    return bool(company_head and len(company_head) >= 4 and company_head in text.lower())


def _has_stock_context_for_ticker(row: dict[str, Any], text: str) -> bool:
    ticker = _clean(row.get("ticker")).upper()
    if not ticker:
        return True
    lower = text.lower()
    return any(
        phrase in lower
        for phrase in [
            f"${ticker.lower()}",
            f"{ticker.lower()} stock",
            f"{ticker.lower()} shares",
            f"{ticker.lower()} earnings",
            f"buy {ticker.lower()}",
            f"sell {ticker.lower()}",
            f"short {ticker.lower()}",
            f"long {ticker.lower()}",
        ]
    )


def _evidence_quote(text: str, match: re.Match[str] | None = None, *, limit: int = 240) -> str:
    text = _normalize_space(text)
    if not text:
        return ""
    if match is None:
        return text[:limit]
    start = max(0, match.start() - 90)
    end = min(len(text), match.end() + 110)
    return text[start:end].strip()[:limit]


def _confidence_needs_review(confidence: float, min_auto_confidence: float, label: str) -> bool:
    return confidence < min_auto_confidence or label == "unclear"


def _decision(
    *,
    is_true_recommendation: str,
    recommendation_type: str,
    direction: str,
    time_horizon: str,
    conviction: str,
    evidence_quality: str,
    labeler_notes: str,
    auto_label_method: str,
    auto_label_confidence: float,
    auto_label_reason: str,
    auto_label_evidence_quote: str,
    min_auto_confidence: float,
    auto_label_model: str = "",
    rule_flags: tuple[str, ...] = (),
    llm_raw_json: str = "",
    force_needs_review: bool = False,
) -> AutoLabelDecision:
    confidence = max(0.0, min(1.0, round(float(auto_label_confidence), 3)))
    needs_review = force_needs_review or _confidence_needs_review(
        confidence,
        min_auto_confidence,
        is_true_recommendation,
    )
    return AutoLabelDecision(
        is_true_recommendation=is_true_recommendation,
        recommendation_type=recommendation_type,
        direction=direction,
        time_horizon=time_horizon,
        conviction=conviction,
        evidence_quality=evidence_quality,
        labeler_notes=labeler_notes,
        auto_label_method=auto_label_method,
        auto_label_confidence=confidence,
        auto_label_needs_review=needs_review,
        auto_label_reason=auto_label_reason,
        auto_label_evidence_quote=auto_label_evidence_quote,
        auto_label_model=auto_label_model,
        rule_flags=rule_flags,
        llm_raw_json=llm_raw_json,
    )


def _unclear_decision(
    row: dict[str, Any],
    *,
    method: str,
    reason: str,
    min_auto_confidence: float,
    model: str = "",
    rule_flags: tuple[str, ...] = (),
    llm_raw_json: str = "",
) -> AutoLabelDecision:
    quote = _evidence_quote(_clean(row.get("transcript_window_text")) or _combined_text(row))
    return _decision(
        is_true_recommendation="unclear",
        recommendation_type="unclear",
        direction="unclear",
        time_horizon="unclear",
        conviction="unclear",
        evidence_quality="weak",
        labeler_notes=reason,
        auto_label_method=method,
        auto_label_confidence=0.35,
        auto_label_reason=reason,
        auto_label_evidence_quote=quote,
        min_auto_confidence=min_auto_confidence,
        auto_label_model=model,
        rule_flags=rule_flags,
        llm_raw_json=llm_raw_json,
        force_needs_review=True,
    )


def label_event_with_rules(
    row: dict[str, Any],
    *,
    min_auto_confidence: float = 0.75,
) -> AutoLabelDecision:
    """Label one transcript event with deterministic, auditable rules."""

    text = _combined_text(row)
    window_text = _normalize_space(row.get("transcript_window_text"))
    flags: list[str] = []

    if len(text) < 40:
        return _unclear_decision(
            row,
            method="rules",
            reason="insufficient transcript context for deterministic labeling",
            min_auto_confidence=min_auto_confidence,
            rule_flags=("insufficient_context",),
        )

    ticker = _clean(row.get("ticker")).upper()
    if (
        ticker in AMBIGUOUS_TICKERS
        and FALSE_TICKER_CONTEXT_PATTERN.search(text)
        and not _has_stock_context_for_ticker(row, text)
    ):
        match = FALSE_TICKER_CONTEXT_PATTERN.search(text)
        return _decision(
            is_true_recommendation="no",
            recommendation_type="false_positive",
            direction="unclear",
            time_horizon="unclear",
            conviction="low",
            evidence_quality="strong",
            labeler_notes="Deterministic rule: ambiguous ticker appears as ordinary language.",
            auto_label_method="rules",
            auto_label_confidence=0.90,
            auto_label_reason="ambiguous_ticker_false_positive",
            auto_label_evidence_quote=_evidence_quote(text, match),
            min_auto_confidence=min_auto_confidence,
            rule_flags=("ambiguous_ticker_false_positive",),
        )

    target_mentioned = _target_is_mentioned(row, text)
    if not target_mentioned:
        flags.append("target_not_explicit_in_context")

    third_party_match = THIRD_PARTY_PATTERN.search(text)
    news_match = NEWS_PATTERN.search(text)
    macro_match = MACRO_PATTERN.search(text)
    historical_match = HISTORICAL_PATTERN.search(text)

    for pattern, rec_type, direction, conviction, flag, base_confidence in TRUE_SIGNAL_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        true_flags = [flag]
        confidence = base_confidence
        evidence_quality = "strong" if flag.startswith(("first_person", "creator_")) else "medium"
        if not target_mentioned:
            confidence -= 0.18
        if third_party_match and not flag.startswith(("first_person", "creator_")):
            confidence -= 0.25
            true_flags.append("possible_third_party_attribution")
        if historical_match and flag not in {"creator_bought", "creator_owns_position"}:
            confidence -= 0.12
            true_flags.append("possible_historical_context")
        if flag == "price_target_language":
            detected_direction = _clean(row.get("detected_direction")).lower()
            if detected_direction in {"bullish", "positive"}:
                direction = "positive"
            elif detected_direction in {"bearish", "negative"}:
                direction = "negative"
        confidence = max(0.60, confidence)
        reason = f"deterministic explicit recommendation signal: {flag}"
        return _decision(
            is_true_recommendation="yes",
            recommendation_type=rec_type,
            direction=direction,
            time_horizon="unclear",
            conviction=conviction,
            evidence_quality=evidence_quality,
            labeler_notes=reason,
            auto_label_method="rules",
            auto_label_confidence=confidence,
            auto_label_reason=reason,
            auto_label_evidence_quote=_evidence_quote(text, match),
            min_auto_confidence=min_auto_confidence,
            rule_flags=tuple([*flags, *true_flags]),
        )

    if third_party_match:
        return _decision(
            is_true_recommendation="no",
            recommendation_type="false_positive",
            direction="unclear",
            time_horizon="unclear",
            conviction="low",
            evidence_quality="strong",
            labeler_notes="Deterministic rule: recommendation/action is attributed to a third party.",
            auto_label_method="rules",
            auto_label_confidence=0.89,
            auto_label_reason="third_party_attribution_not_creator_recommendation",
            auto_label_evidence_quote=_evidence_quote(text, third_party_match),
            min_auto_confidence=min_auto_confidence,
            rule_flags=tuple([*flags, "third_party_attribution"]),
        )

    if news_match:
        return _decision(
            is_true_recommendation="no",
            recommendation_type="news_reaction",
            direction="neutral",
            time_horizon="unclear",
            conviction="low",
            evidence_quality="medium",
            labeler_notes="Deterministic rule: event is news or business-description discussion without a creator recommendation.",
            auto_label_method="rules",
            auto_label_confidence=0.79,
            auto_label_reason="news_or_business_context_without_creator_recommendation",
            auto_label_evidence_quote=_evidence_quote(text, news_match),
            min_auto_confidence=min_auto_confidence,
            rule_flags=tuple([*flags, "news_only_or_business_context"]),
        )

    if macro_match:
        return _decision(
            is_true_recommendation="no",
            recommendation_type="macro_commentary",
            direction="neutral",
            time_horizon="unclear",
            conviction="low",
            evidence_quality="medium",
            labeler_notes="Deterministic rule: macro or index discussion lacks a tradeable creator stock view.",
            auto_label_method="rules",
            auto_label_confidence=0.78,
            auto_label_reason="macro_or_index_commentary_without_tradeable_recommendation",
            auto_label_evidence_quote=_evidence_quote(text, macro_match),
            min_auto_confidence=min_auto_confidence,
            rule_flags=tuple([*flags, "macro_commentary"]),
        )

    if historical_match:
        return _decision(
            is_true_recommendation="no",
            recommendation_type="false_positive",
            direction="unclear",
            time_horizon="unclear",
            conviction="low",
            evidence_quality="medium",
            labeler_notes="Deterministic rule: mention is historical or retrospective rather than a current recommendation.",
            auto_label_method="rules",
            auto_label_confidence=0.76,
            auto_label_reason="historical_or_retrospective_context",
            auto_label_evidence_quote=_evidence_quote(text, historical_match),
            min_auto_confidence=min_auto_confidence,
            rule_flags=tuple([*flags, "historical_or_retrospective"]),
        )

    if target_mentioned and len(window_text) >= 25:
        return _unclear_decision(
            row,
            method="rules",
            reason="ticker/company mention found but deterministic rules found no clear creator recommendation",
            min_auto_confidence=min_auto_confidence,
            rule_flags=tuple([*flags, "no_clear_rule_match"]),
        )

    return _unclear_decision(
        row,
        method="rules",
        reason="insufficient target-specific context for deterministic labeling",
        min_auto_confidence=min_auto_confidence,
        rule_flags=tuple([*flags, "insufficient_target_context"]),
    )


def _llm_model(option_value: str | None = None) -> str:
    return _clean(option_value) or _clean(os.getenv("AUTO_LABEL_LLM_MODEL")) or DEFAULT_LLM_MODEL


def _llm_input(row: dict[str, Any]) -> dict[str, str]:
    allowed_fields = [
        "event_id",
        "creator",
        "title",
        "ticker",
        "company_name",
        "detected_signal",
        "detected_direction",
        "transcript_window_text",
        "context_before",
        "context_after",
    ]
    return {field: _clean(row.get(field)) for field in allowed_fields}


def _llm_json_schema() -> dict[str, Any]:
    return {
        "name": "event_recommendation_label",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "is_true_recommendation": {"type": "string", "enum": sorted(TRUE_LABEL_VALUES)},
                "recommendation_type": {"type": "string", "enum": RECOMMENDATION_TYPE_VALUES},
                "direction": {"type": "string", "enum": DIRECTION_VALUES},
                "time_horizon": {"type": "string", "enum": TIME_HORIZON_VALUES},
                "conviction": {"type": "string", "enum": CONVICTION_VALUES},
                "evidence_quality": {"type": "string", "enum": EVIDENCE_QUALITY_VALUES},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "needs_review": {"type": "boolean"},
                "reason": {"type": "string"},
                "evidence_quote": {"type": "string"},
            },
            "required": [
                "is_true_recommendation",
                "recommendation_type",
                "direction",
                "time_horizon",
                "conviction",
                "evidence_quality",
                "confidence",
                "needs_review",
                "reason",
                "evidence_quote",
            ],
        },
    }


def _llm_messages(row: dict[str, Any]) -> list[dict[str, str]]:
    system = (
        "You label YouTube finance transcript events for an academic event-study dataset. "
        "Treat a row as yes only if the creator gives a concrete stock view or portfolio action. "
        "Treat a row as no if the creator only reports news, discusses another investor's action, "
        "mentions a ticker as an example/customer/supplier/comparable, makes a non-tradeable macro "
        "statement, or the recommendation is not attributable to the creator. Use unclear when "
        "evidence is insufficient. Be conservative: false positives are worse than false negatives."
    )
    user = json.dumps(_llm_input(row), ensure_ascii=True, sort_keys=True)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _call_openai_label(row: dict[str, Any], *, model: str, api_key: str) -> dict[str, Any]:
    response = requests.post(
        OPENAI_CHAT_COMPLETIONS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0,
            "messages": _llm_messages(row),
            "response_format": {
                "type": "json_schema",
                "json_schema": _llm_json_schema(),
            },
        },
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            "OpenAI auto-labeling request failed "
            f"with status {response.status_code}: {response.text[:500]}"
        )
    payload = response.json()
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("OpenAI auto-labeling response was missing message content.") from exc
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI auto-labeling response was not valid JSON.") from exc


def _validate_llm_payload(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if payload.get("is_true_recommendation") not in TRUE_LABEL_VALUES:
        errors.append("is_true_recommendation")
    if payload.get("recommendation_type") not in RECOMMENDATION_TYPE_VALUES:
        errors.append("recommendation_type")
    if payload.get("direction") not in DIRECTION_VALUES:
        errors.append("direction")
    if payload.get("time_horizon") not in TIME_HORIZON_VALUES:
        errors.append("time_horizon")
    if payload.get("conviction") not in CONVICTION_VALUES:
        errors.append("conviction")
    if payload.get("evidence_quality") not in EVIDENCE_QUALITY_VALUES:
        errors.append("evidence_quality")
    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError):
        errors.append("confidence")
        confidence = 0.0
    if not 0 <= confidence <= 1:
        errors.append("confidence")
    if not isinstance(payload.get("needs_review"), bool):
        errors.append("needs_review")
    if errors:
        raise RuntimeError("OpenAI auto-labeling response failed schema validation: " + ", ".join(errors))
    payload["confidence"] = confidence
    payload["reason"] = _clean(payload.get("reason"))
    payload["evidence_quote"] = _clean(payload.get("evidence_quote"))
    return payload


def _llm_decision(
    row: dict[str, Any],
    *,
    model: str,
    api_key: str,
    min_auto_confidence: float,
    rule_decision: AutoLabelDecision | None = None,
) -> AutoLabelDecision:
    payload = _validate_llm_payload(_call_openai_label(row, model=model, api_key=api_key))
    raw_json = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    flags = list(rule_decision.rule_flags if rule_decision else ())
    disagree = (
        rule_decision is not None
        and rule_decision.is_true_recommendation != "unclear"
        and rule_decision.is_true_recommendation != payload["is_true_recommendation"]
    )
    if disagree:
        flags.append("rule_llm_disagreement")
    return _decision(
        is_true_recommendation=payload["is_true_recommendation"],
        recommendation_type=payload["recommendation_type"],
        direction=payload["direction"],
        time_horizon=payload["time_horizon"],
        conviction=payload["conviction"],
        evidence_quality=payload["evidence_quality"],
        labeler_notes=payload["reason"],
        auto_label_method="hybrid_llm" if rule_decision else "llm",
        auto_label_confidence=payload["confidence"],
        auto_label_reason=payload["reason"],
        auto_label_evidence_quote=payload["evidence_quote"],
        min_auto_confidence=min_auto_confidence,
        auto_label_model=model,
        rule_flags=tuple(flags),
        llm_raw_json=raw_json,
        force_needs_review=bool(payload["needs_review"]) or disagree,
    )


def _read_csv_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    configure_csv_field_size_limit()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return rows, fieldnames


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (_clean(row.get("event_id")), _clean(row.get("video_id")), _clean(row.get("ticker")).upper())


def _has_existing_auto_label(row: dict[str, Any]) -> bool:
    return bool(_clean(row.get("auto_label_method")))


def _output_columns(input_columns: list[str]) -> list[str]:
    columns = list(input_columns)
    for column in EVENT_VALIDATION_SAMPLE_COLUMNS:
        if column not in columns:
            columns.append(column)
    for column in AUDIT_COLUMNS:
        if column not in columns:
            columns.append(column)
    return columns


def _decision_to_row(
    row: dict[str, Any],
    decision: AutoLabelDecision,
    *,
    timestamp_utc: str,
) -> dict[str, Any]:
    labeled = dict(row)
    labeled.update(
        {
            "is_true_recommendation": decision.is_true_recommendation,
            "recommendation_type": decision.recommendation_type,
            "direction": decision.direction,
            "time_horizon": decision.time_horizon,
            "conviction": decision.conviction,
            "evidence_quality": decision.evidence_quality,
            "labeler_notes": decision.labeler_notes,
            "auto_label_method": decision.auto_label_method,
            "auto_label_confidence": f"{decision.auto_label_confidence:.3f}",
            "auto_label_needs_review": str(decision.auto_label_needs_review).lower(),
            "auto_label_reason": decision.auto_label_reason,
            "auto_label_evidence_quote": decision.auto_label_evidence_quote,
            "auto_label_model": decision.auto_label_model,
            "auto_label_timestamp_utc": timestamp_utc,
            "auto_label_prompt_version": decision.auto_label_prompt_version,
            "rule_flags": ";".join(decision.rule_flags),
            "llm_raw_json": decision.llm_raw_json,
        }
    )
    return labeled


def _float_or_zero(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _boolish(value: object) -> bool:
    return _clean(value).lower() in {"1", "true", "yes", "y"}


def _needs_review_queue(row: dict[str, Any], *, min_auto_confidence: float) -> bool:
    return (
        _boolish(row.get("auto_label_needs_review"))
        or _float_or_zero(row.get("auto_label_confidence")) < min_auto_confidence
        or _clean(row.get("is_true_recommendation")).lower() == "unclear"
        or "rule_llm_disagreement" in _clean(row.get("rule_flags"))
    )


def _existing_auto_rows(output_path: Path, *, force: bool) -> dict[tuple[str, str, str], dict[str, str]]:
    if force or not output_path.exists():
        return {}
    rows, _ = _read_csv_rows(output_path)
    return {_row_key(row): row for row in rows if _has_existing_auto_label(row)}


def _label_row(
    row: dict[str, Any],
    *,
    method: str,
    min_auto_confidence: float,
    confirm_llm_run: bool,
    model: str,
    api_key: str | None,
    dry_run: bool,
) -> AutoLabelDecision:
    if method == "rules":
        return label_event_with_rules(row, min_auto_confidence=min_auto_confidence)

    if method == "llm":
        if dry_run or not confirm_llm_run:
            return _unclear_decision(
                row,
                method="llm_unconfirmed",
                reason="LLM labeling requested but --confirm-llm-run was not passed; no external API call made.",
                min_auto_confidence=min_auto_confidence,
                model=model,
                rule_flags=("llm_not_confirmed",),
            )
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required when --confirm-llm-run is passed for LLM labeling."
            )
        return _llm_decision(
            row,
            model=model,
            api_key=api_key,
            min_auto_confidence=min_auto_confidence,
        )

    rule_decision = label_event_with_rules(row, min_auto_confidence=min_auto_confidence)
    if rule_decision.is_true_recommendation != "unclear":
        return rule_decision
    if dry_run or not confirm_llm_run:
        return _unclear_decision(
            row,
            method="hybrid_unconfirmed",
            reason=(
                "Deterministic rules were ambiguous and --confirm-llm-run was not passed; "
                "no external API call made."
            ),
            min_auto_confidence=min_auto_confidence,
            model=model,
            rule_flags=tuple([*rule_decision.rule_flags, "llm_not_confirmed"]),
        )
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required when --confirm-llm-run is passed for hybrid LLM labeling."
        )
    return _llm_decision(
        row,
        model=model,
        api_key=api_key,
        min_auto_confidence=min_auto_confidence,
        rule_decision=rule_decision,
    )


def _summary_count_rows(
    rows: list[dict[str, Any]],
    *,
    section: str,
    key: str,
    total: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_clean(row.get(key)) or "unknown"].append(row)
    return [
        {
            "section": section,
            "segment": segment,
            "count": len(group_rows),
            "share": round(len(group_rows) / total, 4) if total else 0,
            "average_confidence": round(
                mean([_float_or_zero(row.get("auto_label_confidence")) for row in group_rows]),
                4,
            )
            if group_rows
            else 0,
        }
        for segment, group_rows in sorted(grouped.items())
    ]


def _confidence_bucket(confidence: float) -> str:
    if confidence < 0.50:
        return "0.00-0.49"
    if confidence < 0.75:
        return "0.50-0.74"
    if confidence < 0.90:
        return "0.75-0.89"
    return "0.90-1.00"


def _false_positive_reason(row: dict[str, Any]) -> str:
    reason = _clean(row.get("auto_label_reason"))
    if not reason:
        return _clean(row.get("recommendation_type")) or "unspecified"
    return reason.split(":", maxsplit=1)[0]


def _summary_rows(rows: list[dict[str, Any]], *, min_auto_confidence: float) -> list[dict[str, Any]]:
    total = len(rows)
    summary: list[dict[str, Any]] = [
        {
            "section": "overall",
            "segment": "total_rows",
            "count": total,
            "share": 1.0 if total else 0,
            "average_confidence": round(
                mean([_float_or_zero(row.get("auto_label_confidence")) for row in rows]),
                4,
            )
            if rows
            else 0,
        }
    ]
    for label in ["yes", "no", "unclear"]:
        count = sum(1 for row in rows if _clean(row.get("is_true_recommendation")).lower() == label)
        summary.append(
            {
                "section": "label",
                "segment": label,
                "count": count,
                "share": round(count / total, 4) if total else 0,
                "average_confidence": round(
                    mean(
                        [
                            _float_or_zero(row.get("auto_label_confidence"))
                            for row in rows
                            if _clean(row.get("is_true_recommendation")).lower() == label
                        ]
                    ),
                    4,
                )
                if count
                else 0,
            }
        )
    for method_prefix in ["rules", "hybrid_llm", "llm"]:
        count = sum(
            1
            for row in rows
            if _clean(row.get("auto_label_method")).lower() == method_prefix
            or (
                method_prefix == "rules"
                and _clean(row.get("auto_label_method")).lower().startswith("rules")
            )
        )
        summary.append(
            {
                "section": "method",
                "segment": method_prefix,
                "count": count,
                "share": round(count / total, 4) if total else 0,
                "average_confidence": 0,
            }
        )
    review_count = sum(1 for row in rows if _needs_review_queue(row, min_auto_confidence=min_auto_confidence))
    summary.append(
        {
            "section": "review",
            "segment": "needs_review",
            "count": review_count,
            "share": round(review_count / total, 4) if total else 0,
            "average_confidence": 0,
        }
    )

    bucketed: Counter[str] = Counter(
        _confidence_bucket(_float_or_zero(row.get("auto_label_confidence"))) for row in rows
    )
    for bucket, count in sorted(bucketed.items()):
        summary.append(
            {
                "section": "confidence_distribution",
                "segment": bucket,
                "count": count,
                "share": round(count / total, 4) if total else 0,
                "average_confidence": 0,
            }
        )

    for section, key in [
        ("creator", "creator"),
        ("year", "year"),
        ("recommendation_type", "recommendation_type"),
        ("direction", "direction"),
    ]:
        summary.extend(_summary_count_rows(rows, section=section, key=key, total=total))

    false_rows = [
        row for row in rows if _clean(row.get("is_true_recommendation")).lower() == "no"
    ]
    reason_counts = Counter(_false_positive_reason(row) for row in false_rows)
    for reason, count in reason_counts.most_common(10):
        summary.append(
            {
                "section": "false_positive_reason",
                "segment": reason,
                "count": count,
                "share": round(count / total, 4) if total else 0,
                "average_confidence": 0,
            }
        )
    return summary


def _example_sort_key(row: dict[str, Any]) -> float:
    return _float_or_zero(row.get("auto_label_confidence"))


def _example_line(row: dict[str, Any]) -> str:
    snippet = _evidence_quote(_clean(row.get("auto_label_evidence_quote")) or row.get("transcript_window_text"))
    return (
        f"- {row.get('event_id')} | {row.get('creator')} | {row.get('ticker')} | "
        f"confidence={_float_or_zero(row.get('auto_label_confidence')):.2f} | {snippet}"
    )


def _top_examples(
    rows: list[dict[str, Any]],
    *,
    label: str | None = None,
    review: bool | None = None,
    min_auto_confidence: float = 0.75,
    limit: int = 5,
) -> list[dict[str, Any]]:
    selected = rows
    if label is not None:
        selected = [
            row for row in selected if _clean(row.get("is_true_recommendation")).lower() == label
        ]
    if review is not None:
        selected = [
            row
            for row in selected
            if _needs_review_queue(row, min_auto_confidence=min_auto_confidence) is review
        ]
    selected = list(selected)
    selected.sort(key=_example_sort_key, reverse=review is not True)
    return selected[:limit]


def _write_auto_summary_markdown(
    path: Path,
    *,
    source_path: Path,
    output_path: Path,
    rows: list[dict[str, Any]],
    min_auto_confidence: float,
) -> Path:
    total = len(rows)
    labels = Counter(_clean(row.get("is_true_recommendation")).lower() or "blank" for row in rows)
    methods = Counter(_clean(row.get("auto_label_method")).lower() or "unknown" for row in rows)
    review_rows = [
        row for row in rows if _needs_review_queue(row, min_auto_confidence=min_auto_confidence)
    ]
    avg_confidence = (
        mean([_float_or_zero(row.get("auto_label_confidence")) for row in rows]) if rows else 0
    )
    bucket_counts = Counter(_confidence_bucket(_float_or_zero(row.get("auto_label_confidence"))) for row in rows)
    false_reasons = Counter(
        _false_positive_reason(row)
        for row in rows
        if _clean(row.get("is_true_recommendation")).lower() == "no"
    )
    lines = [
        "# Automated Event Labeling Summary",
        "",
        f"- Source file: `{source_path}`",
        f"- Auto-labeled output: `{output_path}`",
        f"- Total rows: {total}",
        f"- Rows auto-labeled yes/no/unclear: {labels.get('yes', 0)} / {labels.get('no', 0)} / {labels.get('unclear', 0)}",
        f"- Rows labeled by rules: {methods.get('rules', 0)}",
        f"- Rows labeled by LLM: {methods.get('hybrid_llm', 0) + methods.get('llm', 0)}",
        f"- Rows needing review: {len(review_rows)}",
        f"- Average confidence: {avg_confidence:.3f}",
        "",
        "## Confidence Distribution",
        "",
    ]
    lines.extend(f"- {bucket}: {count}" for bucket, count in sorted(bucket_counts.items()))
    lines.extend(
        [
            "",
            "## Top False-Positive Reasons",
            "",
        ]
    )
    if false_reasons:
        lines.extend(f"- {reason}: {count}" for reason, count in false_reasons.most_common(10))
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## High-Confidence Yes Examples",
            "",
            *(_example_line(row) for row in _top_examples(rows, label="yes", limit=5)),
            "",
            "## High-Confidence No Examples",
            "",
            *(_example_line(row) for row in _top_examples(rows, label="no", limit=5)),
            "",
            "## Examples Needing Review",
            "",
            *(
                _example_line(row)
                for row in _top_examples(
                    rows,
                    review=True,
                    min_auto_confidence=min_auto_confidence,
                    limit=5,
                )
            ),
            "",
            "## Research Note",
            "",
            "These auto labels are generated by an automated deterministic/optional-LLM workflow. "
            "The final paper should describe them transparently as automated and, when LLMs are "
            "enabled, model-assisted labels. Low-confidence and unclear rows are separated into a "
            "review queue rather than treated as validated ground truth.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _validate_method(method: str) -> str:
    normalized = _clean(method).lower()
    if normalized not in {"rules", "hybrid", "llm"}:
        raise ValueError("method must be one of: rules, hybrid, llm")
    return normalized


def auto_label_event_validation(
    *,
    input_path: Path = DEFAULT_AUTO_LABEL_INPUT_PATH,
    output_path: Path = DEFAULT_AUTO_LABEL_OUTPUT_PATH,
    review_output_path: Path = DEFAULT_REVIEW_OUTPUT_PATH,
    summary_md_path: Path = DEFAULT_AUTO_SUMMARY_MD_PATH,
    summary_csv_path: Path = DEFAULT_AUTO_SUMMARY_CSV_PATH,
    method: str = "hybrid",
    seed: int = 496,
    min_auto_confidence: float = 0.75,
    llm_model: str | None = None,
    confirm_llm_run: bool = False,
    dry_run: bool = False,
    limit: int | None = None,
    force: bool = False,
) -> AutoLabelingResult:
    method = _validate_method(method)
    if not input_path.exists():
        raise FileNotFoundError(f"Validation input not found: {input_path}")
    if not 0 <= min_auto_confidence <= 1:
        raise ValueError("min_auto_confidence must be between 0 and 1")
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1 when provided")

    ensure_data_dirs()
    rows, input_columns = _read_csv_rows(input_path)
    if limit is not None:
        rows = rows[:limit]
    rng = random.Random(seed)
    timestamp_utc = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    model = _llm_model(llm_model)
    effective_confirm_llm = confirm_llm_run and not dry_run
    if method in {"hybrid", "llm"} and effective_confirm_llm and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is required when --confirm-llm-run is passed for auto labeling."
        )
    api_key = os.getenv("OPENAI_API_KEY") if effective_confirm_llm else None
    existing_rows = _existing_auto_rows(output_path, force=force)

    labeled_rows: list[dict[str, Any]] = []
    rows_to_label = list(rows)
    rng.shuffle(rows_to_label)
    labeled_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows_to_label:
        key = _row_key(row)
        if not force and _has_existing_auto_label(row):
            labeled_by_key[key] = dict(row)
            continue
        if key in existing_rows:
            labeled_by_key[key] = dict(existing_rows[key])
            continue
        decision = _label_row(
            row,
            method=method,
            min_auto_confidence=min_auto_confidence,
            confirm_llm_run=effective_confirm_llm,
            model=model,
            api_key=api_key,
            dry_run=dry_run,
        )
        labeled_by_key[key] = _decision_to_row(row, decision, timestamp_utc=timestamp_utc)

    for row in rows:
        labeled_rows.append(labeled_by_key[_row_key(row)])

    review_rows = [
        row for row in labeled_rows if _needs_review_queue(row, min_auto_confidence=min_auto_confidence)
    ]
    summary_rows = _summary_rows(labeled_rows, min_auto_confidence=min_auto_confidence)
    output_columns = _output_columns(input_columns)

    if not dry_run:
        _write_csv(output_path, labeled_rows, output_columns)
        _write_csv(review_output_path, review_rows, output_columns)
        _write_csv(summary_csv_path, summary_rows, AUTO_LABEL_SUMMARY_COLUMNS)
        _write_auto_summary_markdown(
            summary_md_path,
            source_path=input_path,
            output_path=output_path,
            rows=labeled_rows,
            min_auto_confidence=min_auto_confidence,
        )

    labels = Counter(_clean(row.get("is_true_recommendation")).lower() for row in labeled_rows)
    methods = Counter(_clean(row.get("auto_label_method")).lower() for row in labeled_rows)
    return AutoLabelingResult(
        output_path=output_path,
        review_output_path=review_output_path,
        summary_md_path=summary_md_path,
        summary_csv_path=summary_csv_path,
        total_rows=len(labeled_rows),
        rows_labeled_yes=labels.get("yes", 0),
        rows_labeled_no=labels.get("no", 0),
        rows_labeled_unclear=labels.get("unclear", 0),
        rows_labeled_by_rules=methods.get("rules", 0),
        rows_labeled_by_llm=methods.get("hybrid_llm", 0) + methods.get("llm", 0),
        rows_needing_review=len(review_rows),
        dry_run=dry_run,
    )


def _event_rows_by_id(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows, _ = _read_csv_rows(path)
    return {_clean(row.get("event_id")): row for row in rows if _clean(row.get("event_id"))}


def _merged_event_row(row: dict[str, Any], event_rows: dict[str, dict[str, str]]) -> dict[str, Any]:
    merged = dict(event_rows.get(_clean(row.get("event_id")), {}))
    for key, value in row.items():
        if _clean(value) or key not in merged:
            merged[key] = value
    return merged


def _event_date_utc(published_at: object) -> str:
    value = _clean(published_at)
    if len(value) >= 10 and re.match(r"\d{4}-\d{2}-\d{2}", value[:10]):
        return value[:10]
    return ""


def _source_transcript_type(row: dict[str, Any]) -> str:
    existing = _clean(row.get("source_transcript_type"))
    if existing:
        return existing
    source = _clean(row.get("transcript_source")) or "unknown"
    provider = _clean(row.get("provider_name"))
    return f"{source}:{provider}" if provider else source


def _clean_event_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": _clean(row.get("event_id")),
        "video_id": _clean(row.get("video_id")),
        "creator": _clean(row.get("creator")),
        "title": _clean(row.get("title")),
        "published_at": _clean(row.get("published_at")),
        "event_date_utc": _event_date_utc(row.get("published_at")),
        "ticker": _clean(row.get("ticker")).upper(),
        "company_name": _clean(row.get("company_name")),
        "recommendation_type": _clean(row.get("recommendation_type")),
        "direction": _clean(row.get("direction")),
        "confidence": f"{_float_or_zero(row.get('auto_label_confidence')):.3f}",
        "evidence_quality": _clean(row.get("evidence_quality")),
        "source_transcript_type": _source_transcript_type(row),
        "transcript_source": _clean(row.get("transcript_source")),
        "provider_name": _clean(row.get("provider_name")),
        "video_url": _clean(row.get("video_url")),
        "transcript_window_text": _clean(row.get("transcript_window_text")),
        "context_before": _clean(row.get("context_before")),
        "context_after": _clean(row.get("context_after")),
        "auto_label_reason": _clean(row.get("auto_label_reason")),
        "auto_label_evidence_quote": _clean(row.get("auto_label_evidence_quote")),
    }


def _clean_exclusion_reasons(
    row: dict[str, Any],
    *,
    min_confidence: float,
    include_weak_evidence: bool,
    include_review_needed: bool,
) -> list[str]:
    reasons: list[str] = []
    label = _clean(row.get("is_true_recommendation")).lower()
    if label != "yes":
        reasons.append(f"is_true_recommendation={label or 'blank'}")
    direction = _clean(row.get("direction")).lower()
    if direction not in {"positive", "negative", "neutral"}:
        reasons.append(f"direction={direction or 'blank'}")
    confidence = _float_or_zero(row.get("auto_label_confidence"))
    if confidence < min_confidence:
        reasons.append(f"confidence_below_{min_confidence:.2f}")
    evidence_quality = _clean(row.get("evidence_quality")).lower()
    if evidence_quality not in {"strong", "medium"} and not include_weak_evidence:
        reasons.append(f"evidence_quality={evidence_quality or 'blank'}")
    if _boolish(row.get("auto_label_needs_review")) and not include_review_needed:
        reasons.append("needs_review")
    return reasons


def _write_clean_summary(
    path: Path,
    *,
    source_path: Path,
    output_path: Path,
    exclusions_path: Path,
    included: list[dict[str, Any]],
    exclusions: list[dict[str, Any]],
    min_confidence: float,
    include_weak_evidence: bool,
    include_review_needed: bool,
) -> Path:
    reason_counts = Counter(
        reason
        for row in exclusions
        for reason in _clean(row.get("clean_event_exclusion_reason")).split(";")
        if reason
    )
    lines = [
        "# Clean Auto-Labeled Events Summary",
        "",
        f"- Source file: `{source_path}`",
        f"- Clean events output: `{output_path}`",
        f"- Exclusions output: `{exclusions_path}`",
        f"- Included rows: {len(included)}",
        f"- Excluded rows: {len(exclusions)}",
        f"- Minimum confidence: {min_confidence:.2f}",
        f"- Include weak evidence: {include_weak_evidence}",
        f"- Include review-needed rows: {include_review_needed}",
        "",
        "## Exclusion Reasons",
        "",
    ]
    if reason_counts:
        lines.extend(f"- {reason}: {count}" for reason, count in reason_counts.most_common())
    else:
        lines.append("- None.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_clean_auto_labeled_events(
    *,
    input_path: Path = DEFAULT_AUTO_LABEL_OUTPUT_PATH,
    events_input_path: Path = DEFAULT_TRANSCRIPT_EVENTS_EXPORT_PATH,
    output_path: Path = DEFAULT_CLEAN_EVENTS_OUTPUT_PATH,
    exclusions_output_path: Path = DEFAULT_CLEAN_EVENTS_EXCLUSIONS_PATH,
    summary_md_path: Path = DEFAULT_CLEAN_EVENTS_SUMMARY_PATH,
    min_confidence: float = 0.75,
    include_weak_evidence: bool = False,
    include_review_needed: bool = False,
    dry_run: bool = False,
) -> CleanAutoLabeledEventsResult:
    if not input_path.exists():
        raise FileNotFoundError(f"Auto-labeled validation input not found: {input_path}")
    if not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1")

    rows, _ = _read_csv_rows(input_path)
    event_rows = _event_rows_by_id(events_input_path)
    included: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for row in rows:
        merged = _merged_event_row(row, event_rows)
        projection = _clean_event_projection(merged)
        reasons = _clean_exclusion_reasons(
            merged,
            min_confidence=min_confidence,
            include_weak_evidence=include_weak_evidence,
            include_review_needed=include_review_needed,
        )
        if reasons:
            exclusions.append({**projection, "clean_event_exclusion_reason": ";".join(reasons)})
        else:
            included.append(projection)

    if not dry_run:
        _write_csv(output_path, included, CLEAN_EVENT_COLUMNS)
        _write_csv(exclusions_output_path, exclusions, CLEAN_EXCLUSION_COLUMNS)
        _write_clean_summary(
            summary_md_path,
            source_path=input_path,
            output_path=output_path,
            exclusions_path=exclusions_output_path,
            included=included,
            exclusions=exclusions,
            min_confidence=min_confidence,
            include_weak_evidence=include_weak_evidence,
            include_review_needed=include_review_needed,
        )

    return CleanAutoLabeledEventsResult(
        output_path=output_path,
        exclusions_output_path=exclusions_output_path,
        summary_md_path=summary_md_path,
        included_rows=len(included),
        excluded_rows=len(exclusions),
        dry_run=dry_run,
    )
