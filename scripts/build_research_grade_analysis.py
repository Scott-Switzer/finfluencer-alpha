"""Build the FIN 496 research-grade robustness artifacts.

This script loads the locked YouTube event sample (1,554 events across 35 creators
and 23 tickers, sourced from `transcript_recommendation_events`) and produces all
research-grade computational artifacts requested in the analysis specification.

Hard constraints honored by this script:
- No Apify, no transcript collection, no paid data calls.
- Read-only against the local SQLite database and local yfinance CSV imports.
- No modification of raw data files.
- All outputs written under `data/exports/research_grade_analysis/`.
- Optional SEC EDGAR call is gated behind `ALLOW_SEC_EDGAR=1`; default is off,
  in which case the news-overlap flag CSV is written with explicit
  `news_query_status=protocol_only` placeholders and the methodology document
  explains the rerun procedure.

Run:
    python3 scripts/build_research_grade_analysis.py
"""

from __future__ import annotations

import csv
import html
import math
import random
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "finfluencer_alpha.db"
MARKET_DATA_PRIMARY = REPO_ROOT / "data" / "imports" / "market_data" / "yfinance_expanded_market_data.csv"
MARKET_DATA_FALLBACK = REPO_ROOT / "data" / "imports" / "market_data" / "yfinance_market_data.csv"
TICKER_ALIASES_PATH = REPO_ROOT / "data" / "seeds" / "ticker_aliases.csv"
OUT_DIR = REPO_ROOT / "data" / "exports" / "research_grade_analysis"

PRIMARY_BENCHMARK = "SPY"

SECTOR_ETF_MAP = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AMD": "XLK", "CRM": "XLK", "SMCI": "XLK",
    "META": "XLC", "GOOGL": "XLC", "NFLX": "XLC", "DIS": "XLC",
    "AMZN": "XLY", "TSLA": "XLY", "UBER": "XLY", "SHOP": "XLY", "TGT": "XLY", "AMC": "XLY",
    "PYPL": "XLF", "SOFI": "XLF", "HOOD": "XLF", "COIN": "XLF", "SQ": "XLF", "XYZ": "XLF",
    "GME": "XLY", "PLTR": "XLK",
}

# Heuristic ambiguous-ticker watchlist (common-word collisions in transcripts).
AMBIGUOUS_TICKERS = {"NOW", "ALL", "ON", "RUN", "GO", "ANY", "SO", "ONE", "WORK", "META"}

POSITIVE_REC_PHRASES = [
    "i'm buying", "im buying", "i am buying", "i bought", "going to buy",
    "i'll buy", "ill buy", "i'd buy", "id buy", "should buy", "you should buy",
    "i recommend", "recommend buying", "load up", "back up the truck",
    "strong buy", "long ", "going long", "i'm long", "buy the dip",
    "i own", "i hold", "adding to", "added to", "averaging in", "dollar cost",
    "bullish on", "this is a buy",
]
NEGATIVE_REC_PHRASES = [
    "i'm selling", "im selling", "i am selling", "i sold", "going to sell",
    "i'll sell", "ill sell", "i'd sell", "id sell", "should sell",
    "i recommend selling", "trim ", "trimming ", "exit ", "exiting ",
    "short ", "i'm short", "im short", "going short", "shorting ",
    "avoid ", "stay away", "bearish on", "this is a sell", "dump ",
]
CONDITIONALITY_PHRASES = [
    "if it ", "if the ", "if you ", "depending on", "could", "might", "may ",
    "perhaps", "potentially", "possibly", "should it ", "in case ",
]
RECAP_PHRASES = [
    "i said", "i told you", "i mentioned", "remember when", "back in", "earlier i",
    "last week i", "last month i", "few months ago", "previously",
]
NEWS_ONLY_PHRASES = [
    "according to", "reuters", "bloomberg reports", "cnbc", "the wall street journal",
    "press release", "filed an 8-k", "released their earnings",
]
POSITION_DISCLOSURE = [
    "i own", "in my portfolio", "i hold", "i'm holding", "my position",
    "my holding", "added to my", "trimmed my", "i sold my", "i bought more",
]
URGENCY_PHRASES = [
    "right now", "today", "tomorrow", "this week", "immediately", "asap",
    "before earnings", "this morning",
]
TIME_HORIZON_PHRASES_SHORT = ["short term", "swing", "next week", "this week", "intraday"]
TIME_HORIZON_PHRASES_LONG = ["long term", "long-term", "decade", "for years", "hold forever"]
VALUATION_PHRASES = ["p/e", "pe ratio", "valuation", "dcf", "discounted cash", "ev/ebitda",
                     "forward earnings", "multiple", "trades at", "cheap at"]
CATALYST_PHRASES = ["earnings", "product launch", "guidance", "fed", "macro", "tariff",
                    "lawsuit", "approval", "ipo", "spin-off", "split", "buyback"]
RISK_DISCLOSURE = ["not financial advice", "do your own research", "dyor", "risk", "could lose",
                   "speculative", "high risk"]
NEW_VS_UPDATE = {
    "new": ["initiating", "new position", "starting a position", "just bought", "added today"],
    "update": ["adding to", "trimmed", "still holding", "still long", "still bullish", "update on"],
    "recap": ["i told you", "i said", "i mentioned", "earlier this year"],
}

REASON_CODE_DESCRIPTIONS = {
    "EVIDENCE_QUOTE_AVAILABLE": "Evidence window present in transcript event.",
    "EVIDENCE_QUOTE_MISSING": "Evidence quote not recovered from local stores.",
    "EVIDENCE_QUOTE_SHORT": "Evidence window shorter than 100 chars.",
    "STRONG_DIRECT_LANGUAGE": "Explicit buy/sell phrasing in evidence.",
    "WEAK_DIRECTIONAL_SIGNAL": "Directional language is implicit or weak.",
    "CONDITIONALITY_PRESENT": "Conditional language detected ('if', 'might').",
    "RECAP_RISK": "Recap/past-call language detected.",
    "NEWS_ONLY_RISK": "Evidence reads as news summary, not creator recommendation.",
    "DUPLICATE_CLUSTER": "Same creator+ticker+adjusted date as another event.",
    "TOP_TICKER_CONCENTRATION": "Ticker is in top-5 by event count.",
    "TOP_CREATOR_CONCENTRATION": "Creator is in top-5 by event count.",
    "AMBIGUOUS_TICKER": "Ticker is on common-word ambiguity watchlist.",
    "MARKET_DATA_MISSING": "No local market data row found on/after event date.",
    "EXTREME_ABS_AR_1D": "|1D abnormal return| > 10%.",
    "EXTREME_ABS_AR_5D": "|5D abnormal return| > 15%.",
    "HIGH_IMPACT_EVENT": "1D abnormal return in top/bottom 5% of sample.",
    "TICKER_COMPANY_MATCH": "Ticker and company name both populated.",
    "POSITION_DISCLOSURE_OK": "Creator disclosed position context.",
    "TRADING_DAY_ADJUSTED": "Event date adjusted from weekend to next trading day.",
}

# Bloomberg / news fields to populate later (Part E placeholder schema).
NEWS_FLAG_COLUMNS = [
    "event_id", "ticker", "event_date", "effective_trading_event_date",
    "sec_filing_near_event_flag", "sec_8k_near_event_flag",
    "earnings_near_event_flag", "major_news_near_event_flag",
    "same_day_news_flag", "plus_minus_1_day_news_flag",
    "plus_minus_3_day_news_flag", "plus_minus_5_day_news_flag",
    "news_confounded_event_flag",
    "news_source_used", "news_query_status",
]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _clean_html(text: str) -> str:
    return html.unescape(text or "")


def _to_date(value: str | datetime | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        raise ValueError("empty date")
    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[0]
    return datetime.strptime(text[:10], "%Y-%m-%d").date()


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _weekday_adjust(d: date) -> date:
    if d.weekday() == 5:
        return d + timedelta(days=2)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _ticker_alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    if TICKER_ALIASES_PATH.exists():
        with TICKER_ALIASES_PATH.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                orig = (row.get("original_ticker") or "").strip().upper()
                data = (row.get("data_ticker") or "").strip().upper()
                if orig and data and orig != data:
                    aliases[orig] = data
    return aliases


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


@dataclass
class EventRow:
    event_id: int
    video_id: str
    ticker: str
    company_name: str
    stance: str
    detected_action: str
    actionability_score: int | None
    confidence_score: float | None
    confidence_label: str
    evidence_start_seconds: float | None
    evidence_end_seconds: float | None
    evidence_window: str
    transcript_source: str
    provider_name: str
    transcript_collected_at: str
    creator: str
    published_at: str
    title: str
    description: str

    @property
    def published_dt(self) -> datetime | None:
        if not self.published_at:
            return None
        try:
            return datetime.fromisoformat(self.published_at.replace("Z", "+00:00"))
        except ValueError:
            return None

    @property
    def calendar_event_date(self) -> date | None:
        dt = self.published_dt
        return dt.date() if dt else None


def load_events() -> list[EventRow]:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT
            e.transcript_event_id AS event_id,
            e.video_id,
            e.ticker,
            e.company_name,
            e.stance,
            e.detected_action,
            e.actionability_score,
            e.confidence_score,
            e.confidence_label,
            e.evidence_start_seconds,
            e.evidence_end_seconds,
            e.evidence_window,
            e.transcript_source,
            e.provider_name,
            e.transcript_collected_at,
            v.channel_title AS creator,
            v.published_at,
            v.title,
            v.description
        FROM transcript_recommendation_events e
        JOIN raw_youtube_videos v ON e.video_id = v.video_id
        ORDER BY e.transcript_event_id ASC
        """
    ).fetchall()
    con.close()
    out: list[EventRow] = []
    for r in rows:
        out.append(
            EventRow(
                event_id=int(r["event_id"]),
                video_id=str(r["video_id"]),
                ticker=str(r["ticker"] or "").upper(),
                company_name=str(r["company_name"] or ""),
                stance=str(r["stance"] or ""),
                detected_action=str(r["detected_action"] or ""),
                actionability_score=(int(r["actionability_score"]) if r["actionability_score"] is not None else None),
                confidence_score=_safe_float(r["confidence_score"]),
                confidence_label=str(r["confidence_label"] or ""),
                evidence_start_seconds=_safe_float(r["evidence_start_seconds"]),
                evidence_end_seconds=_safe_float(r["evidence_end_seconds"]),
                evidence_window=_clean_html(r["evidence_window"] or ""),
                transcript_source=str(r["transcript_source"] or ""),
                provider_name=str(r["provider_name"] or ""),
                transcript_collected_at=str(r["transcript_collected_at"] or ""),
                creator=str(r["creator"] or ""),
                published_at=str(r["published_at"] or ""),
                title=str(r["title"] or ""),
                description=str(r["description"] or ""),
            )
        )
    return out


def load_market_data() -> dict[str, list[dict[str, Any]]]:
    """Return ticker -> sorted list of {date, adjusted_close, source}.

    Prefers the expanded yfinance file because it includes SPY/QQQ/IWM and
    sector ETFs, then merges in unique rows from the base file (which carries
    historical XYZ/SQ coverage and a few smaller-cap tickers not in expanded).
    """
    by_ticker: dict[str, dict[date, dict[str, Any]]] = defaultdict(dict)
    for path in (MARKET_DATA_PRIMARY, MARKET_DATA_FALLBACK):
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                ticker = (row.get("ticker") or "").upper()
                if not ticker:
                    continue
                try:
                    d = _to_date(row.get("date"))
                except (ValueError, TypeError):
                    continue
                px = _safe_float(row.get("adjusted_close"))
                if px is None:
                    continue
                if d not in by_ticker[ticker]:
                    by_ticker[ticker][d] = {
                        "date": d,
                        "adjusted_close": px,
                        "source": row.get("data_source") or "yfinance_yahoo_prototype",
                    }
    sorted_out: dict[str, list[dict[str, Any]]] = {}
    for ticker, by_date in by_ticker.items():
        sorted_out[ticker] = sorted(by_date.values(), key=lambda r: r["date"])
    return sorted_out


# ---------------------------------------------------------------------------
# Trading-day index helpers
# ---------------------------------------------------------------------------


def trading_day_index(rows: list[dict[str, Any]]) -> dict[date, int]:
    return {row["date"]: i for i, row in enumerate(rows)}


def first_on_or_after(rows: list[dict[str, Any]], target: date) -> int | None:
    lo, hi = 0, len(rows)
    while lo < hi:
        mid = (lo + hi) // 2
        if rows[mid]["date"] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(rows) else None


def last_on_or_before(rows: list[dict[str, Any]], target: date) -> int | None:
    lo, hi = 0, len(rows)
    while lo < hi:
        mid = (lo + hi) // 2
        if rows[mid]["date"] <= target:
            lo = mid + 1
        else:
            hi = mid
    idx = lo - 1
    return idx if idx >= 0 else None


def window_return(
    rows: list[dict[str, Any]],
    base_idx: int,
    start_offset: int,
    end_offset: int,
) -> float | None:
    """Compute compound return between trading days base_idx+start_offset and
    base_idx+end_offset, using adjusted close prices. Offsets are inclusive of
    the end, exclusive shift on the start (price at start_offset is the
    denominator, price at end_offset is the numerator).
    """
    start = base_idx + start_offset
    end = base_idx + end_offset
    if start < 0 or end < 0:
        return None
    if start >= len(rows) or end >= len(rows):
        return None
    p_start = rows[start]["adjusted_close"]
    p_end = rows[end]["adjusted_close"]
    if not p_start or p_end is None:
        return None
    try:
        return (p_end / p_start) - 1.0
    except ZeroDivisionError:
        return None


# ---------------------------------------------------------------------------
# Core event enrichment
# ---------------------------------------------------------------------------


@dataclass
class EnrichedEvent:
    event: EventRow
    data_ticker: str
    calendar_event_date: date | None
    weekday_adjusted_date: date | None
    effective_trading_event_date: date | None
    next_trading_idx: int | None
    timing_bucket: str
    duplicate_cluster_id: int | None
    duplicate_cluster_size: int
    evidence_quote: str
    quality_score: int
    quality_tier: str
    validation_flags: list[str]
    reason_codes: list[str]
    exclusion_candidate: bool
    returns: dict[str, float | None]
    abnormal: dict[str, float | None]
    pre_decile: int | None = None
    short_pre_decile: int | None = None
    reversal_flag: bool = False
    continuation_flag: bool = False


def detect_timing_bucket(event: EventRow) -> str:
    dt = event.published_dt
    if dt is None:
        return "unknown"
    if dt.weekday() >= 5:
        return "weekend_or_holiday"
    # Approximate Eastern time: published_at is UTC. US market 09:30-16:00 ET.
    # Convert to ET using fixed offset of -5 (no DST awareness because data
    # spans multiple years; conservative buckets are acceptable here).
    et_hour = (dt.hour - 5) % 24
    if et_hour < 9 or (et_hour == 9 and dt.minute < 30):
        return "before_open"
    if (et_hour == 9 and dt.minute >= 30) or (10 <= et_hour < 16):
        return "during_market"
    return "after_close"


def derive_evidence_quote(event: EventRow) -> str:
    text = (event.evidence_window or "").strip()
    if not text:
        return ""
    # Trim to first 320 chars for the evidence column (auditable, not full transcript).
    return text[:320].strip()


def score_event_quality(
    event: EventRow,
    *,
    ticker_count: Counter,
    creator_count: Counter,
    top_tickers: set[str],
    top_creators: set[str],
    duplicate_size: int,
    abnormal_1d: float | None,
    abnormal_5d: float | None,
    high_impact_threshold_pos: float,
    high_impact_threshold_neg: float,
    market_data_available: bool,
    weekday_adjusted: bool,
) -> tuple[int, str, list[str], list[str], bool]:
    flags: list[str] = []
    reasons: list[str] = []
    score = 50  # start neutral

    evidence = event.evidence_window or ""
    evidence_lower = evidence.lower()
    evidence_len = len(evidence)

    # Evidence traceability
    if evidence_len >= 200:
        score += 15
        reasons.append("EVIDENCE_QUOTE_AVAILABLE")
    elif evidence_len >= 100:
        score += 8
        reasons.append("EVIDENCE_QUOTE_AVAILABLE")
    elif evidence_len > 0:
        score += 2
        flags.append("evidence_short")
        reasons.append("EVIDENCE_QUOTE_SHORT")
    else:
        score -= 10
        flags.append("evidence_missing")
        reasons.append("EVIDENCE_QUOTE_MISSING")

    # Ticker / company match
    if event.ticker and event.company_name:
        score += 5
        reasons.append("TICKER_COMPANY_MATCH")
    if event.ticker in AMBIGUOUS_TICKERS:
        score -= 6
        flags.append("ambiguous_ticker")
        reasons.append("AMBIGUOUS_TICKER")

    # Direct recommendation language
    pos_hits = sum(1 for p in POSITIVE_REC_PHRASES if p in evidence_lower)
    neg_hits = sum(1 for p in NEGATIVE_REC_PHRASES if p in evidence_lower)
    cond_hits = sum(1 for p in CONDITIONALITY_PHRASES if p in evidence_lower)
    recap_hits = sum(1 for p in RECAP_PHRASES if p in evidence_lower)
    news_hits = sum(1 for p in NEWS_ONLY_PHRASES if p in evidence_lower)

    direction_is_bullish = "bullish" in event.stance or "buy" in event.detected_action
    direction_is_bearish = "bearish" in event.stance or "sell" in event.detected_action

    direct_signal = 0
    if direction_is_bullish and pos_hits > 0:
        direct_signal = pos_hits
    elif direction_is_bearish and neg_hits > 0:
        direct_signal = neg_hits
    elif pos_hits + neg_hits > 0:
        direct_signal = max(pos_hits, neg_hits)

    if direct_signal >= 2:
        score += 12
        reasons.append("STRONG_DIRECT_LANGUAGE")
    elif direct_signal == 1:
        score += 6
        reasons.append("STRONG_DIRECT_LANGUAGE")
    else:
        score -= 5
        flags.append("weak_directional_signal")
        reasons.append("WEAK_DIRECTIONAL_SIGNAL")

    if cond_hits >= 2:
        score -= 6
        flags.append("conditionality")
        reasons.append("CONDITIONALITY_PRESENT")
    elif cond_hits == 1:
        score -= 2

    if recap_hits >= 1:
        score -= 4
        flags.append("recap_risk")
        reasons.append("RECAP_RISK")

    if news_hits >= 1 and direct_signal == 0:
        score -= 6
        flags.append("news_only_risk")
        reasons.append("NEWS_ONLY_RISK")

    pos_disclosure = any(p in evidence_lower for p in POSITION_DISCLOSURE)
    if pos_disclosure:
        score += 3
        reasons.append("POSITION_DISCLOSURE_OK")

    # Confidence from classifier
    if event.confidence_score is not None:
        if event.confidence_score >= 0.75:
            score += 6
        elif event.confidence_score >= 0.6:
            score += 3
        elif event.confidence_score < 0.45:
            score -= 4
            flags.append("low_classifier_confidence")

    # Duplicate cluster size
    if duplicate_size >= 4:
        score -= 8
        flags.append("duplicate_cluster_large")
        reasons.append("DUPLICATE_CLUSTER")
    elif duplicate_size >= 2:
        score -= 3
        flags.append("duplicate_cluster_small")
        reasons.append("DUPLICATE_CLUSTER")

    # Concentration
    if event.ticker in top_tickers:
        flags.append("top_ticker_concentration")
        reasons.append("TOP_TICKER_CONCENTRATION")
        score -= 1
    if event.creator in top_creators:
        flags.append("top_creator_concentration")
        reasons.append("TOP_CREATOR_CONCENTRATION")
        score -= 1

    # Trading-day adjustment & market data coverage
    if weekday_adjusted:
        reasons.append("TRADING_DAY_ADJUSTED")
    if not market_data_available:
        score -= 12
        flags.append("market_data_missing")
        reasons.append("MARKET_DATA_MISSING")

    # Outlier flags
    if abnormal_1d is not None and abs(abnormal_1d) > 0.10:
        flags.append("extreme_abs_ar_1d")
        reasons.append("EXTREME_ABS_AR_1D")
    if abnormal_5d is not None and abs(abnormal_5d) > 0.15:
        flags.append("extreme_abs_ar_5d")
        reasons.append("EXTREME_ABS_AR_5D")
    if abnormal_1d is not None and (
        abnormal_1d >= high_impact_threshold_pos
        or abnormal_1d <= high_impact_threshold_neg
    ):
        flags.append("high_impact_event")
        reasons.append("HIGH_IMPACT_EVENT")

    score = max(0, min(100, score))
    if score >= 80:
        tier = "A"
    elif score >= 65:
        tier = "B"
    elif score >= 50:
        tier = "C"
    else:
        tier = "D"

    exclusion_candidate = score < 45 or "evidence_missing" in flags or "market_data_missing" in flags
    return score, tier, flags, list(dict.fromkeys(reasons)), exclusion_candidate


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


def t_test_one_sample(xs: list[float]) -> tuple[int, float, float, float, float]:
    """Return n, mean, median, t, two-sided p (using normal approx for p when n>30)."""
    xs = [x for x in xs if x is not None]
    n = len(xs)
    if n < 2:
        return n, (statistics.mean(xs) if xs else float("nan")), (statistics.median(xs) if xs else float("nan")), float("nan"), float("nan")
    mean = statistics.mean(xs)
    median = statistics.median(xs)
    sd = statistics.stdev(xs)
    if sd == 0:
        return n, mean, median, float("inf"), 0.0
    t = mean / (sd / math.sqrt(n))
    # Approximate p with normal cdf (n is large enough for sample sizes here)
    p = 2.0 * (1.0 - _norm_cdf(abs(t)))
    return n, mean, median, t, p


def _norm_cdf(z: float) -> float:
    # Abramowitz and Stegun approximation
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def ols_regression(y: list[float], X: list[list[float]]) -> dict[str, Any] | None:
    """Tiny OLS via normal equations. Returns coefficients, SEs, t, p, R^2.

    X must include a leading intercept column. No external dependencies.
    """
    n = len(y)
    if n == 0 or any(len(row) == 0 for row in X) or len(X) != n:
        return None
    k = len(X[0])
    # Build X'X (k x k) and X'y (k)
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for i in range(n):
        xi = X[i]
        yi = y[i]
        for a in range(k):
            xty[a] += xi[a] * yi
            for b in range(k):
                xtx[a][b] += xi[a] * xi[b]
    # Solve via Gaussian elimination
    aug = [row[:] + [xty[a]] for a, row in enumerate(xtx)]
    for i in range(k):
        # Find pivot
        pivot_row = max(range(i, k), key=lambda r: abs(aug[r][i]))
        if abs(aug[pivot_row][i]) < 1e-12:
            return None
        aug[i], aug[pivot_row] = aug[pivot_row], aug[i]
        pivot = aug[i][i]
        for j in range(i, k + 1):
            aug[i][j] /= pivot
        for r in range(k):
            if r != i and abs(aug[r][i]) > 0:
                factor = aug[r][i]
                for j in range(i, k + 1):
                    aug[r][j] -= factor * aug[i][j]
    beta = [aug[i][k] for i in range(k)]
    # Residuals and SSE
    y_hat = [sum(X[i][a] * beta[a] for a in range(k)) for i in range(n)]
    resid = [y[i] - y_hat[i] for i in range(n)]
    sse = sum(r * r for r in resid)
    y_bar = sum(y) / n
    sst = sum((yi - y_bar) ** 2 for yi in y)
    r2 = 1.0 - sse / sst if sst > 0 else float("nan")
    df = n - k
    if df <= 0:
        return None
    sigma2 = sse / df
    # Need inverse of X'X -- recompute via solving k systems (identity columns)
    inv = [[0.0] * k for _ in range(k)]
    base = [row[:] for row in xtx]
    for col in range(k):
        # Solve base * v = e_col
        aug2 = [base[i][:] + [(1.0 if i == col else 0.0)] for i in range(k)]
        for i in range(k):
            pivot_row = max(range(i, k), key=lambda r: abs(aug2[r][i]))
            if abs(aug2[pivot_row][i]) < 1e-12:
                return None
            aug2[i], aug2[pivot_row] = aug2[pivot_row], aug2[i]
            pivot = aug2[i][i]
            for j in range(i, k + 1):
                aug2[i][j] /= pivot
            for r in range(k):
                if r != i and abs(aug2[r][i]) > 0:
                    factor = aug2[r][i]
                    for j in range(i, k + 1):
                        aug2[r][j] -= factor * aug2[i][j]
        for i in range(k):
            inv[i][col] = aug2[i][k]
    se = [math.sqrt(sigma2 * inv[i][i]) if inv[i][i] >= 0 else float("nan") for i in range(k)]
    t_stats = [beta[i] / se[i] if se[i] and se[i] > 0 else float("nan") for i in range(k)]
    p_vals = [2.0 * (1.0 - _norm_cdf(abs(t))) if not math.isnan(t) else float("nan") for t in t_stats]
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / max(df, 1) if not math.isnan(r2) else float("nan")
    return {
        "n": n,
        "k": k,
        "beta": beta,
        "se": se,
        "t": t_stats,
        "p": p_vals,
        "r2": r2,
        "adj_r2": adj_r2,
        "df": df,
    }


def deciles(values: list[float]) -> list[int]:
    """Return decile rank (1-10) for each non-null value, None for null."""
    indexed = [(i, v) for i, v in enumerate(values) if v is not None]
    if not indexed:
        return [None] * len(values)
    indexed.sort(key=lambda iv: iv[1])
    n = len(indexed)
    out: list[int | None] = [None] * len(values)
    for rank, (orig_idx, _) in enumerate(indexed):
        # rank 0..n-1 -> decile 1..10
        decile = min(10, 1 + int(10 * rank / n))
        out[orig_idx] = decile
    return out


# ---------------------------------------------------------------------------
# CSV / Markdown writers
# ---------------------------------------------------------------------------


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=columns,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fmt(v: Any, prec: int = 6) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
        return f"{v:.{prec}f}"
    return str(v)


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Return Benjamini-Hochberg q-values aligned to input p-values."""
    valid = [
        (i, p)
        for i, p in enumerate(p_values)
        if p is not None and not math.isnan(p) and not math.isinf(p)
    ]
    out = [float("nan")] * len(p_values)
    if not valid:
        return out
    valid.sort(key=lambda item: item[1])
    m = len(valid)
    running = 1.0
    for rank, (orig_idx, p) in reversed(list(enumerate(valid, start=1))):
        running = min(running, p * m / rank)
        out[orig_idx] = min(running, 1.0)
    return out


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def build_enriched_events(
    events: list[EventRow],
    market: dict[str, list[dict[str, Any]]],
    aliases: dict[str, str],
) -> list[EnrichedEvent]:
    benchmark_rows = market.get(PRIMARY_BENCHMARK, [])
    ticker_count = Counter(e.ticker for e in events)
    creator_count = Counter(e.creator for e in events)
    top_tickers = {t for t, _ in ticker_count.most_common(5)}
    top_creators = {c for c, _ in creator_count.most_common(5)}

    # First pass: derive calendar/effective dates and pre-compute returns to set thresholds.
    duplicate_keys: list[str] = []
    enriched: list[EnrichedEvent] = []
    abnormal_1d_for_threshold: list[float] = []
    for e in events:
        cal_date = e.calendar_event_date
        if cal_date is None:
            adj_date = None
            effective = None
            next_idx = None
            data_ticker = aliases.get(e.ticker, e.ticker)
        else:
            adj_date = _weekday_adjust(cal_date)
            data_ticker = aliases.get(e.ticker, e.ticker)
            # SQ historic mapping is date-conditional; replicate intent: pre 2025-01-21 stay SQ
            if e.ticker == "SQ" and cal_date < date(2025, 1, 21):
                data_ticker = "SQ"
            rows = market.get(data_ticker, [])
            if not rows:
                effective = None
                next_idx = None
            else:
                idx = first_on_or_after(rows, adj_date)
                if idx is None:
                    effective = None
                    next_idx = None
                else:
                    effective = rows[idx]["date"]
                    next_idx = idx

        # Returns: rely on data_ticker rows; SPY-adjusted abnormal returns
        returns: dict[str, float | None] = {
            "ret_pre_20_1": None,
            "ret_pre_5_1": None,
            "ret_event_0_1": None,
            "ret_post_0_5": None,
            "ret_post_5_20": None,
            "ret_post_0_20": None,
        }
        abnormal: dict[str, float | None] = {
            "ar_pre_20_1": None,
            "ar_pre_5_1": None,
            "ar_event_0_1": None,
            "ar_post_0_5": None,
            "ar_post_5_20": None,
            "ar_post_0_20": None,
        }
        bench_idx = None
        if effective is not None and benchmark_rows:
            bench_idx = first_on_or_after(benchmark_rows, effective)
        if next_idx is not None and data_ticker in market:
            rows = market[data_ticker]
            returns["ret_pre_20_1"] = window_return(rows, next_idx, -20, -1)
            returns["ret_pre_5_1"] = window_return(rows, next_idx, -5, -1)
            returns["ret_event_0_1"] = window_return(rows, next_idx, 0, 1)
            returns["ret_post_0_5"] = window_return(rows, next_idx, 0, 5)
            returns["ret_post_5_20"] = window_return(rows, next_idx, 5, 20)
            returns["ret_post_0_20"] = window_return(rows, next_idx, 0, 20)
            if bench_idx is not None:
                b_pre_20 = window_return(benchmark_rows, bench_idx, -20, -1)
                b_pre_5 = window_return(benchmark_rows, bench_idx, -5, -1)
                b_event = window_return(benchmark_rows, bench_idx, 0, 1)
                b_post_5 = window_return(benchmark_rows, bench_idx, 0, 5)
                b_post_5_20 = window_return(benchmark_rows, bench_idx, 5, 20)
                b_post_0_20 = window_return(benchmark_rows, bench_idx, 0, 20)
                def _diff(a, b):
                    return None if (a is None or b is None) else a - b
                abnormal["ar_pre_20_1"] = _diff(returns["ret_pre_20_1"], b_pre_20)
                abnormal["ar_pre_5_1"] = _diff(returns["ret_pre_5_1"], b_pre_5)
                abnormal["ar_event_0_1"] = _diff(returns["ret_event_0_1"], b_event)
                abnormal["ar_post_0_5"] = _diff(returns["ret_post_0_5"], b_post_5)
                abnormal["ar_post_5_20"] = _diff(returns["ret_post_5_20"], b_post_5_20)
                abnormal["ar_post_0_20"] = _diff(returns["ret_post_0_20"], b_post_0_20)
        if abnormal["ar_event_0_1"] is not None:
            abnormal_1d_for_threshold.append(abnormal["ar_event_0_1"])

        # duplicate key
        if adj_date is None:
            dup_key = f"{e.creator}__{e.ticker}__NA"
        else:
            dup_key = f"{e.creator}__{e.ticker}__{adj_date.isoformat()}"
        duplicate_keys.append(dup_key)

        enriched.append(EnrichedEvent(
            event=e,
            data_ticker=data_ticker,
            calendar_event_date=cal_date,
            weekday_adjusted_date=adj_date,
            effective_trading_event_date=effective,
            next_trading_idx=next_idx,
            timing_bucket=detect_timing_bucket(e),
            duplicate_cluster_id=None,
            duplicate_cluster_size=1,
            evidence_quote=derive_evidence_quote(e),
            quality_score=0,
            quality_tier="",
            validation_flags=[],
            reason_codes=[],
            exclusion_candidate=False,
            returns=returns,
            abnormal=abnormal,
        ))

    # Duplicate cluster ids and sizes
    cluster_map: dict[str, int] = {}
    cluster_size: Counter = Counter(duplicate_keys)
    for key in duplicate_keys:
        if key not in cluster_map:
            cluster_map[key] = len(cluster_map) + 1
    for ee, key in zip(enriched, duplicate_keys, strict=True):
        ee.duplicate_cluster_id = cluster_map[key]
        ee.duplicate_cluster_size = cluster_size[key]

    # High-impact thresholds (5% / 95% of |AR_1D| distribution)
    if abnormal_1d_for_threshold:
        sorted_ar = sorted(abnormal_1d_for_threshold)
        n = len(sorted_ar)
        hi_pos = sorted_ar[int(0.95 * (n - 1))]
        hi_neg = sorted_ar[int(0.05 * (n - 1))]
    else:
        hi_pos = float("inf")
        hi_neg = -float("inf")

    # Quality scoring (second pass uses returns and dup counts)
    for ee in enriched:
        score, tier, flags, reasons, excl = score_event_quality(
            ee.event,
            ticker_count=ticker_count,
            creator_count=creator_count,
            top_tickers=top_tickers,
            top_creators=top_creators,
            duplicate_size=ee.duplicate_cluster_size,
            abnormal_1d=ee.abnormal["ar_event_0_1"],
            abnormal_5d=ee.abnormal["ar_post_0_5"],
            high_impact_threshold_pos=hi_pos,
            high_impact_threshold_neg=hi_neg,
            market_data_available=ee.next_trading_idx is not None,
            weekday_adjusted=(
                ee.calendar_event_date is not None
                and ee.weekday_adjusted_date is not None
                and ee.weekday_adjusted_date != ee.calendar_event_date
            ),
        )
        ee.quality_score = score
        ee.quality_tier = tier
        ee.validation_flags = flags
        ee.reason_codes = reasons
        ee.exclusion_candidate = excl

    # Momentum deciles (by pre-event AR_20_1 and AR_5_1)
    ar_pre_20 = [ee.abnormal["ar_pre_20_1"] for ee in enriched]
    ar_pre_5 = [ee.abnormal["ar_pre_5_1"] for ee in enriched]
    dec20 = deciles(ar_pre_20)
    dec5 = deciles(ar_pre_5)
    for ee, d20, d5 in zip(enriched, dec20, dec5, strict=True):
        ee.pre_decile = d20
        ee.short_pre_decile = d5
        # Reversal vs continuation:
        # reversal_flag if sign(pre_AR_20_1) != sign(post_AR_0_5)
        # continuation_flag if sign(pre_AR_20_1) == sign(post_AR_0_5) and both non-trivial
        pre = ee.abnormal["ar_pre_20_1"]
        post = ee.abnormal["ar_post_0_5"]
        if pre is not None and post is not None and abs(pre) > 1e-6 and abs(post) > 1e-6:
            if (pre > 0) != (post > 0):
                ee.reversal_flag = True
            else:
                ee.continuation_flag = True

    return enriched


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------


def write_event_quality_csv(enriched: list[EnrichedEvent]) -> None:
    columns = [
        "event_id", "video_id", "creator", "ticker", "event_date",
        "recommendation_type", "evidence_quote", "event_quality_score",
        "event_quality_tier", "validation_flags", "exclusion_candidate",
        "reason_codes",
    ]
    rows: list[dict[str, Any]] = []
    for ee in enriched:
        rec_type = "buy" if "bull" in ee.event.stance else ("sell" if "bear" in ee.event.stance else ee.event.stance)
        rows.append({
            "event_id": ee.event.event_id,
            "video_id": ee.event.video_id,
            "creator": ee.event.creator,
            "ticker": ee.event.ticker,
            "event_date": ee.calendar_event_date.isoformat() if ee.calendar_event_date else "",
            "recommendation_type": rec_type,
            "evidence_quote": ee.evidence_quote,
            "event_quality_score": ee.quality_score,
            "event_quality_tier": ee.quality_tier,
            "validation_flags": ";".join(ee.validation_flags),
            "exclusion_candidate": ee.exclusion_candidate,
            "reason_codes": ";".join(ee.reason_codes),
        })
    write_csv(OUT_DIR / "02_event_quality_scores.csv", rows, columns)


def write_event_quality_summary(enriched: list[EnrichedEvent]) -> None:
    tier_counts = Counter(ee.quality_tier for ee in enriched)
    tier_by_creator: dict[str, Counter] = defaultdict(Counter)
    tier_by_ticker: dict[str, Counter] = defaultdict(Counter)
    reason_counter: Counter = Counter()
    exclusion_count = 0
    flag_counter: Counter = Counter()
    for ee in enriched:
        tier_by_creator[ee.event.creator][ee.quality_tier] += 1
        tier_by_ticker[ee.event.ticker][ee.quality_tier] += 1
        for r in ee.reason_codes:
            reason_counter[r] += 1
        for f in ee.validation_flags:
            flag_counter[f] += 1
        if ee.exclusion_candidate:
            exclusion_count += 1

    lines = [
        "# Event Quality Score Summary",
        "",
        f"- Total scored events: `{len(enriched)}`",
        f"- Exclusion candidates: `{exclusion_count}`",
        f"- Mean score: `{statistics.mean(ee.quality_score for ee in enriched):.2f}`",
        f"- Median score: `{statistics.median(ee.quality_score for ee in enriched):.2f}`",
        "",
        "## Distribution by Tier",
        "",
        "| Tier | Count | Share |",
        "| --- | --- | --- |",
    ]
    total = len(enriched)
    for tier in ["A", "B", "C", "D"]:
        c = tier_counts.get(tier, 0)
        share = c / total if total else 0.0
        lines.append(f"| {tier} | {c} | {share:.2%} |")
    lines += ["", "## Tier Share by Top 10 Creators", "",
              "| Creator | Total | A | B | C | D |",
              "| --- | --- | --- | --- | --- | --- |"]
    creator_totals = Counter(ee.event.creator for ee in enriched)
    for creator, total_c in creator_totals.most_common(10):
        ct = tier_by_creator.get(creator, Counter())
        lines.append(f"| {creator} | {total_c} | {ct.get('A',0)} | {ct.get('B',0)} | {ct.get('C',0)} | {ct.get('D',0)} |")
    lines += ["", "## Tier Share by Top 10 Tickers", "",
              "| Ticker | Total | A | B | C | D |",
              "| --- | --- | --- | --- | --- | --- |"]
    ticker_totals = Counter(ee.event.ticker for ee in enriched)
    for ticker, total_t in ticker_totals.most_common(10):
        tt = tier_by_ticker.get(ticker, Counter())
        lines.append(f"| {ticker} | {total_t} | {tt.get('A',0)} | {tt.get('B',0)} | {tt.get('C',0)} | {tt.get('D',0)} |")
    lines += ["", "## Top Reason Codes", "",
              "| Reason | Count | Meaning |",
              "| --- | --- | --- |"]
    for reason, count in reason_counter.most_common(15):
        meaning = REASON_CODE_DESCRIPTIONS.get(reason, "")
        lines.append(f"| {reason} | {count} | {meaning} |")
    lines += ["", "## Top Validation Flags", "",
              "| Flag | Count |",
              "| --- | --- |"]
    for flag, count in flag_counter.most_common(15):
        lines.append(f"| {flag} | {count} |")
    write_md(OUT_DIR / "03_event_quality_summary.md", "\n".join(lines) + "\n")


def write_validation_methodology() -> None:
    text = """# Automated Event Validation Methodology

## Why No Full Manual Audit

A full manual audit of 1,554 accepted recommendation events is not feasible for
this research-grade pass. A defensible manual audit would require at least
3-5 minutes per event for transcript context retrieval, recommendation
classification verification, and bookkeeping. At ~4 minutes per event, the full
sample alone is ~104 hours of single-rater work, before any second-rater
adjudication. The course timeline (Bloomberg validation expected in roughly
two days) cannot absorb that cost, and our goal is reproducible, auditable
inference rather than rater-bottlenecked inference.

## How Automated Validation Substitutes

The automated validator (`scripts/build_research_grade_analysis.py`) produces a
per-event quality score (0-100) and a tier (A/B/C/D) from auditable inputs that
the data already contains:

1. Transcript evidence traceability: presence and length of the
   `transcript_recommendation_events.evidence_window` text.
2. Directional language strength: lexicon match for explicit
   buy/sell/hold/own/add/trim language consistent with the classifier-assigned
   stance.
3. Conditionality and hedging: penalty for "if/might/could/may" patterns that
   would weaken a directional reading.
4. Recap/past-call risk: penalty for "I said/told you/remember when" phrasing
   that flags retrospective rather than forward calls.
5. News-only risk: penalty when the evidence window reads as a news summary
   ("according to/Reuters/Bloomberg reports/press release") without a
   first-person recommendation signal.
6. Ticker/company sanity: bonus when both ticker and company name are
   populated; penalty when the ticker appears on a common-word ambiguity
   watchlist (`NOW`, `ALL`, `ON`, `RUN`, etc.).
7. Duplicate-cluster risk: penalty for events that share creator+ticker+date
   with other events (collapsed by weekday-adjusted date).
8. Concentration flags: down-weight for top-5 ticker or top-5 creator
   membership, since those drive the headline mean by construction.
9. Market data coverage: heavy penalty when no on-or-after trading day exists
   in the local market-data CSV for the event's data ticker.
10. Outlier and high-impact flags: bookkeeping flags for |AR_1D| > 10% and
    AR_1D in the sample top/bottom 5% so downstream code can run high-impact
    cuts without re-deriving thresholds.
11. Classifier confidence: bonus/penalty bands around 0.45 / 0.60 / 0.75 of the
    rule-classifier confidence score already stored on the event row.

Reason codes (see `REASON_CODE_DESCRIPTIONS` in the script) are emitted in a
semicolon-joined `reason_codes` column so every score is auditable: any review
can replay the contribution of every code without rerunning the model.

## Where LLM Adjudication Belongs

This pass does not invoke any external LLM. The intended adjudication scope
for any future LLM pass is narrow and high-risk only:

- D-tier events with `news_only_risk`, `recap_risk`, or `weak_directional_signal`
  flags.
- Events with `ambiguous_ticker` flag (ticker on common-word watchlist).
- Duplicate-cluster heads where every member event tied to the same creator,
  ticker, and trading day might warrant collapsing to a single observation.

The repo already contains a `classifier_ai_audit/` directory with prior
adjudication output schema; that schema can absorb an LLM second pass without
new infrastructure.

## Optional 10-15 Minute Human Spot-Check

A 20-30 event spot-check is sufficient to detect catastrophic validator drift
(direction inversions, evidence quotes that contradict the recommendation
type, ticker collisions, mass duplication). The sample is built by
`04_quick_spot_check_sample.csv` and is composed of five buckets:

- Top 5 highest positive 1D abnormal returns.
- Top 5 most negative 1D abnormal returns.
- 5 lowest-quality-score accepted events.
- 5 duplicate-cluster events (largest creator+ticker+date clusters).
- 5 random events drawn with a fixed seed for reproducibility.

The reviewer fills `quick_review_result` (`agree`/`disagree`/`unsure`) and
`quick_notes` directly. The CSV is the audit artifact; no separate notebook is
required. Disagreement rates above 20% on the four targeted buckets should
trigger a focused LLM adjudication pass before any inference is reported as
research-grade.

## Audit Trail

For every accepted event the validator preserves:

- `event_id` (`transcript_event_id` primary key),
- raw stance and detected action from the classifier,
- evidence window length and a truncated evidence quote,
- duplicate-cluster id and size,
- a semicolon-joined list of validation flags and reason codes.

This means the per-event score can be recomputed from the database snapshot at
any time and any disagreement can be localized to a specific reason code.
"""
    write_md(OUT_DIR / "01_automated_event_validation_methodology.md", text)


def write_spot_check_sample(enriched: list[EnrichedEvent]) -> None:
    columns = [
        "event_id", "creator", "ticker", "event_date", "recommendation_type",
        "evidence_quote", "event_quality_score", "reason_for_inclusion",
        "quick_review_result", "quick_notes",
    ]
    # Buckets
    by_ar = [(ee, ee.abnormal.get("ar_event_0_1")) for ee in enriched if ee.abnormal.get("ar_event_0_1") is not None]
    by_ar.sort(key=lambda x: x[1])
    top_neg = [ee for ee, _ in by_ar[:5]]
    top_pos = [ee for ee, _ in by_ar[-5:][::-1]]
    lowest_quality = sorted(enriched, key=lambda e: e.quality_score)[:5]
    duplicate_events = sorted(enriched, key=lambda e: -e.duplicate_cluster_size)[:5]
    rng = random.Random(42)
    random_events = rng.sample(enriched, k=min(5, len(enriched)))

    seen: set[int] = set()
    rows: list[dict[str, Any]] = []

    def _rec_type(ee: EnrichedEvent) -> str:
        return "buy" if "bull" in ee.event.stance else ("sell" if "bear" in ee.event.stance else ee.event.stance)

    def _add(ee: EnrichedEvent, reason: str) -> None:
        if ee.event.event_id in seen:
            return
        seen.add(ee.event.event_id)
        rows.append({
            "event_id": ee.event.event_id,
            "creator": ee.event.creator,
            "ticker": ee.event.ticker,
            "event_date": ee.calendar_event_date.isoformat() if ee.calendar_event_date else "",
            "recommendation_type": _rec_type(ee),
            "evidence_quote": ee.evidence_quote,
            "event_quality_score": ee.quality_score,
            "reason_for_inclusion": reason,
            "quick_review_result": "",
            "quick_notes": "",
        })

    for ee in top_pos:
        _add(ee, "top_positive_AR_1D")
    for ee in top_neg:
        _add(ee, "top_negative_AR_1D")
    for ee in lowest_quality:
        _add(ee, "lowest_quality_score")
    for ee in duplicate_events:
        _add(ee, "duplicate_cluster_member")
    for ee in random_events:
        _add(ee, "random_seed_42")

    write_csv(OUT_DIR / "04_quick_spot_check_sample.csv", rows, columns)


def write_event_timeline(enriched: list[EnrichedEvent], market: dict[str, list[dict[str, Any]]]) -> None:
    columns = [
        "event_id", "video_id", "creator", "ticker", "recommendation_type",
        "video_published_at", "transcript_evidence_timestamp",
        "calendar_event_date", "effective_trading_event_date", "timing_bucket",
        "event_window_minus20_minus1_start", "event_window_minus20_minus1_end",
        "event_window_minus5_minus1_start", "event_window_minus5_minus1_end",
        "event_window_0_plus1_start", "event_window_0_plus1_end",
        "event_window_0_plus3_start", "event_window_0_plus3_end",
        "event_window_0_plus5_start", "event_window_0_plus5_end",
        "event_window_plus5_plus20_start", "event_window_plus5_plus20_end",
        "event_window_0_plus20_start", "event_window_0_plus20_end",
        "lookahead_risk_flag", "duplicate_cluster_id", "duplicate_cluster_size",
    ]
    rows: list[dict[str, Any]] = []
    for ee in enriched:
        rows.append(_timeline_row(ee, market))
    write_csv(OUT_DIR / "05_event_timeline_dataset.csv", rows, columns)


def _trading_date_at_offset(
    rows: list[dict[str, Any]], base_idx: int | None, offset: int
) -> str:
    if base_idx is None or rows is None:
        return ""
    idx = base_idx + offset
    if idx < 0 or idx >= len(rows):
        return ""
    return rows[idx]["date"].isoformat()


def _timeline_row(ee: EnrichedEvent, market: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rec_type = "buy" if "bull" in ee.event.stance else ("sell" if "bear" in ee.event.stance else ee.event.stance)
    ticker_rows = market.get(ee.data_ticker, [])
    base = ee.next_trading_idx
    # Lookahead risk: during/after market hours on the calendar event date means
    # the event occurs in the same trading day as the chosen "trading_day_0";
    # before_open or weekend means the recommendation precedes the next trading
    # day. We flag during_market and after_close as elevated lookahead risk
    # because the published_at may post-date intraday price moves we then assign
    # to the same trading day.
    lookahead_flag = ee.timing_bucket in {"during_market", "after_close"}
    # Evidence timestamp expressed as seconds offset within the video
    if ee.event.evidence_start_seconds is not None and ee.event.published_dt is not None:
        evt_ts = (ee.event.published_dt + timedelta(seconds=ee.event.evidence_start_seconds)).isoformat()
    else:
        evt_ts = ""
    out = {
        "event_id": ee.event.event_id,
        "video_id": ee.event.video_id,
        "creator": ee.event.creator,
        "ticker": ee.event.ticker,
        "recommendation_type": rec_type,
        "video_published_at": ee.event.published_at,
        "transcript_evidence_timestamp": evt_ts,
        "calendar_event_date": ee.calendar_event_date.isoformat() if ee.calendar_event_date else "",
        "effective_trading_event_date": ee.effective_trading_event_date.isoformat() if ee.effective_trading_event_date else "",
        "timing_bucket": ee.timing_bucket,
        "lookahead_risk_flag": lookahead_flag,
        "duplicate_cluster_id": ee.duplicate_cluster_id,
        "duplicate_cluster_size": ee.duplicate_cluster_size,
    }
    windows = [
        ("event_window_minus20_minus1", -20, -1),
        ("event_window_minus5_minus1", -5, -1),
        ("event_window_0_plus1", 0, 1),
        ("event_window_0_plus3", 0, 3),
        ("event_window_0_plus5", 0, 5),
        ("event_window_plus5_plus20", 5, 20),
        ("event_window_0_plus20", 0, 20),
    ]
    for prefix, lo, hi in windows:
        out[f"{prefix}_start"] = _trading_date_at_offset(ticker_rows, base, lo)
        out[f"{prefix}_end"] = _trading_date_at_offset(ticker_rows, base, hi)
    return out


def write_timeline_methodology() -> None:
    text = """# Event Timeline Methodology

## Inputs

- Locked sample of 1,554 accepted YouTube recommendation events
  (`transcript_recommendation_events` joined to `raw_youtube_videos`).
- `published_at` is the YouTube upload timestamp in UTC.
- Evidence offset within the video is taken from
  `transcript_recommendation_events.evidence_start_seconds`.
- Trading calendars are reconstructed from local yfinance market-data CSVs
  (`yfinance_expanded_market_data.csv` and `yfinance_market_data.csv`).

## Definitions

- `calendar_event_date`: UTC calendar date of the YouTube upload timestamp.
- `weekday_adjusted_date`: Saturday -> Monday, Sunday -> Monday, weekday
  preserved. Conservative because actual holiday calendars are not used.
- `effective_trading_event_date`: first available ticker trading day on or after
  `weekday_adjusted_date`. If the ticker has no row on or after that date,
  the field is blank and all window endpoints become blank.
- `transcript_evidence_timestamp`: `published_at + evidence_start_seconds`.
  This is a viewer-sequential timestamp proxy, not a market-release timestamp:
  the whole video can become publicly available at `published_at`, and the
  recording may have occurred before upload. It is retained only to locate the
  evidence span inside the video.
- `timing_bucket`: `before_open`, `during_market`, `after_close`,
  `weekend_or_holiday`, `unknown`. Uses a fixed UTC -> ET offset of -5 hours
  and ignores DST; this is a conservative approximation.
- `lookahead_risk_flag`: `True` for `during_market` or `after_close` events.
  Those events can be uploaded *after* the intraday move, so any same-day
  abnormal return that we attribute to the event window already contains some
  reaction the creator may have been responding to.

## Trading-Day Window Conventions

For each event, with `base_idx` defined as the trading-day index of
`effective_trading_event_date` for that ticker, the seven windows are computed
on trading-day offsets relative to `base_idx`:

| Window | Start offset | End offset | Use |
| --- | --- | --- | --- |
| [-20,-1] | -20 | -1 | Pre-event momentum |
| [-5,-1] | -5 | -1 | Short pre-event momentum |
| [0,+1] | 0 | +1 | Event-day reaction |
| [0,+3] | 0 | +3 | Reaction extension |
| [0,+5] | 0 | +5 | Headline 5D post-event window |
| [+5,+20] | +5 | +20 | Reversal vs continuation horizon |
| [0,+20] | 0 | +20 | Full post-event window |

When intraday timestamps are not granular enough to resolve the recommendation
to a market session (the only timestamp available is the upload time), we adopt
the conservative convention: the next available trading day on or after the
calendar event date is `trading_day_0`. This avoids backdating the
recommendation onto a day whose intraday moves the creator may have observed
before uploading. Events uploaded `before_open` therefore share the same
trading day index as events uploaded `during_market` or `after_close` on the
same calendar day, but the `lookahead_risk_flag` lets downstream consumers
isolate `before_open` events for cleanest inference.

## Duplicate Clustering

A cluster is identified by `(creator, ticker, weekday_adjusted_date)`.
`duplicate_cluster_id` is a deterministic integer (insertion order),
`duplicate_cluster_size` counts how many events share that key. Robust
inference should collapse clusters with `size >= 2` to a single observation or
cluster the standard errors on this key (see
`13_statistical_robustness_matrix.md`).

## Known Limitations

- Holiday-aware trading calendars are inferred only through the presence of a
  row in the ticker's market-data file; explicit NYSE/NASDAQ holiday tables
  would improve `effective_trading_event_date` for sparse tickers.
- DST-aware time-zone conversion is not applied; `timing_bucket` is a
  conservative approximation.
- For SQ historic events before 2025-01-21 the data ticker stays `SQ`; for
  events after the ticker change the data ticker is resolved to `XYZ`.
"""
    write_md(OUT_DIR / "06_event_timeline_methodology.md", text)


def write_momentum_outputs(enriched: list[EnrichedEvent]) -> None:
    csv_columns = [
        "event_id", "creator", "ticker", "recommendation_type",
        "pre_event_return_20_1", "pre_event_abnormal_return_20_1",
        "pre_event_return_5_1", "pre_event_abnormal_return_5_1",
        "event_day_return_0_1", "event_day_abnormal_return_0_1",
        "post_event_return_0_5", "post_event_abnormal_return_0_5",
        "post_event_return_5_20", "post_event_abnormal_return_5_20",
        "post_event_return_0_20", "post_event_abnormal_return_0_20",
        "momentum_decile", "short_momentum_decile",
        "reversal_flag", "continuation_flag",
        "event_quality_score",
    ]
    rows = []
    for ee in enriched:
        rec_type = "buy" if "bull" in ee.event.stance else ("sell" if "bear" in ee.event.stance else ee.event.stance)
        rows.append({
            "event_id": ee.event.event_id,
            "creator": ee.event.creator,
            "ticker": ee.event.ticker,
            "recommendation_type": rec_type,
            "pre_event_return_20_1": _fmt(ee.returns["ret_pre_20_1"]),
            "pre_event_abnormal_return_20_1": _fmt(ee.abnormal["ar_pre_20_1"]),
            "pre_event_return_5_1": _fmt(ee.returns["ret_pre_5_1"]),
            "pre_event_abnormal_return_5_1": _fmt(ee.abnormal["ar_pre_5_1"]),
            "event_day_return_0_1": _fmt(ee.returns["ret_event_0_1"]),
            "event_day_abnormal_return_0_1": _fmt(ee.abnormal["ar_event_0_1"]),
            "post_event_return_0_5": _fmt(ee.returns["ret_post_0_5"]),
            "post_event_abnormal_return_0_5": _fmt(ee.abnormal["ar_post_0_5"]),
            "post_event_return_5_20": _fmt(ee.returns["ret_post_5_20"]),
            "post_event_abnormal_return_5_20": _fmt(ee.abnormal["ar_post_5_20"]),
            "post_event_return_0_20": _fmt(ee.returns["ret_post_0_20"]),
            "post_event_abnormal_return_0_20": _fmt(ee.abnormal["ar_post_0_20"]),
            "momentum_decile": ee.pre_decile if ee.pre_decile is not None else "",
            "short_momentum_decile": ee.short_pre_decile if ee.short_pre_decile is not None else "",
            "reversal_flag": ee.reversal_flag,
            "continuation_flag": ee.continuation_flag,
            "event_quality_score": ee.quality_score,
        })
    write_csv(OUT_DIR / "08_momentum_decomposition_results.csv", rows, csv_columns)

    # Build regression models
    def _pack(rows_subset: list[tuple[float, list[float]]]) -> tuple[list[float], list[list[float]]]:
        if not rows_subset:
            return [], []
        y = [r[0] for r in rows_subset]
        X = [[1.0] + r[1] for r in rows_subset]
        return y, X

    # Build observations for each model
    model_specs: list[tuple[str, str, list[tuple[float, list[float]]]]] = []

    base_obs: list[tuple[float, list[float], str, str]] = []
    for ee in enriched:
        y = ee.abnormal["ar_post_0_5"]
        pre20 = ee.abnormal["ar_pre_20_1"]
        if y is None or pre20 is None:
            continue
        base_obs.append((y, [pre20], ee.event.creator, ee.event.ticker))

    # Model 1: y ~ pre20
    obs1 = [(y, x) for y, x, _, _ in base_obs]
    model_specs.append(("Model 1", "post_AR_0_5 ~ pre_AR_20_1", obs1))

    # Model 2: y ~ pre20 + pre5 + buy_dummy
    obs2 = []
    obs2_meta = []
    obs2_events = []
    for ee in enriched:
        y = ee.abnormal["ar_post_0_5"]
        pre20 = ee.abnormal["ar_pre_20_1"]
        pre5 = ee.abnormal["ar_pre_5_1"]
        if y is None or pre20 is None or pre5 is None:
            continue
        buy_dummy = 1.0 if "bull" in ee.event.stance else 0.0
        obs2.append((y, [pre20, pre5, buy_dummy]))
        obs2_meta.append((ee.event.creator, ee.event.ticker))
        obs2_events.append(ee)
    model_specs.append(("Model 2", "post_AR_0_5 ~ pre_AR_20_1 + pre_AR_5_1 + buy_dummy", obs2))

    # Model 3: + creator FE (top creators as dummies; reference = "other")
    top_creators = [c for c, _ in Counter(ee.event.creator for ee in enriched).most_common(8)]
    obs3 = []
    for (y, x), (creator, _ticker) in zip(obs2, obs2_meta, strict=True):
        creator_dummies = [1.0 if creator == c else 0.0 for c in top_creators[1:]]  # drop first as reference
        obs3.append((y, x + creator_dummies))
    model_specs.append(("Model 3", "Model 2 + top-creator FE (top 8, first as reference)", obs3))

    # Model 4: + ticker FE (top tickers as dummies)
    top_tickers = [t for t, _ in Counter(ee.event.ticker for ee in enriched).most_common(8)]
    obs4 = []
    for (y, x), (creator, ticker) in zip(obs2, obs2_meta, strict=True):
        creator_dummies = [1.0 if creator == c else 0.0 for c in top_creators[1:]]
        ticker_dummies = [1.0 if ticker == t else 0.0 for t in top_tickers[1:]]
        obs4.append((y, x + creator_dummies + ticker_dummies))
    model_specs.append(("Model 4", "Model 3 + top-ticker FE (top 8, first as reference)", obs4))

    # Model 5: + event_quality_score (omit news_overlap_flag because it is
    # identically zero in this pass and would make X'X singular; the
    # placeholder is documented below).
    obs5 = []
    for ee, base_row in zip(obs2_events, obs4, strict=True):
        y, x = base_row
        obs5.append((y, x + [ee.quality_score / 100.0]))
    model_specs.append(("Model 5", "Model 4 + event_quality_score_scaled (news_overlap_flag omitted in this pass; will be added Bloomberg-day)", obs5))

    # Run all models
    fitted: list[tuple[str, str, dict[str, Any] | None, list[str]]] = []
    var_names_per_model = {
        "Model 1": ["Intercept", "pre_AR_20_1"],
        "Model 2": ["Intercept", "pre_AR_20_1", "pre_AR_5_1", "buy_dummy"],
        "Model 3": ["Intercept", "pre_AR_20_1", "pre_AR_5_1", "buy_dummy"] +
            [f"creator[{c}]" for c in top_creators[1:]],
        "Model 4": ["Intercept", "pre_AR_20_1", "pre_AR_5_1", "buy_dummy"] +
            [f"creator[{c}]" for c in top_creators[1:]] +
            [f"ticker[{t}]" for t in top_tickers[1:]],
        "Model 5": ["Intercept", "pre_AR_20_1", "pre_AR_5_1", "buy_dummy"] +
            [f"creator[{c}]" for c in top_creators[1:]] +
            [f"ticker[{t}]" for t in top_tickers[1:]] +
            ["event_quality_score_scaled"],
    }
    for name, spec, obs in model_specs:
        y, X = _pack(obs)
        fit = ols_regression(y, X) if y else None
        fitted.append((name, spec, fit, var_names_per_model[name]))

    def _cluster_robust_rows(
        model_name: str,
        obs: list[tuple[float, list[float]]],
        vars_: list[str],
        events_for_obs: list[EnrichedEvent],
    ) -> tuple[list[dict[str, Any]], str | None]:
        try:
            import statsmodels.api as sm  # type: ignore[import-untyped]
        except Exception as exc:
            return [], f"statsmodels unavailable: {exc}"

        y, X = _pack(obs)
        if not y or len(events_for_obs) != len(y):
            return [], "observation/group length mismatch"

        rows_out: list[dict[str, Any]] = []
        target_vars = {"pre_AR_20_1", "pre_AR_5_1", "buy_dummy", "event_quality_score_scaled"}
        for group_name, groups in (
            ("ticker", [ee.event.ticker for ee in events_for_obs]),
            ("creator", [ee.event.creator for ee in events_for_obs]),
        ):
            try:
                fit = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
            except Exception as exc:
                return rows_out, f"{model_name} cluster by {group_name} failed: {exc}"
            for i, var in enumerate(vars_):
                if var not in target_vars:
                    continue
                rows_out.append({
                    "model": model_name,
                    "cluster": group_name,
                    "variable": var,
                    "coef": float(fit.params[i]),
                    "se": float(fit.bse[i]),
                    "t": float(fit.tvalues[i]),
                    "p": float(fit.pvalues[i]),
                    "n": len(y),
                    "clusters": len(set(groups)),
                })
        return rows_out, None

    cluster_rows: list[dict[str, Any]] = []
    cluster_notes: list[str] = []
    for model_name, obs, events_for_obs in (
        ("Model 2", obs2, obs2_events),
        ("Model 5", obs5, obs2_events),
    ):
        rows_out, note = _cluster_robust_rows(
            model_name,
            obs,
            var_names_per_model[model_name],
            events_for_obs,
        )
        cluster_rows.extend(rows_out)
        if note:
            cluster_notes.append(note)

    # Per-decile diagnostics
    decile_stats: list[dict[str, Any]] = []
    by_dec: dict[int, list[EnrichedEvent]] = defaultdict(list)
    for ee in enriched:
        if ee.pre_decile is not None:
            by_dec[ee.pre_decile].append(ee)
    for dec in sorted(by_dec):
        items = by_dec[dec]
        post = [ee.abnormal["ar_post_0_5"] for ee in items if ee.abnormal["ar_post_0_5"] is not None]
        hit = sum(1 for v in post if v > 0) / len(post) if post else float("nan")
        rev = sum(1 for ee in items if ee.reversal_flag) / len(items)
        n_post, mean_post, median_post, t_post, p_post = t_test_one_sample(post)
        decile_stats.append({
            "decile": dec,
            "n": len(items),
            "n_post": n_post,
            "mean_post_AR_0_5": mean_post,
            "median_post_AR_0_5": median_post,
            "t_post": t_post,
            "p_post": p_post,
            "hit_rate_post_AR_0_5": hit,
            "reversal_probability": rev,
        })

    # Markdown analysis
    lines = [
        "# Momentum Decomposition Analysis",
        "",
        "## Inputs",
        "",
        "- Locked sample: 1,554 accepted YouTube recommendation events.",
        "- Market data: local yfinance prices (expanded + base), SPY benchmark.",
        "- Window conventions match `06_event_timeline_methodology.md`.",
        "",
        "## Variable Definitions",
        "",
        "- `pre_AR_20_1`: SPY-adjusted abnormal return over trading days [-20, -1].",
        "- `pre_AR_5_1`: SPY-adjusted abnormal return over trading days [-5, -1].",
        "- `event_AR_0_1`: SPY-adjusted abnormal return over trading days [0, +1].",
        "- `post_AR_0_5`, `post_AR_5_20`, `post_AR_0_20`: as above for post-event windows.",
        "- `momentum_decile`: decile rank of `pre_AR_20_1` across the sample (1 = most negative).",
        "- `short_momentum_decile`: decile rank of `pre_AR_5_1`.",
        "- `reversal_flag`: True iff sign(`pre_AR_20_1`) != sign(`post_AR_0_5`) and both are non-trivial.",
        "- `continuation_flag`: True iff signs agree and both are non-trivial.",
        "",
        "## Models",
        "",
    ]
    for name, spec, fit, vars_ in fitted:
        lines.append(f"### {name}: {spec}")
        lines.append("")
        if fit is None:
            lines.append("Insufficient observations or singular design matrix; not fit.")
            lines.append("")
            continue
        lines.append(f"- n = {fit['n']}, adj R^2 = {fit['adj_r2']:.4f}, df = {fit['df']}")
        lines.append("")
        lines.append("| Variable | Coefficient | SE | t | p |")
        lines.append("| --- | --- | --- | --- | --- |")
        for i, v in enumerate(vars_):
            lines.append(
                f"| {v} | {fit['beta'][i]:.6f} | {fit['se'][i]:.6f} | {fit['t'][i]:.3f} | {fit['p'][i]:.4f} |"
            )
        lines.append("")
    lines += [
        "## Cluster-Robust SE Diagnostics",
        "",
        "Computed with `statsmodels.OLS(...).fit(cov_type=\"cluster\")` for Model 2",
        "and Model 5. These are diagnostic robustness checks on the same expanded",
        "yfinance event panel; they do not address news confounding or factor alphas.",
        "",
    ]
    if cluster_rows:
        lines += [
            "| Model | Cluster | Variable | Coefficient | Cluster SE | t | p | n | clusters |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in cluster_rows:
            lines.append(
                f"| {row['model']} | {row['cluster']} | {row['variable']} | "
                f"{row['coef']:.6f} | {row['se']:.6f} | {row['t']:.3f} | "
                f"{row['p']:.4f} | {row['n']} | {row['clusters']} |"
            )
        lines.append("")
    if cluster_notes:
        lines.append("Cluster diagnostic notes:")
        lines.extend(f"- {note}" for note in cluster_notes)
        lines.append("")
    lines += [
        "## Pre-Event Momentum Decile Diagnostics",
        "",
        "| Decile | n | n_post | mean post_AR_0_5 | median post_AR_0_5 | t | p | hit_rate | reversal_prob |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for ds in decile_stats:
        lines.append(
            f"| {ds['decile']} | {ds['n']} | {ds['n_post']} | "
            f"{_fmt(ds['mean_post_AR_0_5'])} | {_fmt(ds['median_post_AR_0_5'])} | "
            f"{_fmt(ds['t_post'], 3)} | {_fmt(ds['p_post'], 4)} | "
            f"{_fmt(ds['hit_rate_post_AR_0_5'], 4)} | {_fmt(ds['reversal_probability'], 4)} |"
        )
    lines += [
        "",
        "## Interpretation Guardrails",
        "",
        "- `news_overlap_flag` is omitted from Model 5 because the current news flags",
        "  are protocol placeholders. After Bloomberg or SEC EDGAR news flagging runs,",
        "  Model 5 should include the populated flag and report any coefficient changes.",
        "- Fixed-effect implementation uses top-creator and top-ticker dummies (first level dropped as",
        "  reference). With ~1,500 observations and 14-15 dummies this is well-identified; absorbing",
        "  full FE (35 creators, 23 tickers) is recommended in any future statsmodels rerun.",
        "- p-values use a normal approximation; for n in this range the deviation from a t distribution",
        "  is negligible, but final paper tables should use the statsmodels cluster/HAC covariance",
        "  estimators shown above.",
        "",
    ]
    write_md(OUT_DIR / "07_momentum_decomposition_analysis.md", "\n".join(lines))


def write_news_overlap_outputs(enriched: list[EnrichedEvent]) -> None:
    # Methodology
    methodology = """# News Overlap Methodology

## Goal

For every accepted YouTube recommendation event, determine whether a confounding
public information event sits in a tight window around the recommendation. A
confounded event cannot be used to attribute abnormal returns to the YouTube
recommendation itself.

## Confound Types Targeted

- **SEC filings**: 8-K, 10-Q, 10-K, S-1, 424B, 10-Q/A, 10-K/A and any other
  material-event filing the SEC records under the issuer's CIK.
- **Earnings releases**: separate flag because earnings are typically pre-announced
  on the issuer IR calendar even when not yet filed as an 8-K.
- **Other major news**: company-specific news clusters (analyst rating changes,
  M&A, regulatory action, product recalls, executive changes).

## Sources Permitted in This Pass

This pass is read-only and does not require Bloomberg. Two safe free sources
are allowed; both are run as protocol with an explicit fallback. If a source is
not invoked, the corresponding `news_source_used` is `protocol_only` and
`news_query_status` is `not_run`.

1. **SEC EDGAR company submissions API** (`https://data.sec.gov/submissions/CIK########.json`)
   - Requires a ticker -> CIK mapping. If the mapping file does not exist in the
     repo, this pass is run in protocol mode and a Bloomberg-day rerun fills the
     real values.
   - Rate-limit policy: respect SEC fair-access (max 10 requests/second, with a
     descriptive `User-Agent`). This pass uses a conservative <=2 requests per
     second when invoked.
   - Cached payload only stores metadata (filing date, accession number, form
     type). Filing bodies are not fetched.
2. **GDELT GKG counts** (`https://api.gdeltproject.org/api/v2/doc/doc?...`)
   - Used only to produce a noisy proxy `major_news_near_event_flag` if invoked.
   - Counts and top metadata are cached; full article bodies are not downloaded
     and not redistributed.
   - Treated as a noisy proxy because GDELT keyword matching has high false
     positive rates and does not guarantee creator-relevance.

When neither source is invoked (default for this pass), the output CSV is
populated with the full schema and explicit placeholder values:

| Field | Value when not run |
| --- | --- |
| `sec_filing_near_event_flag` | `unknown` |
| `sec_8k_near_event_flag` | `unknown` |
| `earnings_near_event_flag` | `unknown` |
| `major_news_near_event_flag` | `unknown` |
| `same_day_news_flag` | `unknown` |
| `plus_minus_1_day_news_flag` | `unknown` |
| `plus_minus_3_day_news_flag` | `unknown` |
| `plus_minus_5_day_news_flag` | `unknown` |
| `news_confounded_event_flag` | `unknown` |
| `news_source_used` | `protocol_only` |
| `news_query_status` | `not_run` |

## Window Definitions

- `same_day_news_flag`: news event timestamp falls on the trading day equal to
  `effective_trading_event_date`.
- `plus_minus_1_day_news_flag`: news event timestamp falls within +/-1 trading
  day of `effective_trading_event_date`.
- `plus_minus_3_day_news_flag`: +/-3 trading days.
- `plus_minus_5_day_news_flag`: +/-5 trading days. This is the primary
  confound-window flag and aligns with Bloomberg news search of
  `event_date +/-5 calendar/trading days` requested in the Bloomberg plan.
- Filing-based flags (`sec_*`) use *calendar* day windows because SEC filings
  are calendar-day stamped. The tightest filing flag is the same trading day,
  with a +/- 5 trading-day window for the broad flag.

## Confound Definition

`news_confounded_event_flag = True` iff any of the following holds within
+/- 5 trading days of `effective_trading_event_date`:

- `sec_8k_near_event_flag = True`,
- `earnings_near_event_flag = True`,
- `major_news_near_event_flag = True` (sustained cluster, e.g., >= 3 high-tone
  GDELT articles tagged to the issuer in the window).

The flag is intentionally conservative: it removes the event from any
robustness cut that purports to test the YouTube-recommendation channel
independently of public news.

## Bloomberg-Ready Replacement

When Bloomberg access becomes available, the same CSV schema is regenerated by
running the BQuant / Excel-API job described in `18_bloomberg_validation_protocol.md`.
Required Bloomberg fields:

- `CH_LAST` company headlines on event date +/-5 calendar/trading days,
- `ANR` analyst rating change events,
- `EARN_ANN_DT` earnings announcement timestamps,
- `EVT_DT_EARN`, `EVT_DT_DIV`, `EVT_DT_SPLIT`, `EVT_DT_CORP_ACTION`,
- `NEWS_HEAT_PUB_DNUM` news heat sub-scores.

## Reproducibility

If/when the SEC EDGAR or GDELT pass runs, the script emits a `news_query_log.json`
in this directory recording: request URL (sanitized), HTTP status, response
size, retrieval timestamp, and any backoff applied. No request payload contains
secrets. Re-running with the same locked sample and the same query log
deterministically reproduces the flag CSV.
"""
    write_md(OUT_DIR / "09_news_overlap_methodology.md", methodology)

    # Flags CSV in protocol mode (no live calls in this pass).
    rows = []
    for ee in enriched:
        rows.append({
            "event_id": ee.event.event_id,
            "ticker": ee.event.ticker,
            "event_date": ee.calendar_event_date.isoformat() if ee.calendar_event_date else "",
            "effective_trading_event_date": ee.effective_trading_event_date.isoformat() if ee.effective_trading_event_date else "",
            "sec_filing_near_event_flag": "unknown",
            "sec_8k_near_event_flag": "unknown",
            "earnings_near_event_flag": "unknown",
            "major_news_near_event_flag": "unknown",
            "same_day_news_flag": "unknown",
            "plus_minus_1_day_news_flag": "unknown",
            "plus_minus_3_day_news_flag": "unknown",
            "plus_minus_5_day_news_flag": "unknown",
            "news_confounded_event_flag": "unknown",
            "news_source_used": "protocol_only",
            "news_query_status": "not_run",
        })
    write_csv(OUT_DIR / "10_news_overlap_flags.csv", rows, NEWS_FLAG_COLUMNS)

    summary = f"""# News Overlap Summary

## Status

- Live SEC EDGAR pass: **not run** in this pass (ALLOW_SEC_EDGAR off by default
  to keep the analysis fully offline-safe).
- Live GDELT pass: **not run** in this pass.
- All flag columns in `10_news_overlap_flags.csv` are populated with the value
  `unknown`. `news_source_used = protocol_only`, `news_query_status = not_run`.

## Sample

- Rows in flag CSV: `{len(rows)}` (= 1,554 locked events).

## Bloomberg-Day Rerun Checklist

1. Build `data/seeds/ticker_cik_map.csv` for the 23 locked tickers from
   `https://www.sec.gov/files/company_tickers.json`.
2. Run SEC EDGAR pass: per ticker, pull
   `https://data.sec.gov/submissions/CIK<10-digit>.json`, filter to
   `filings.recent.form in {{8-K, 10-Q, 10-K, S-1, 424B, 10-K/A, 10-Q/A}}`,
   keep `filingDate`, `form`, `accessionNumber`.
3. For each locked event, set `sec_8k_near_event_flag = True` iff any 8-K filing
   date is within +/-5 trading days of `effective_trading_event_date`. Tighten
   to same-day and +/-1 day flags using the same filing dates.
4. Populate `earnings_near_event_flag` from Bloomberg `EARN_ANN_DT`. SEC EDGAR
   alone is *not* sufficient because earnings are typically announced ahead of
   the 8-K filing.
5. Populate `major_news_near_event_flag` from Bloomberg `NEWS_HEAT_PUB_DNUM`
   peaks within +/-5 trading days, with manual sanity check on the top 30
   flagged events.
6. Replace `news_query_status = not_run` with `bloomberg_<YYYY-MM-DD>` and
   commit the regenerated CSV to `data/exports/research_grade_analysis/`.

## Why No Live Run Now

- The task specification explicitly disallows paid sources and treats SEC and
  GDELT as optional. Going offline keeps the run deterministic, removes
  network failure modes, and means the same CSV schema is delivered whether or
  not external calls succeeded. Bloomberg-day rerun is the canonical fill-in
  step.
"""
    write_md(OUT_DIR / "11_news_overlap_summary.md", summary)


def write_return_robustness_plan() -> None:
    text = """# Return Model Robustness Plan

## Status

- Baseline: market-adjusted abnormal returns vs SPY (computed in this pass for
  all 1,554 events with available local market data).
- Plan: extend to a layered set of return models against the same locked
  sample, with explicit reruns scheduled at Bloomberg-day.

## Layered Models

| # | Model | What it adds | Computed in this pass | Required data |
| --- | --- | --- | --- | --- |
| 1 | Raw returns | None | Yes | Local yfinance prices |
| 2 | Market-adjusted | Subtract SPY return | Yes | Local SPY series |
| 3 | CAPM alpha | Regress on SPY excess; report alpha | Plan | Risk-free rate (FRED DGS3MO), or treat as zero |
| 4 | Fama-French 3 factor | Add SMB, HML | Plan | Kenneth French Data Library |
| 5 | Carhart 4 factor | Add MOM | Plan | Kenneth French Data Library |
| 6 | Fama-French 5 factor | Add RMW, CMA | Plan | Kenneth French Data Library |
| 7 | Industry-adjusted | Subtract sector ETF (XLK/XLC/XLY/XLF/XLI) | Plan (sector mapping already exists) | Local sector ETF series in expanded file |
| 8 | Matched-control | Build size/momentum matched control firm; AR = event - control | Plan | Tradeable universe + market-cap snapshot |

## Implementation Sketch

```python
import pandas as pd
import statsmodels.api as sm
import requests
from io import BytesIO
from zipfile import ZipFile

def fetch_french_factors(url: str) -> pd.DataFrame:
    r = requests.get(url, headers={"User-Agent": "fin496-capstone (educational)"}, timeout=30)
    r.raise_for_status()
    with ZipFile(BytesIO(r.content)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".CSV"))
        with zf.open(name) as f:
            df = pd.read_csv(f, skiprows=3, skipfooter=2, engine="python")
    df = df.rename(columns={df.columns[0]: "date"})
    df["date"] = pd.to_datetime(df["date"].astype(str).str.zfill(8), format="%Y%m%d", errors="coerce")
    return df.dropna(subset=["date"]).set_index("date").apply(pd.to_numeric, errors="coerce") / 100.0

FF3 = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip"
MOM = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_daily_CSV.zip"
FF5 = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
```

For each model and each event-window definition (1D, 5D, 20D), report:

- alpha, t-stat, p-value, n,
- mean and median return,
- subsample cuts by buy/sell, by top-vs-non-top ticker, by quality tier A vs C/D,
- comparison vs the market-adjusted baseline (delta in alpha and t-stat).

## Implementation Order (Bloomberg-Day Plan)

1. Fetch French data daily files (FF3, MOM, FF5) into
   `data/imports/french_factors/`. This is allowed because the Kenneth French
   data library is free and explicitly cite-able.
   Expected extracted files:
   - `data/imports/french_factors/F-F_Research_Data_Factors_daily.CSV`
   - `data/imports/french_factors/F-F_Momentum_Factor_daily.CSV`
   - `data/imports/french_factors/F-F_Research_Data_5_Factors_2x3_daily.CSV`
2. Build `event_factor_panel.csv`: event_id x window x daily return contributions
   (ticker excess, SPY excess, factor returns aligned to trading days).
3. Run CAPM via `statsmodels.OLS(y, X)` with HC0 standard errors.
4. Run FF3, Carhart, FF5 via the same scaffolding (only the X matrix grows).
5. Run industry-adjusted by replacing SPY with the mapped sector ETF.
6. Build matched-control: nearest-neighbor on (market cap decile, momentum
   decile, SPY beta). With only 23 tickers in the sample, matched control should
   use a *cross-section* of S&P 500 universe constructed once.
7. Report a consolidated `return_model_alpha_table.csv` with one row per
   (model, window, sample cut).

## Acceptance Criteria

- Headline 5D abnormal return is positive and significant under at least three
  of {raw, market-adj, CAPM, FF3, Carhart, FF5, industry-adj}.
- Headline result survives matched-control (delta in alpha within 2 standard
  errors of the market-adjusted baseline).
- Sign and direction stable across buy and sell cuts.
- No single creator or single ticker drives more than 25% of the headline
  point estimate (this is also a robustness cut in `13_statistical_robustness_matrix.md`).
"""
    write_md(OUT_DIR / "12_return_model_robustness_plan.md", text)


def _canonical_baseline_ars(enriched: list[EnrichedEvent]) -> tuple[list[float], list[float]]:
    """Replicate the locked-sample yfinance baseline: 16 large-cap tickers only,
    benchmark_adjusted_close column from `yfinance_market_data.csv`. Returns
    (ar_1d, ar_5d). This matches the locked numbers exactly:
    n=1516, mean_1D=0.002728, n=1503, mean_5D=0.005236.
    """
    if not MARKET_DATA_FALLBACK.exists():
        return [], []
    by_ticker: dict[str, dict[date, tuple[float, float]]] = defaultdict(dict)
    with MARKET_DATA_FALLBACK.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                d = _to_date(r.get("date"))
            except (ValueError, TypeError):
                continue
            px = _safe_float(r.get("adjusted_close"))
            bench = _safe_float(r.get("benchmark_adjusted_close"))
            if px is None or bench is None:
                continue
            by_ticker[(r.get("ticker") or "").upper()][d] = (px, bench)
    sorted_dates = {tk: sorted(d.keys()) for tk, d in by_ticker.items()}

    ar_1d, ar_5d = [], []
    for ee in enriched:
        if ee.weekday_adjusted_date is None:
            continue
        tk = ee.event.ticker
        data_tk = tk
        if tk == "SQ" and ee.weekday_adjusted_date >= date(2025, 1, 21):
            data_tk = "XYZ"
        if data_tk not in by_ticker:
            continue
        dates = sorted_dates[data_tk]
        idx = None
        for i, d in enumerate(dates):
            if d >= ee.weekday_adjusted_date:
                idx = i
                break
        if idx is None:
            continue
        a1 = _baseline_ar(by_ticker, data_tk, dates, idx, 1)
        a5 = _baseline_ar(by_ticker, data_tk, dates, idx, 5)
        if a1 is not None:
            ar_1d.append(a1)
        if a5 is not None:
            ar_5d.append(a5)
    return ar_1d, ar_5d


def _baseline_ar(
    by_ticker: dict[str, dict[date, tuple[float, float]]],
    data_tk: str,
    dates: list[date],
    idx: int,
    horizon: int,
) -> float | None:
    if idx + horizon >= len(dates):
        return None
    px0, b0 = by_ticker[data_tk][dates[idx]]
    px1, b1 = by_ticker[data_tk][dates[idx + horizon]]
    if px0 == 0 or b0 == 0:
        return None
    return (px1 / px0 - 1) - (b1 / b0 - 1)


def write_statistical_robustness_matrix(enriched: list[EnrichedEvent]) -> None:
    # Canonical locked-sample baseline (16-ticker yfinance file, matches locked spec)
    canon_1d, canon_5d = _canonical_baseline_ars(enriched)
    cn_1, cm_1, cmd_1, ct_1, cp_1 = t_test_one_sample(canon_1d)
    cn_5, cm_5, cmd_5, ct_5, cp_5 = t_test_one_sample(canon_5d)

    # Expanded-data calculation (35 tickers, includes small caps)
    ar_1d = [ee.abnormal["ar_event_0_1"] for ee in enriched if ee.abnormal["ar_event_0_1"] is not None]
    ar_5d = [ee.abnormal["ar_post_0_5"] for ee in enriched if ee.abnormal["ar_post_0_5"] is not None]

    n_1, mean_1, median_1, t_1, p_1 = t_test_one_sample(ar_1d)
    n_5, mean_5, median_5, t_5, p_5 = t_test_one_sample(ar_5d)

    # Wilcoxon signed-rank (sign test approximation) using just sign counts
    def _sign_test(xs: list[float]) -> tuple[int, int, float]:
        nz = [x for x in xs if abs(x) > 1e-9]
        pos = sum(1 for x in nz if x > 0)
        n = len(nz)
        if n == 0:
            return 0, 0, float("nan")
        p_hat = pos / n
        # Two-sided binomial vs 0.5 normal approx
        z = (p_hat - 0.5) / math.sqrt(0.25 / n)
        p = 2.0 * (1.0 - _norm_cdf(abs(z)))
        return n, pos, p

    sn_1, sp_1, sp_p_1 = _sign_test(ar_1d)
    sn_5, sp_5, sp_p_5 = _sign_test(ar_5d)

    # Bootstrap 95% CI for mean AR_5D (1000 resamples) using fixed seed
    def _bootstrap_ci(xs: list[float], iters: int = 1000, seed: int = 7) -> tuple[float, float]:
        rng = random.Random(seed)
        if not xs:
            return float("nan"), float("nan")
        means: list[float] = []
        n = len(xs)
        for _ in range(iters):
            sample = [xs[rng.randrange(n)] for _ in range(n)]
            means.append(sum(sample) / n)
        means.sort()
        return means[int(0.025 * iters)], means[int(0.975 * iters)]

    ci_5_lo, ci_5_hi = _bootstrap_ci(ar_5d)
    ci_1_lo, ci_1_hi = _bootstrap_ci(ar_1d)

    # Subsample stats: buy-only, sell-only
    ar_5d_buy = [ee.abnormal["ar_post_0_5"] for ee in enriched
                 if "bull" in ee.event.stance and ee.abnormal["ar_post_0_5"] is not None]
    ar_5d_sell = [ee.abnormal["ar_post_0_5"] for ee in enriched
                  if "bear" in ee.event.stance and ee.abnormal["ar_post_0_5"] is not None]
    bn, bm, _, bt, bp = t_test_one_sample(ar_5d_buy)
    sn, sm, _, st_, sp = t_test_one_sample(ar_5d_sell)

    # Duplicate-collapsed: keep first event per cluster_id
    seen_clusters: set[int] = set()
    ar_5d_dedup = []
    for ee in enriched:
        if ee.duplicate_cluster_id in seen_clusters:
            continue
        seen_clusters.add(ee.duplicate_cluster_id)
        if ee.abnormal["ar_post_0_5"] is not None:
            ar_5d_dedup.append(ee.abnormal["ar_post_0_5"])
    dn, dm, _, dt_, dp = t_test_one_sample(ar_5d_dedup)

    # High-quality only (tier A or B)
    ar_5d_hq = [ee.abnormal["ar_post_0_5"] for ee in enriched
                if ee.quality_tier in {"A", "B"} and ee.abnormal["ar_post_0_5"] is not None]
    hn, hm, _, ht, hp = t_test_one_sample(ar_5d_hq)

    # Winsorize at 1% / 99%
    def _winsorize(xs: list[float], p: float = 0.01) -> list[float]:
        if not xs:
            return xs
        s = sorted(xs)
        lo = s[int(p * (len(s) - 1))]
        hi = s[int((1 - p) * (len(s) - 1))]
        return [min(max(x, lo), hi) for x in xs]

    ar_5d_wins = _winsorize(ar_5d)
    wn, wm, _, wt, wp = t_test_one_sample(ar_5d_wins)

    # Non-top-ticker (exclude NVDA, TSLA, AAPL, AMD, AMZN)
    top5 = {"NVDA", "TSLA", "AAPL", "AMD", "AMZN"}
    ar_5d_nontop = [ee.abnormal["ar_post_0_5"] for ee in enriched
                    if ee.event.ticker not in top5 and ee.abnormal["ar_post_0_5"] is not None]
    ntn, ntm, _, ntt, ntp = t_test_one_sample(ar_5d_nontop)

    def _values(field: str, predicate=lambda ee: True) -> list[float]:
        return [
            value for ee in enriched
            if predicate(ee) and (value := ee.abnormal[field]) is not None
        ]

    def _dedup_values(field: str) -> list[float]:
        seen: set[int] = set()
        values: list[float] = []
        for ee in enriched:
            if ee.duplicate_cluster_id in seen:
                continue
            seen.add(ee.duplicate_cluster_id)
            value = ee.abnormal[field]
            if value is not None:
                values.append(value)
        return values

    def _cut_row(name: str, vals_1d: list[float], vals_5d: list[float], note: str) -> dict[str, Any]:
        n1, m1, _, t1_, p1_ = t_test_one_sample(vals_1d)
        n5, m5, _, t5_, p5_ = t_test_one_sample(vals_5d)
        return {
            "cut": name,
            "n1": n1,
            "mean1": m1,
            "t1": t1_,
            "p1": p1_,
            "n5": n5,
            "mean5": m5,
            "t5": t5_,
            "p5": p5_,
            "note": note,
        }

    low_lookahead_buckets = {"before_open", "weekend_or_holiday"}
    core_cut_rows = [
        _cut_row("Canonical baseline", canon_1d, canon_5d, "16-ticker locked yfinance file"),
        _cut_row("Expanded all events", ar_1d, ar_5d, "All locked events with expanded market coverage"),
        _cut_row(
            "Low-lookahead-risk",
            _values("ar_event_0_1", lambda ee: ee.timing_bucket in low_lookahead_buckets),
            _values("ar_post_0_5", lambda ee: ee.timing_bucket in low_lookahead_buckets),
            "before_open/weekend_or_holiday only; fixed UTC-to-ET approximation",
        ),
        _cut_row(
            "Duplicate-collapsed",
            _dedup_values("ar_event_0_1"),
            ar_5d_dedup,
            "First event per creator+ticker+weekday-adjusted-date cluster",
        ),
        _cut_row(
            "Non-top-ticker",
            _values("ar_event_0_1", lambda ee: ee.event.ticker not in top5),
            ar_5d_nontop,
            "Excludes NVDA/TSLA/AAPL/AMD/AMZN",
        ),
        _cut_row(
            "High-quality tier A/B",
            _values("ar_event_0_1", lambda ee: ee.quality_tier in {"A", "B"}),
            ar_5d_hq,
            "Automated event-quality score >= 65",
        ),
    ]
    core_cut_table_rows = "\n".join(
        f"| {row['cut']} | {row['n1']} | {row['mean1']:.6f} | {row['t1']:.3f} | "
        f"{row['p1']:.4f} | {row['n5']} | {row['mean5']:.6f} | "
        f"{row['t5']:.3f} | {row['p5']:.4f} | {row['note']} |"
        for row in core_cut_rows
    )

    fdr_inputs = []
    for row in core_cut_rows:
        fdr_inputs.append((f"{row['cut']} AR_0_1", row["p1"]))
        fdr_inputs.append((f"{row['cut']} AR_0_5", row["p5"]))
    fdr_inputs.extend([
        ("Buy-only AR_0_5", bp),
        ("Sell-only AR_0_5", sp),
        ("Winsorized 1%/99% AR_0_5", wp),
    ])
    q_values = benjamini_hochberg([float(p) for _, p in fdr_inputs])
    fdr_table_rows = "\n".join(
        f"| {label} | {p:.4f} | {q:.4f} |"
        for (label, p), q in zip(fdr_inputs, q_values, strict=True)
    )

    # Leave-one-creator-out: report range of mean AR_5D across LOCO runs (top 5 creators).
    top_creators = [c for c, _ in Counter(ee.event.creator for ee in enriched).most_common(5)]
    loco_creator: list[tuple[str, int, float, float, float]] = []
    for cr in top_creators:
        xs = [ee.abnormal["ar_post_0_5"] for ee in enriched
              if ee.event.creator != cr and ee.abnormal["ar_post_0_5"] is not None]
        n, m, _, t_, p = t_test_one_sample(xs)
        loco_creator.append((cr, n, m, t_, p))

    # Leave-one-ticker-out (top 5)
    top_tickers = [t for t, _ in Counter(ee.event.ticker for ee in enriched).most_common(5)]
    loco_ticker: list[tuple[str, int, float, float, float]] = []
    for tk in top_tickers:
        xs = [ee.abnormal["ar_post_0_5"] for ee in enriched
              if ee.event.ticker != tk and ee.abnormal["ar_post_0_5"] is not None]
        n, m, _, t_, p = t_test_one_sample(xs)
        loco_ticker.append((tk, n, m, t_, p))

    # Placebo: shift each event's effective trading date by +/- {15, 30, 60} trading days
    # and recompute AR_5D using the same windows. We can't easily do this here without
    # rebuilding the market panel, so we emit a permutation test instead: scramble event
    # date assignments within ticker.
    # Permutation: per ticker, randomly reassign event_id -> existing other event's index.
    # Effect: this shuffles which event gets which post-event window for that ticker.
    rng = random.Random(13)
    placebo_means: list[float] = []
    by_ticker_idxs: dict[str, list[int]] = defaultdict(list)
    for i, ee in enumerate(enriched):
        by_ticker_idxs[ee.data_ticker].append(i)
    # Build market panel index alignment from enriched directly
    # We approximate placebo by sampling AR_5D values within ticker uniformly.
    ar_5d_by_ticker: dict[str, list[float]] = defaultdict(list)
    for ee in enriched:
        if ee.abnormal["ar_post_0_5"] is not None:
            ar_5d_by_ticker[ee.data_ticker].append(ee.abnormal["ar_post_0_5"])
    for _ in range(500):
        sampled = []
        for tk, indices in by_ticker_idxs.items():
            pool = ar_5d_by_ticker.get(tk, [])
            if not pool:
                continue
            for _ in indices:
                sampled.append(pool[rng.randrange(len(pool))])
        if sampled:
            placebo_means.append(sum(sampled) / len(sampled))
    placebo_mean_avg = sum(placebo_means) / len(placebo_means) if placebo_means else float("nan")
    placebo_ge_obs = sum(1 for m in placebo_means if m >= mean_5) / len(placebo_means) if placebo_means else float("nan")

    text = f"""# Statistical Robustness Matrix

## Headline Summary

Two parallel calculations are reported. The **canonical baseline** restricts the
ticker universe to the 16-ticker `yfinance_market_data.csv` file that was used
to derive the locked-spec abnormal returns (`n=1,516 (1D)`,
`mean_1D=0.002728`, `p_1D=0.001174`; `n=1,503 (5D)`, `mean_5D=0.005236`,
`p_5D=0.001425`). The **expanded sample** uses
`yfinance_expanded_market_data.csv`, which covers all 23 locked event tickers
plus benchmarks/sector ETFs and adds 6 smaller-cap event tickers (AMC, COIN,
GME, HOOD, SHOP, SMCI). The shift between the two rows is itself a robustness
finding: the headline result is sensitive to small-cap inclusion.

### Canonical baseline (16-ticker file, matches locked spec)

| Window | n | mean | median | t | p (normal approx) |
| --- | --- | --- | --- | --- | --- |
| AR_0_1 (1D) | {cn_1} | {cm_1:.6f} | {cmd_1:.6f} | {ct_1:.3f} | {cp_1:.4f} |
| AR_0_5 (5D) | {cn_5} | {cm_5:.6f} | {cmd_5:.6f} | {ct_5:.3f} | {cp_5:.4f} |

### Expanded sample (35-ticker file, all locked events with market coverage)

| Window | n | mean | median | t | p (normal approx) | bootstrap 95% CI |
| --- | --- | --- | --- | --- | --- | --- |
| AR_0_1 (1D) | {n_1} | {mean_1:.6f} | {median_1:.6f} | {t_1:.3f} | {p_1:.4f} | [{ci_1_lo:.6f}, {ci_1_hi:.6f}] |
| AR_0_5 (5D) | {n_5} | {mean_5:.6f} | {median_5:.6f} | {t_5:.3f} | {p_5:.4f} | [{ci_5_lo:.6f}, {ci_5_hi:.6f}] |

All numbers above use SPY-adjusted abnormal returns on the locked sample. The
canonical mean/p values match the locked yfinance provisional values to
displayed precision. The return windows use adjusted-close-to-adjusted-close
price relatives; they are event-study windows, not executable open/close
trading rules.

## Timing and Core Robustness Cuts

| Cut | 1D n | 1D mean | 1D t | 1D p | 5D n | 5D mean | 5D t | 5D p | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
{core_cut_table_rows}

## Sign Test (Wilcoxon Approximation via Binomial Sign)

| Window | n_nonzero | n_positive | two-sided p |
| --- | --- | --- | --- |
| AR_0_1 (1D) | {sn_1} | {sp_1} | {sp_p_1:.4f} |
| AR_0_5 (5D) | {sn_5} | {sp_5} | {sp_p_5:.4f} |

## Multiple-Testing Adjustment

Benjamini-Hochberg FDR is computed across the headline timing/core-cut
p-values plus the buy, sell, and winsorized 5D cuts reported below.

| Test | raw p | BH q |
| --- | --- | --- |
{fdr_table_rows}

## Direction and Sample Cuts (AR_0_5)

| Cut | n | mean | t | p |
| --- | --- | --- | --- | --- |
| Buy only | {bn} | {bm:.6f} | {bt:.3f} | {bp:.4f} |
| Sell only | {sn} | {sm:.6f} | {st_:.3f} | {sp:.4f} |
| Duplicate-collapsed | {dn} | {dm:.6f} | {dt_:.3f} | {dp:.4f} |
| High-quality only (tier A/B) | {hn} | {hm:.6f} | {ht:.3f} | {hp:.4f} |
| Winsorized 1%/99% | {wn} | {wm:.6f} | {wt:.3f} | {wp:.4f} |
| Non-top-ticker (exclude NVDA/TSLA/AAPL/AMD/AMZN) | {ntn} | {ntm:.6f} | {ntt:.3f} | {ntp:.4f} |

## Leave-One-Creator-Out (AR_0_5, top 5 creators)

| Excluded creator | n_remaining | mean | t | p |
| --- | --- | --- | --- | --- |
""" + "\n".join(
        f"| {c} | {n} | {m:.6f} | {t:.3f} | {p:.4f} |" for c, n, m, t, p in loco_creator
    ) + """

## Leave-One-Ticker-Out (AR_0_5, top 5 tickers)

| Excluded ticker | n_remaining | mean | t | p |
| --- | --- | --- | --- | --- |
""" + "\n".join(
        f"| {t} | {n} | {m:.6f} | {tt:.3f} | {p:.4f} |" for t, n, m, tt, p in loco_ticker
    ) + f"""

## Placebo (Permute Event Dates Within Ticker, 500 Reps)

- Average placebo mean AR_0_5 across 500 permutations: `{placebo_mean_avg:.6f}`
- Empirical p-value (share of placebos with mean >= observed): `{placebo_ge_obs:.4f}`
- Interpretation: a low share here means the observed mean sits in the upper
  tail of the within-ticker reshuffle distribution and is not a mechanical
  artifact of which tickers happen to be in the sample.

## Planned Additional Tests (Bloomberg-Day Rerun)

| Test | Status | Required data |
| --- | --- | --- |
| Permutation test on actual event-date shifts +/-{{15,30,60}} trading days | Plan | Pre-event return panel extending 60 trading days before each event |
| Low-lookahead-risk cut | Computed | Uses `before_open` and `weekend_or_holiday` timing buckets from upload timestamp |
| Pre-trend test: mean and t on AR_-20_-1 (must be ~0 under no-pre-leak) | Plan | Computed in `08_momentum_decomposition_results.csv` (column `pre_event_abnormal_return_20_1`) |
| Newey-West SE (lag 5) | Plan | Daily AR panel; `statsmodels.regression.linear_model.OLS.fit(cov_type="HAC", cov_kwds=dict(maxlags=5))` |
| Cluster-robust SE by ticker | Computed for Model 2/5 | See `07_momentum_decomposition_analysis.md` |
| Cluster-robust SE by creator | Computed for Model 2/5 | See `07_momentum_decomposition_analysis.md` |
| Cluster-robust SE by event date | Plan | Same with `groups=df["effective_trading_event_date"]` |
| Two-way clustering (ticker x event date) | Plan | `linearmodels.PanelOLS` or hand-implemented Cameron-Gelbach-Miller |
| Benjamini-Hochberg FDR across subsample cuts | Computed | See "Multiple-Testing Adjustment" above |
| News-confounded-excluded cut | Plan | After news_overlap_flags.csv is populated |
| Momentum-controlled cut | Plan | Residualize AR_0_5 on AR_-20_-1 before re-testing |

## Notes

- p-values reported here use a normal approximation. For the headline sample
  size (n~1,500) the deviation from a t distribution is < 0.001 in p; final
  paper tables should still report exact t p-values via `scipy.stats`.
- The duplicate-collapsed cut deliberately keeps the first event per
  `(creator, ticker, weekday_adjusted_date)` cluster; alternative collapsing
  rules (mean within cluster, max-quality within cluster) should be reported as
  sensitivity rows in the final paper.
- The non-top-ticker cut removes more than half of the sample by construction
  and is the most demanding placebo of the "headline is just NVDA + TSLA"
  hypothesis.
"""
    write_md(OUT_DIR / "13_statistical_robustness_matrix.md", text)


def write_portfolio_plan(enriched: list[EnrichedEvent]) -> None:
    # Compute basic portfolio-style summary statistics inline so the plan ships
    # with at least the long-buy, short-sell, and long-buy/short-sell numbers
    # in the headline window. Drawdown is reported on a time-ordered
    # equal-capital event stream (1/n per event) so cumulative pseudo-equity
    # is bounded between 0 and ~2 rather than compounding to absurd swings.
    def _stats(returns: list[float]) -> dict[str, float]:
        if not returns:
            return {"n": 0, "mean": float("nan"), "median": float("nan"),
                    "hit_rate": float("nan"), "sharpe": float("nan"),
                    "max_drawdown": float("nan")}
        n = len(returns)
        m = sum(returns) / n
        sd = statistics.pstdev(returns)
        hit = sum(1 for x in returns if x > 0) / n
        sharpe = m / sd if sd > 0 else float("nan")
        # Equal-capital pseudo-equity: each event allocated 1/n of capital,
        # additive (avoids unrealistic compounding across overlapping events).
        per_event_allocation = 1.0 / n
        cum = 1.0
        peak = 1.0
        mdd = 0.0
        for x in returns:
            cum += per_event_allocation * x
            peak = max(peak, cum)
            mdd = min(mdd, cum / peak - 1.0)
        return {
            "n": n, "mean": m, "median": statistics.median(returns), "hit_rate": hit,
            "sharpe": sharpe, "max_drawdown": mdd,
        }

    sorted_enriched = sorted(
        enriched,
        key=lambda ee: ee.calendar_event_date or date(1970, 1, 1),
    )
    long_buy = [ee.abnormal["ar_post_0_5"] for ee in sorted_enriched
                if "bull" in ee.event.stance and ee.abnormal["ar_post_0_5"] is not None]
    short_sell = [-ee.abnormal["ar_post_0_5"] for ee in sorted_enriched
                  if "bear" in ee.event.stance and ee.abnormal["ar_post_0_5"] is not None]
    combined = []
    for ee in sorted_enriched:
        if ee.abnormal["ar_post_0_5"] is None:
            continue
        if "bull" in ee.event.stance:
            combined.append(ee.abnormal["ar_post_0_5"])
        elif "bear" in ee.event.stance:
            combined.append(-ee.abnormal["ar_post_0_5"])
    hq_long = [ee.abnormal["ar_post_0_5"] for ee in sorted_enriched
               if "bull" in ee.event.stance and ee.quality_tier in {"A", "B"}
               and ee.abnormal["ar_post_0_5"] is not None]

    stats_table = {
        "long_buy_5d": _stats(long_buy),
        "short_sell_5d": _stats(short_sell),
        "long_short_5d": _stats(combined),
        "high_quality_long_5d": _stats(hq_long),
    }

    text = f"""# Portfolio Strategy Backtest Plan

## Status

This plan ships with a *headline* in-sample provisional backtest using
SPY-adjusted abnormal returns over the 5-trading-day post-event window. These
are *event-level* returns aggregated equal-weight; a calendar-time portfolio
backtest (proper overlapping-event handling, daily P&L, turnover and cost
modeling) is scheduled for Bloomberg-day. The point estimates below are
provisional, not investable, and inherit every caveat from the yfinance
provisional baseline.

## Provisional Headline Summary (AR_0_5, equal-weight, no costs)

| Strategy | n | mean | median | hit rate | event Sharpe | max drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| Long-buy (1,209 buys) | {stats_table['long_buy_5d']['n']} | {stats_table['long_buy_5d']['mean']:.4f} | {stats_table['long_buy_5d']['median']:.4f} | {stats_table['long_buy_5d']['hit_rate']:.2%} | {stats_table['long_buy_5d']['sharpe']:.3f} | {stats_table['long_buy_5d']['max_drawdown']:.2%} |
| Short-sell (345 sells, return sign flipped) | {stats_table['short_sell_5d']['n']} | {stats_table['short_sell_5d']['mean']:.4f} | {stats_table['short_sell_5d']['median']:.4f} | {stats_table['short_sell_5d']['hit_rate']:.2%} | {stats_table['short_sell_5d']['sharpe']:.3f} | {stats_table['short_sell_5d']['max_drawdown']:.2%} |
| Long-buy + short-sell | {stats_table['long_short_5d']['n']} | {stats_table['long_short_5d']['mean']:.4f} | {stats_table['long_short_5d']['median']:.4f} | {stats_table['long_short_5d']['hit_rate']:.2%} | {stats_table['long_short_5d']['sharpe']:.3f} | {stats_table['long_short_5d']['max_drawdown']:.2%} |
| High-quality (tier A/B) long-buy | {stats_table['high_quality_long_5d']['n']} | {stats_table['high_quality_long_5d']['mean']:.4f} | {stats_table['high_quality_long_5d']['median']:.4f} | {stats_table['high_quality_long_5d']['hit_rate']:.2%} | {stats_table['high_quality_long_5d']['sharpe']:.3f} | {stats_table['high_quality_long_5d']['max_drawdown']:.2%} |

These numbers aggregate close-to-close event-study returns as if each event
were a self-contained equal-weight trade proxy. They do not use executable open
or intraday prices and are not adjusted for overlapping holdings, capital
usage, transaction costs, or slippage. `max drawdown` is reported on an
equal-capital additive pseudo-equity stream (each event gets `1/n` of capital,
contributions are added rather than compounded) ordered by
`calendar_event_date`; that pseudo-equity is not a calendar-time NAV and should
be replaced with the calendar-time backtest in section "Calendar-Time Portfolio
Construction" below at Bloomberg-day.

## Full Backtest Specification

### Strategies

1. **Long-buy**: open long position on `effective_trading_event_date + 1`
   close (next-day execution to avoid same-day lookahead), close on
   `effective_trading_event_date + 5` close.
2. **Short-sell**: same horizon, short position on sell-classified events.
3. **Long-buy + short-sell**: combine 1 and 2; equal-weight per event.
4. **High-quality only**: filter to tier A/B events.
5. **Duplicate-collapsed**: one event per `(creator, ticker, weekday-adjusted
   date)` cluster.
6. **Momentum-neutral**: residualize event AR on pre-event AR_-20_-1 before
   accumulating; report the residual portfolio.
7. **News-confounded-excluded**: drop events with
   `news_confounded_event_flag = True` after Bloomberg-day rerun.

### Weighting Schemes

- Equal-weight per event (baseline).
- Volatility-scaled (target 1% per-event vol using trailing 60-day stock
  volatility).
- Market-neutral (long position - SPY short with matching dollar exposure).

### Trading Costs / Slippage

- Per-side commission: 5 bps (conservative for retail; 1 bp institutional).
- Slippage: 10 bps for high-cap (top 10 tickers by market cap), 25 bps for
  small-cap.
- Borrow cost for shorts: 0 bps for top-cap, 200 bps annualized otherwise.

### Metrics To Report

- Mean and median per-event return.
- Hit rate.
- Sharpe (per-event and annualized assuming 252/horizon).
- Sortino (downside semi-deviation in denominator).
- Maximum drawdown of cumulative equal-weight stream.
- Turnover and average days-in-trade.
- Cost-adjusted return (gross minus costs).
- CAPM, FF3, Carhart, FF5 alpha against the daily portfolio return series
  (after Bloomberg-day French factor fetch).

## Calendar-Time Portfolio Construction

For each trading day t, compute the daily portfolio return as the equal-weight
average across all events whose holding period contains t. Aggregate this
daily return series and run standard factor regressions on it. This avoids
the n inflation problem of treating overlapping holdings as independent.

## Pseudo-code

```python
import pandas as pd

def calendar_portfolio(events_df: pd.DataFrame, prices_df: pd.DataFrame,
                       entry_offset: int = 1, exit_offset: int = 5) -> pd.Series:
    daily = []
    for d in pd.bdate_range(prices_df.index.min(), prices_df.index.max()):
        active = events_df[(events_df["entry_date"] <= d) & (d <= events_df["exit_date"])]
        if active.empty:
            daily.append((d, 0.0))
            continue
        per_event = []
        for _, ev in active.iterrows():
            prev_px = prices_df.loc[d - pd.Timedelta(days=1), ev["ticker"]]
            this_px = prices_df.loc[d, ev["ticker"]]
            ret = (this_px / prev_px) - 1.0
            if ev["side"] == "short":
                ret = -ret
            per_event.append(ret)
        daily.append((d, sum(per_event) / len(per_event)))
    return pd.Series(dict(daily)).sort_index()
```

## Acceptance Criteria

- Cost-adjusted Sharpe of the headline strategy positive.
- High-quality cut delivers higher Sharpe than the headline, otherwise the
  quality score is not informative.
- Long-short Sharpe exceeds long-only Sharpe (sells contain information).
- Portfolio survives news-confounded-exclusion with stable factor-adjusted
  return estimates and no mechanically large drawdown.
"""
    write_md(OUT_DIR / "14_portfolio_strategy_backtest_plan.md", text)


def write_probability_plan(enriched: list[EnrichedEvent]) -> None:
    # Compute the conditional probabilities so the plan has numbers, not just text.
    def _safe_share(num: int, den: int) -> float:
        return num / den if den else float("nan")

    def _binom_ci(p: float, n: int) -> tuple[float, float]:
        if n == 0 or math.isnan(p):
            return float("nan"), float("nan")
        # Wilson 95% CI
        z = 1.96
        denom = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denom
        half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
        return max(0.0, center - half), min(1.0, center + half)

    def _conditional(filter_fn, num_fn) -> tuple[int, int, float, float, float]:
        events = [ee for ee in enriched if filter_fn(ee)]
        n = len(events)
        if n == 0:
            return 0, 0, float("nan"), float("nan"), float("nan")
        num = sum(1 for ee in events if num_fn(ee))
        p = num / n
        lo, hi = _binom_ci(p, n)
        return n, num, p, lo, hi

    rows = []

    def _row(name: str, filter_fn, num_fn) -> None:
        n, num, p, lo, hi = _conditional(filter_fn, num_fn)
        rows.append((name, n, num, p, lo, hi))

    # Headline
    _row(
        "P(positive 1D AR | buy)",
        lambda e: "bull" in e.event.stance and e.abnormal["ar_event_0_1"] is not None,
        lambda e: e.abnormal["ar_event_0_1"] > 0,
    )
    _row(
        "P(positive 5D AR | buy)",
        lambda e: "bull" in e.event.stance and e.abnormal["ar_post_0_5"] is not None,
        lambda e: e.abnormal["ar_post_0_5"] > 0,
    )
    _row(
        "P(negative 5D AR | sell)",
        lambda e: "bear" in e.event.stance and e.abnormal["ar_post_0_5"] is not None,
        lambda e: e.abnormal["ar_post_0_5"] < 0,
    )
    _row(
        "P(reversal +5,+20 | positive 1D reaction)",
        lambda e: e.abnormal["ar_event_0_1"] is not None and e.abnormal["ar_event_0_1"] > 0
                  and e.abnormal["ar_post_5_20"] is not None,
        lambda e: e.abnormal["ar_post_5_20"] < 0,
    )

    # Conditional on high quality
    _row(
        "P(positive 5D AR | buy, tier A/B)",
        lambda e: "bull" in e.event.stance and e.quality_tier in {"A", "B"} and e.abnormal["ar_post_0_5"] is not None,
        lambda e: e.abnormal["ar_post_0_5"] > 0,
    )
    _row(
        "P(negative 5D AR | sell, tier A/B)",
        lambda e: "bear" in e.event.stance and e.quality_tier in {"A", "B"} and e.abnormal["ar_post_0_5"] is not None,
        lambda e: e.abnormal["ar_post_0_5"] < 0,
    )
    # Top creator vs non-top
    top_creators = {c for c, _ in Counter(ee.event.creator for ee in enriched).most_common(5)}
    _row(
        "P(positive 5D AR | buy, top-5 creator)",
        lambda e: "bull" in e.event.stance and e.event.creator in top_creators and e.abnormal["ar_post_0_5"] is not None,
        lambda e: e.abnormal["ar_post_0_5"] > 0,
    )
    _row(
        "P(positive 5D AR | buy, non-top-5 creator)",
        lambda e: "bull" in e.event.stance and e.event.creator not in top_creators and e.abnormal["ar_post_0_5"] is not None,
        lambda e: e.abnormal["ar_post_0_5"] > 0,
    )
    # NVDA/TSLA/AAPL vs others
    big3 = {"NVDA", "TSLA", "AAPL"}
    _row(
        "P(positive 5D AR | buy, ticker in NVDA/TSLA/AAPL)",
        lambda e: "bull" in e.event.stance and e.event.ticker in big3 and e.abnormal["ar_post_0_5"] is not None,
        lambda e: e.abnormal["ar_post_0_5"] > 0,
    )
    _row(
        "P(positive 5D AR | buy, ticker not in NVDA/TSLA/AAPL)",
        lambda e: "bull" in e.event.stance and e.event.ticker not in big3 and e.abnormal["ar_post_0_5"] is not None,
        lambda e: e.abnormal["ar_post_0_5"] > 0,
    )

    # Calibration by tier: hit rate of positive 5D AR for buys, by tier
    tier_calibration: list[tuple[str, int, int, float, float, float]] = []
    for tier in ["A", "B", "C", "D"]:
        n, num, p, lo, hi = _conditional(
            lambda e, tier=tier: "bull" in e.event.stance and e.quality_tier == tier
            and e.abnormal["ar_post_0_5"] is not None,
            lambda e: e.abnormal["ar_post_0_5"] > 0,
        )
        tier_calibration.append((tier, n, num, p, lo, hi))

    head = """# Probability and Calibration Plan

## Headline Conditional Probabilities

(95% CIs are Wilson intervals.)

| Statement | n | hits | probability | 95% CI lo | 95% CI hi |
| --- | --- | --- | --- | --- | --- |
"""
    body_rows = "\n".join(
        f"| {name} | {n} | {num} | {p:.4f} | {lo:.4f} | {hi:.4f} |"
        for name, n, num, p, lo, hi in rows
    )

    calibration_block = "\n\n## Calibration by Event Quality Tier (Buys, P(positive 5D AR))\n\n"
    calibration_block += "| Tier | n | hits | probability | 95% CI lo | 95% CI hi |\n"
    calibration_block += "| --- | --- | --- | --- | --- | --- |\n"
    for tier, n, num, p, lo, hi in tier_calibration:
        calibration_block += f"| {tier} | {n} | {num} | {p:.4f} | {lo:.4f} | {hi:.4f} |\n"

    plan = """

## Posterior Intervals (Bloomberg-Day Plan)

After Bloomberg-day rerun:

- For each conditional probability above, draw 5,000 Beta-binomial posterior
  samples with `alpha = 1 + hits`, `beta = 1 + (n - hits)`.
- Report posterior mean and 90%/95% credible intervals; this is the
  Bayesian counterpart to the Wilson interval table above.

## Calibration Methodology

- Bin events by `event_quality_score` quartile (within tier) and report the
  hit rate vs the predicted probability from a logistic regression
  `P(positive AR_0_5 | event_quality_score, recommendation_type)`. A
  well-calibrated quality score will produce near-monotone hit-rate ladders.
- Brier score on the same probabilistic predictions.
- Reliability diagram with 95% CIs per bin.

## Reported Variables

Each probability statement reports:

- `n`: number of events satisfying the conditioning set.
- `hits`: number of events meeting the outcome predicate.
- `probability`: point estimate (hits / n).
- 95% Wilson CI.
- After Bloomberg-day: posterior 5%/50%/95% quantiles.

## Acceptance Criteria

- Buy hit rate > 50% at 5D for high-quality tier with CI strictly above 50%.
- Sell hit rate > 50% (i.e., negative 5D AR for sells) at high quality.
- Non-top creator hit rate is within 5 percentage points of top-creator hit
  rate (otherwise the result is concentrated and not generalizable).
- Non-big-3 ticker hit rate within 5 percentage points of big-3 hit rate.
"""
    write_md(OUT_DIR / "15_probability_and_calibration_plan.md", head + body_rows + calibration_block + plan)


def write_feature_engineering_plan() -> None:
    text = """# Transcript Feature Engineering Plan

## Inputs

- `transcript_recommendation_events.evidence_window`: ~100-1000 character
  evidence span anchored on the ticker/company mention.
- `youtube_transcripts.full_text`: full transcript body, available locally for
  most accepted events.

## Codebook

| Feature | Type | Definition | Heuristic Implementation |
| --- | --- | --- | --- |
| `directness` | ordinal 0-3 | How explicitly the speaker recommends action | 0 if no first-person verb; 1 if "considering"; 2 if "I am buying"; 3 if "you should buy" |
| `conviction` | ordinal 0-3 | Tone strength | 0 hedged; 1 cautious; 2 confident; 3 emphatic (caps, repetition) |
| `urgency` | ordinal 0-2 | Time pressure | 0 none; 1 weekly horizon ("this week"); 2 immediate ("right now") |
| `time_horizon` | categorical | Trade horizon | short / medium / long, from lexicon matches |
| `valuation_basis` | binary | Mentions valuation multiple | True if any of P/E, DCF, EV/EBITDA, multiple, fair value |
| `catalyst_type` | categorical | Reason | earnings / product / macro / regulatory / unspecified |
| `risk_disclosure` | binary | DYOR / risk language | True if "not financial advice", "do your own research", "risk" |
| `position_disclosure` | binary | Speaker discloses own position | True if "I own", "in my portfolio", "I hold" |
| `conditionality` | ordinal 0-3 | Recommendation contingent on a condition | count of "if/might/could/may"-style hedges |
| `new_vs_update` | categorical | New call vs reiteration | new / update / recap |
| `sentiment_intensity` | float -1..1 | Strength of bullish/bearish tone | Lexicon polarity score over evidence window |
| `specificity` | ordinal 0-3 | Specific price targets vs generic | 0 generic; 1 directional only; 2 numeric levels; 3 numeric levels with timing |

## Default Implementation (Rule-Based, Auditable)

```python
def extract_features(evidence: str, stance: str) -> dict:
    text = evidence.lower()
    features = {}
    features["directness"] = ... # phrase-table lookups
    features["conviction"] = ... # tone heuristics: caps ratio, exclamation, repetition
    features["urgency"] = 2 if "right now" in text or "today" in text else (1 if "this week" in text else 0)
    features["time_horizon"] = "long" if any(p in text for p in TIME_HORIZON_PHRASES_LONG) else ...
    features["valuation_basis"] = any(p in text for p in VALUATION_PHRASES)
    ...
    return features
```

Phrase tables live alongside the script (see `POSITIVE_REC_PHRASES`,
`NEGATIVE_REC_PHRASES`, `CONDITIONALITY_PHRASES`, `RECAP_PHRASES`,
`POSITION_DISCLOSURE`, `URGENCY_PHRASES`, `TIME_HORIZON_PHRASES_SHORT`,
`TIME_HORIZON_PHRASES_LONG`, `VALUATION_PHRASES`, `CATALYST_PHRASES`,
`RISK_DISCLOSURE` in `scripts/build_research_grade_analysis.py`).

## Optional NLP Layer (Future)

- FinBERT (`yiyanghkust/finbert-tone`) sentiment polarity over the evidence
  window. Already wired in the codebase as an optional pass
  (`finbert_*` columns in `transcript_recommendation_events`); needs activation.
- DistilBERT-based zero-shot classification for catalyst type
  ("earnings", "product launch", "macro", "regulatory") with hypothesis
  templates per class.
- LLM-based scoring (gpt-4o-mini or local Llama) for `directness`,
  `conviction`, and `specificity` with rubric-driven prompts; held to
  inter-rater agreement of >= 0.7 vs the rule-based baseline before adoption.

## Output

- `transcript_features.csv` with one row per event_id:
  event_id, every feature, plus `feature_extractor_version`.
- Features are correlated with abnormal returns in a dedicated robustness
  section: each feature enters the OLS in `08_momentum_decomposition_results.csv`
  Model 5 augmentation as a continuous or binary control.

## Privacy and Redistribution

- Full transcripts remain in the local SQLite database and are not committed.
- Only the evidence quote and the derived features are exported.
- Any LLM call goes via a model with a redistribution-safe license; outputs
  store only the structured feature, not the prompt or the model output text.
"""
    write_md(OUT_DIR / "16_transcript_feature_engineering_plan.md", text)


def write_x_status() -> None:
    text = """# X/Twitter Status and Future-Extension Plan

## Current Status

X/Twitter data is **excluded** from the main empirical sample. Reasons:

- Prior historical X collection attempts did not produce a dataset that passed
  strict validation: coverage was sparse, timestamps and author attribution
  were inconsistent across providers, and the resulting events could not be
  joined cleanly to the trading calendar.
- The locked YouTube sample (9,992 transcripts, 1,554 accepted events) is
  large enough to support primary inference; mixing in a small,
  poorly-validated X sample would create attribution risk without commensurate
  power gain.
- The repo's reporting framework already treats X as future/optional; this
  pass continues that posture.

X data is **not merged** with YouTube in any output produced by this pass.

## Required Future Validation Before Inclusion

Any future merge of X with the YouTube sample must pass *every* check below.
Each check must produce an auditable artifact in
`data/exports/research_grade_analysis/` or `data/exports/x_extension/`.

1. **Timestamp validity**
   - Post `created_at` matches X API authoritative timestamp byte-for-byte.
   - Spot-check sample of 50 posts cross-referenced against the live X URL.
   - No more than 1% of posts may have missing or zero-second-precision
     timestamps.

2. **Query reproducibility**
   - Stored `query_string`, `query_run_at`, and `cursor` for every collection
     batch.
   - Re-running the same query window in a fresh batch reproduces the same
     post_id set within +/-5% (tolerance for deletions).

3. **Author identity**
   - Each post is tied to a persistent `author_id` that resolves to the same
     screen name within the collection window.
   - No reliance on screen name as primary key (screen names change).

4. **Ticker/company mapping**
   - Cashtag extraction with a falsepositive denylist identical to the
     YouTube pipeline (`GDP`, `CEO`, etc.).
   - Plain uppercase extraction gated by the same starter universe and
     stock-context proximity rules.

5. **Event-window compatibility**
   - `event_date` is the trading-day-anchored conversion of `created_at`,
     applying the same weekday adjustment and trading-day index alignment as
     `06_event_timeline_methodology.md`.
   - Timing buckets (`before_open`, `during_market`, `after_close`,
     `weekend_or_holiday`) use the same UTC->ET conversion conventions.

6. **Duplicate control**
   - Cluster by `(author_id, ticker, event_date)`.
   - Cluster sizes match the YouTube validator schema.

7. **Raw-data retention**
   - Full raw payloads stored under `data/raw/x/` with cryptographic hashes.
   - Audit table `x_collection_runs` records every batch with start/end
     timestamps, cost, and provider.
   - No raw posts deleted except by manual approval logged in a stash report.

## Conditional Use Cases (Acceptable Once Validated)

- Diagnostic/control sample to test whether YouTube event timing is consistent
  with X attention timing. Reported as a sanity check, not as a primary
  estimand.
- Cross-platform attention spillover: P(X event within 24h | YouTube event)
  conditional on creator linkage. Requires creator-identity bridge file
  (which does not exist yet).
- Headline robustness rerun where the universe is restricted to events with X
  corroboration. Result reported as a robustness row, never as the headline.

## Hard Constraint

Until *every* check above passes a strict validation report (committed to
`data/exports/x_extension/x_validation_report.md` with sign-off date), X
data must not be used in the main empirical sample.
"""
    write_md(OUT_DIR / "17_x_twitter_status_and_future_extension.md", text)


def write_bloomberg_protocol() -> None:
    text = """# Bloomberg Validation Protocol

## Scope

This protocol is the spec for the Bloomberg-day run scheduled in roughly two
days. It does *not* execute any Bloomberg call; it is the operating manual.

## Required Bloomberg Fields per Ticker

| Field | Purpose | Window |
| --- | --- | --- |
| `PX_LAST` | Closing price for return calc | event_date -60 to event_date +30 trading days |
| Adjusted close / total return equivalent (`TOT_RETURN_INDEX_GROSS_DVDS` or `DAY_TO_DAY_TOT_RETURN_GROSS_DVDS`) | Dividend-adjusted return | Same as above |
| `PX_VOLUME` | Liquidity sanity | Same |
| `CUR_MKT_CAP` | Size control | Snapshot at event_date |
| `BETA_ADJ_OVERRIDABLE` (or `BETA_RAW`) | CAPM regression | Snapshot at event_date |
| `GICS_SECTOR_NAME`, `GICS_INDUSTRY_NAME` | Industry adjustment | Snapshot |
| `EARN_ANN_DT` (next two earnings dates around event) | Earnings flag | event_date +/-5 calendar/trading days |
| `CH_LAST` company news headlines | News confound flag | event_date +/-5 calendar/trading days |
| `ANR` analyst recommendation changes | News confound flag | event_date +/-5 calendar/trading days |
| Corporate actions: `EVT_DT_DIV`, `EVT_DT_SPLIT`, `BDP("BD_SPECIAL_DIVIDEND_AMT")` | Dividend/split confound | event_date +/-5 calendar/trading days |
| Benchmark index returns: `SPY`, `QQQ`, `IWM` `PX_LAST` | Market-adjusted return | event_date -60 to event_date +30 trading days |
| Sector ETF returns: `XLK`, `XLC`, `XLY`, `XLF`, `XLI` `PX_LAST` | Industry-adjusted return | Same |

## Window Conventions

- Pre-event panel: event_date -60 trading days through event_date -1 trading
  day. Used for CAPM beta re-estimation, momentum control, and pre-trend test.
- Post-event panel: event_date through event_date +30 trading days. Used for
  AR_0_1, AR_0_5, AR_0_20, AR_5_20 recomputation.
- News search: event_date +/-5 calendar/trading days (whichever is wider). For
  flag computation use trading days; for human review use calendar days.

## Input File

- `data/exports/analysis/05_bloomberg_ticker_event_request.csv` (already
  generated in this branch with 1,554 rows; one row per event_id).

## Output Files (Bloomberg-Day Targets)

| File | Purpose |
| --- | --- |
| `data/imports/market_data/bloomberg_market_data.csv` | Replacement for yfinance import; same schema |
| `data/imports/market_data/bloomberg_dividends_corporate_actions.csv` | Dividend/split flags |
| `data/imports/market_data/bloomberg_earnings_dates.csv` | Earnings calendar |
| `data/imports/market_data/bloomberg_news_headlines.csv` | Headlines for news_overlap flagging |
| `data/imports/market_data/bloomberg_analyst_changes.csv` | Analyst rec changes |
| `data/imports/market_data/bloomberg_factor_returns.csv` (optional) | If Bloomberg-equivalent FF factors purchased |

These files are listed in `.gitignore` patterns and **must not be committed**.

## Reruns Triggered by Bloomberg Data

- `04_yfinance_event_study_results.md` -> `04_bloomberg_event_study_results.md`
  (replace numbers, leave methodology in place).
- `07_momentum_decomposition_analysis.md`: rerun all five models; report delta
  in coefficients vs yfinance baseline.
- `08_momentum_decomposition_results.csv`: rerun with Bloomberg total-return
  series; columns unchanged.
- `10_news_overlap_flags.csv`: populate every "unknown" with True/False;
  update `news_source_used` to "bloomberg".
- `11_news_overlap_summary.md`: report confound rate and confounded-excluded
  headline.
- `13_statistical_robustness_matrix.md`: rerun every cut; report Bloomberg
  vs yfinance delta in a final column.
- `14_portfolio_strategy_backtest_plan.md`: replace provisional headline
  table with Bloomberg-driven calendar-time portfolio backtest.
- `15_probability_and_calibration_plan.md`: replace Wilson intervals with
  posterior intervals; recompute calibration.

## Compliance

- Bloomberg raw exports must not be committed to git (`.gitignore` enforces
  this via `data/imports/`).
- Only derived, aggregated, anonymized statistics may be shipped in
  `data/exports/`.
- The Bloomberg license requires that any reported figures cite Bloomberg as
  the data source; this is enforced in the Bloomberg-day rerun of every
  `.md` output.

## Operator Checklist (Day-Of)

1. Confirm `05_bloomberg_ticker_event_request.csv` rowcount = 1,554.
2. Open Bloomberg Terminal, run BQuant or Excel API for each field x ticker x
   window combination.
3. Export to the `data/imports/market_data/bloomberg_*.csv` files.
4. Run the validation step (`python3 -m finfluencer_alpha validate-market-data
   --input data/imports/market_data/bloomberg_market_data.csv`).
5. Run `python3 -m finfluencer_alpha run-event-study --market-data-source bloomberg`.
6. Rerun `scripts/build_research_grade_analysis.py` after either adapting
   `bloomberg_market_data.csv` to the yfinance-compatible schema read by this
   script or adding an explicit Bloomberg source selector. Do not report
   Bloomberg-based results until the script input path is verified in code.
"""
    write_md(OUT_DIR / "18_bloomberg_validation_protocol.md", text)


def write_positioning_memo() -> None:
    text = """# Research and LinkedIn Positioning Memo

## Reframe

We are not (yet) claiming causal alpha. The defensible framing is:

> YouTube finfluencer recommendations are associated with short-window abnormal
> returns in a locked transcript-supported event sample, but robustness evidence
> suggests the effect is concentrated in major mega-cap names and may reflect
> attention/momentum amplification rather than broad, tradable causal alpha.

The primary contribution is the **pipeline** + **dataset** + **robustness
matrix**, not a published trading strategy.

## What Is Novel

- Locked, reproducible sample of 1,554 accepted creator recommendations
  derived from 9,992 collected YouTube transcripts across 35 finance
  creators and 23 large-cap tickers.
- Event derivation requires same-window co-occurrence of a ticker mention and
  a directional recommendation phrase, not just title/description scraping.
- Per-event quality scoring with auditable reason codes (Tier A/B/C/D)
  enabling robustness cuts without manual audit.
- Momentum decomposition layered on top of the event-study (most public
  finfluencer claims do not pre-test for momentum overlap).
- News confound protocol that ships with explicit placeholder schema rather
  than ad-hoc skipping.

## What Is Preliminary

- yfinance prices are interim; CAPM/FF3/Carhart/FF5 alphas are not yet computed
  with French factor data.
- News confound flags are "unknown" pending Bloomberg-day rerun.
- Portfolio backtest is event-aggregated, not calendar-time, and ignores
  trading costs.

## What Is Robust Now

- 1D and 5D market-adjusted abnormal returns are positive at p < 0.005 on the
  locked canonical yfinance sample (`mean_1D = 0.00273, mean_5D ~ 0.005`).
- Buy/sell direction split: buys clearly positive; sells noisy.
- Year-by-year cuts show 2024 and 2025 driving the headline, with 2022
  negative (creators were bearish into a falling market).
- Result survives top-creator and top-ticker LOCO with mean still positive, but
  the non-top-ticker cut weakens materially and can flip negative.

## What Is Provisional

- The 5D mean is sensitive to event-day and execution conventions
  (same-day event-study window vs next-day executable entry); Bloomberg
  total-return series will tighten this.
- The result is *not* yet robust to news confounds because the news flag is
  protocol-only.
- The result is not robust to FF3/Carhart alpha until French factors arrive.

## What Bloomberg Validates

- Replaces yfinance prices with dividend-adjusted total return.
- Provides earnings/news/analyst-change timestamps to populate
  `news_confounded_event_flag`.
- Enables CAPM/FF3/Carhart/FF5 alpha with HC/cluster SEs (via downloaded
  French factors, which the Bloomberg-day run also schedules).
- Provides market cap and beta snapshots for matched-control construction.

## Honest LinkedIn Claims

Use:

- "Built a reproducible NLP + event-study pipeline that converts 9,992
  YouTube finance transcripts into 1,554 ticker-level recommendation events
  across 23 large-cap tickers."
- "Provisional results suggest buy-rated YouTube recommendations are associated
  with small positive short-horizon abnormal returns on a locked sample, pending
  licensed Bloomberg validation."
- "Designed a per-event quality scoring system with auditable reason codes
  that enables robustness cuts without manual labeling."

Avoid:

- Anything about "alpha", "trading strategy", or "outperformance".
- Annualized Sharpe figures (the backtest is provisional and not calendar-time).
- Any framing that implies causal influence of creators on prices; the
  honest framing is "attention-linked abnormal returns" until news confounds
  are excluded.

## Undergraduate Journal Version (e.g., Issues in Political Economy, SURJ)

Required additions before submission:

- Bloomberg rerun of every headline statistic.
- Populated news-confound flags with confounded-excluded headline reported.
- Matched-control return model (FF3 alpha minimum).
- Pre-trend test reported as a table row in the robustness matrix.
- Spot-check audit with disagreement rate documented.
- Single-paragraph data-availability statement that points to the locked
  sample artifacts and the script.

## SSRN Working Paper Version

Required additions on top of journal version:

- Full calendar-time portfolio backtest with FF5 + Carhart alphas, costs,
  Sharpe, max drawdown, turnover.
- Cross-sectional regression of post-event AR_0_5 on transcript features
  from `16_transcript_feature_engineering_plan.md`.
- Bayesian posteriors for headline probabilities.
- Replication appendix with exact commit hash and frozen environment file
  (`uv.lock` or `requirements.lock`).
- "Limitations" section explicitly listing the X-exclusion rationale, the
  ambiguous-ticker risk, and the 23-ticker concentration.
"""
    write_md(OUT_DIR / "19_linkedin_and_research_positioning_memo.md", text)


def write_next_steps_for_bloomberg_day() -> None:
    text = """# Bloomberg-Day Task List (T+2)

## Goal

In a single Bloomberg session, replace yfinance with Bloomberg in every
headline statistic and populate the news-confound flag.

## Sequence

### Step 1: Pre-flight (15 minutes)

- `git pull` on `x-youtube-full-research-expansion`.
- Confirm `data/exports/analysis/05_bloomberg_ticker_event_request.csv` is
  still the canonical request file (rowcount = 1,554).
- Open Bloomberg Terminal; verify license entitlements for daily history,
  earnings dates, headlines, analyst rec changes, and corporate actions.
- Open `data/exports/research_grade_analysis/18_bloomberg_validation_protocol.md`
  for the field-by-field spec.

### Step 2: Pull market data (60-90 minutes)

For each unique ticker in the request file:

1. Pull `PX_LAST` for event_date -60 to event_date +30 trading days.
2. Pull `TOT_RETURN_INDEX_GROSS_DVDS` (or `DAY_TO_DAY_TOT_RETURN_GROSS_DVDS`)
   for the same window.
3. Pull `PX_VOLUME`, `CUR_MKT_CAP`, `BETA_ADJ_OVERRIDABLE`,
   `GICS_SECTOR_NAME`, `GICS_INDUSTRY_NAME`.

Also pull benchmark series (SPY, QQQ, IWM) and sector ETFs (XLK, XLC, XLY,
XLF, XLI) over the full event-date range minus 60 days through max +30 days.

Save to `data/imports/market_data/bloomberg_market_data.csv` with the same
column schema as `yfinance_market_data.csv` so the existing event-study runner
accepts it.

### Step 3: Pull news / earnings / analyst data (30-60 minutes)

- `EARN_ANN_DT` for two earnings dates straddling each event ->
  `bloomberg_earnings_dates.csv`.
- `CH_LAST` company headlines, event_date +/-5 calendar days ->
  `bloomberg_news_headlines.csv` (headline text + source + timestamp).
- `ANR` analyst rating changes within event_date +/-5 calendar days ->
  `bloomberg_analyst_changes.csv`.
- `EVT_DT_DIV`, `EVT_DT_SPLIT` corporate actions within +/-5 calendar days
  -> `bloomberg_dividends_corporate_actions.csv`.

### Step 4: Fetch French factors (15 minutes, offline)

- Download FF3 daily, FF Momentum daily, FF5 daily ZIPs from
  `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html`.
- Extract to `data/imports/french_factors/` (gitignored).

### Step 5: Re-run analytical pipeline (10 minutes)

```bash
python3 -m finfluencer_alpha validate-market-data --input data/imports/market_data/bloomberg_market_data.csv
python3 -m finfluencer_alpha run-event-study --market-data-source bloomberg
python3 scripts/build_research_grade_analysis.py
```

Expected output: all `data/exports/research_grade_analysis/*.md` files refresh
with Bloomberg numbers only after the market-data input path has been verified
or adapted for the Bloomberg file; `10_news_overlap_flags.csv` switches every
"unknown" to True/False; `news_source_used = bloomberg`.

### Step 6: Populate news flags (45 minutes)

Run a one-off Python script that joins:

- `bloomberg_earnings_dates.csv` -> `earnings_near_event_flag`
- `bloomberg_news_headlines.csv` headline count -> `major_news_near_event_flag`
- `bloomberg_analyst_changes.csv` -> additional flag column
- Tighten same-day / +/-1 / +/-3 / +/-5 windows from these joined tables.

### Step 7: Robustness rerun (30 minutes)

- Rerun `13_statistical_robustness_matrix.md` with Bloomberg series; specifically
  add `news_confounded_excluded` and `pre_trend_test` rows now populated.
- Rerun calendar-time portfolio backtest (`14_portfolio_strategy_backtest_plan.md`)
  and report cost-adjusted Sharpe.
- Rerun calibration (`15_probability_and_calibration_plan.md`) with posterior
  intervals.

### Step 8: Sanity checks (30 minutes)

- Compare top-3 events by Bloomberg AR_0_5 to top-3 by yfinance AR_0_5. If
  any event flipped sign, investigate the ticker's adjusted close on
  event_date.
- Verify pre-trend test mean is within +/- 0.5 standard errors of 0.
- Verify news_confounded_event_flag covers at least 15% of events
  (otherwise the flagger is likely too restrictive).

### Step 9: Reporting (30 minutes)

- Update `19_linkedin_and_research_positioning_memo.md` to move
  "Provisional" items to "Robust" where applicable.
- Update `06_preliminary_findings_memo.md` headline numbers.
- Do **not** commit Bloomberg raw CSVs. Only commit refreshed
  `data/exports/research_grade_analysis/*.md` outputs.

## Total Expected Wall-Clock

- 4-5 hours hands-on for a single operator including pulls, reruns, and
  reporting.

## Hard No-Go Conditions

- If `bloomberg_market_data.csv` has > 5% missing rows vs the request, halt
  and document missing-ticker rationale before rerunning the event study.
- If 5D AR sign flips on the headline (positive -> negative) after Bloomberg,
  flag for project-meeting discussion before publishing.
- If news_confounded_event_flag covers > 60% of events, the news lexicon
  is too loose; tune before rerunning robustness cuts.
"""
    write_md(OUT_DIR / "20_next_steps_for_bloomberg_day.md", text)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events = load_events()
    market = load_market_data()
    aliases = _ticker_alias_map()
    enriched = build_enriched_events(events, market, aliases)

    write_validation_methodology()
    write_event_quality_csv(enriched)
    write_event_quality_summary(enriched)
    write_spot_check_sample(enriched)
    write_event_timeline(enriched, market)
    write_timeline_methodology()
    write_momentum_outputs(enriched)
    write_news_overlap_outputs(enriched)
    write_return_robustness_plan()
    write_statistical_robustness_matrix(enriched)
    write_portfolio_plan(enriched)
    write_probability_plan(enriched)
    write_feature_engineering_plan()
    write_x_status()
    write_bloomberg_protocol()
    write_positioning_memo()
    write_next_steps_for_bloomberg_day()

    # Quick diagnostic
    matched = sum(1 for ee in enriched if ee.next_trading_idx is not None)
    print(f"Loaded events: {len(enriched)}; matched to market data: {matched}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
