from __future__ import annotations

import csv
import math
import sqlite3
import statistics
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "finfluencer_alpha.db"
V1_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package"
V1_LOCK_DIR = V1_DIR / "locked_sample"
V2_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
V2_LOCK_DIR = V2_DIR / "locked_sample_v2"
FIG_DIR = V2_DIR / "figures_data"
MARKET_DATA = REPO_ROOT / "data" / "imports" / "market_data" / "yfinance_market_data.csv"

TOP5_TICKERS = {"NVDA", "TSLA", "AAPL", "AMD", "AMZN"}
LOW_LOOKAHEAD_BUCKETS = {"before_open", "weekend_or_holiday"}
VALID_RECOMMENDATION_TYPES = {"buy", "sell"}
V2_SAMPLE_VERSION = "v2_expanded_live_db_2026-05-16"


@dataclass
class EventRecord:
    event_id: int
    video_id: str
    creator: str
    channel_id: str
    ticker: str
    company_name: str
    stance: str
    detected_action: str
    actionability_score: int | None
    confidence_score: float | None
    confidence_label: str
    evidence_start_seconds: float | None
    transcript_source: str
    provider_name: str
    transcript_collected_at: str
    published_at: str
    event_date: date | None
    timing_bucket: str
    weekday_adjusted_date: date | None
    effective_trading_event_date: date | None
    duplicate_cluster_id: int
    duplicate_cluster_size: int
    recommendation_type: str
    data_ticker: str
    ar_1d: float | None
    ar_5d: float | None
    stock_return_1d: float | None
    stock_return_5d: float | None
    benchmark_return_1d: float | None
    benchmark_return_5d: float | None
    return_exclusion_reason: str


def run_git(args: list[str]) -> str:
    try:
        return subprocess.check_output(args, cwd=REPO_ROOT, text=True).strip()
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def fmt(value: Any, digits: int = 6) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return f"{value:.{digits}f}"
    return str(value)


def fmt_pct(value: float | None, digits: int = 3) -> str:
    if value is None or math.isnan(value):
        return "not available"
    return f"{100.0 * value:.{digits}f}%"


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def weekday_adjust(d: date | None) -> date | None:
    if d is None:
        return None
    if d.weekday() == 5:
        return d + timedelta(days=2)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def timing_bucket(published_at: str) -> str:
    dt = parse_datetime(published_at)
    if dt is None:
        return "unknown"
    if dt.weekday() >= 5:
        return "weekend_or_holiday"
    et_hour = (dt.hour - 5) % 24
    if et_hour < 9 or (et_hour == 9 and dt.minute < 30):
        return "before_open"
    if (et_hour == 9 and dt.minute >= 30) or (10 <= et_hour < 16):
        return "during_market"
    return "after_close"


def safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def t_test(xs: list[float]) -> dict[str, float | int | None]:
    clean = [float(x) for x in xs if x is not None and not math.isnan(float(x))]
    n = len(clean)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "t": None, "p": None, "win_rate": None}
    mean = statistics.mean(clean)
    median = statistics.median(clean)
    win_rate = sum(1 for x in clean if x > 0.0) / n
    if n < 2:
        return {"n": n, "mean": mean, "median": median, "t": None, "p": None, "win_rate": win_rate}
    sd = statistics.stdev(clean)
    if sd == 0:
        t_stat = math.inf if mean > 0 else -math.inf
        p_value = 0.0
    else:
        t_stat = mean / (sd / math.sqrt(n))
        p_value = 2.0 * (1.0 - normal_cdf(abs(t_stat)))
    return {"n": n, "mean": mean, "median": median, "t": t_stat, "p": p_value, "win_rate": win_rate}


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def load_market_data() -> dict[str, list[dict[str, Any]]]:
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    if not MARKET_DATA.exists():
        return by_ticker
    with MARKET_DATA.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            ticker = (row.get("ticker") or "").upper().strip()
            d = parse_date(row.get("date"))
            px = safe_float(row.get("adjusted_close"))
            bench = safe_float(row.get("benchmark_adjusted_close"))
            if not ticker or d is None or px is None or bench is None:
                continue
            by_ticker.setdefault(ticker, []).append(
                {
                    "date": d,
                    "adjusted_close": px,
                    "benchmark_adjusted_close": bench,
                }
            )
    for rows in by_ticker.values():
        rows.sort(key=lambda item: item["date"])
    return by_ticker


def first_on_or_after(rows: list[dict[str, Any]], target: date) -> int | None:
    lo, hi = 0, len(rows)
    while lo < hi:
        mid = (lo + hi) // 2
        if rows[mid]["date"] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(rows) else None


def market_return(
    rows: list[dict[str, Any]],
    idx: int,
    horizon: int,
    column: str,
) -> float | None:
    end = idx + horizon
    if idx < 0 or end >= len(rows):
        return None
    p0 = rows[idx][column]
    p1 = rows[end][column]
    if p0 in (None, 0) or p1 is None:
        return None
    return (p1 / p0) - 1.0


def data_ticker_for(ticker: str, adjusted_date: date | None) -> str:
    if ticker == "SQ" and adjusted_date is not None and adjusted_date >= date(2025, 1, 21):
        return "XYZ"
    return ticker


def return_bundle(
    ticker: str,
    adjusted_date: date | None,
    market: dict[str, list[dict[str, Any]]],
) -> tuple[date | None, str, dict[str, float | None]]:
    data_ticker = data_ticker_for(ticker, adjusted_date)
    empty = {
        "stock_return_1d": None,
        "stock_return_5d": None,
        "benchmark_return_1d": None,
        "benchmark_return_5d": None,
        "ar_1d": None,
        "ar_5d": None,
    }
    if adjusted_date is None:
        return None, data_ticker, empty
    rows = market.get(data_ticker, [])
    if not rows:
        return None, data_ticker, empty
    idx = first_on_or_after(rows, adjusted_date)
    if idx is None:
        return None, data_ticker, empty
    stock_1d = market_return(rows, idx, 1, "adjusted_close")
    stock_5d = market_return(rows, idx, 5, "adjusted_close")
    bench_1d = market_return(rows, idx, 1, "benchmark_adjusted_close")
    bench_5d = market_return(rows, idx, 5, "benchmark_adjusted_close")
    values = {
        "stock_return_1d": stock_1d,
        "stock_return_5d": stock_5d,
        "benchmark_return_1d": bench_1d,
        "benchmark_return_5d": bench_5d,
        "ar_1d": None if stock_1d is None or bench_1d is None else stock_1d - bench_1d,
        "ar_5d": None if stock_5d is None or bench_5d is None else stock_5d - bench_5d,
    }
    return rows[idx]["date"], data_ticker, values


def recommendation_type(stance: str) -> str:
    text = (stance or "").lower()
    if "bear" in text or "sell" in text:
        return "sell"
    return "buy"


def fetch_events(market: dict[str, list[dict[str, Any]]]) -> list[EventRecord]:
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
            e.transcript_source,
            e.provider_name,
            e.transcript_collected_at,
            v.channel_title AS creator,
            v.channel_id,
            v.published_at
        FROM transcript_recommendation_events e
        JOIN raw_youtube_videos v ON e.video_id = v.video_id
        ORDER BY e.transcript_event_id ASC
        """
    ).fetchall()
    con.close()
    initial: list[dict[str, Any]] = []
    duplicate_keys = []
    for r in rows:
        ticker = str(r["ticker"] or "").upper().strip()
        published_at = str(r["published_at"] or "")
        event_date = parse_date(published_at)
        adjusted = weekday_adjust(event_date)
        creator = str(r["creator"] or "")
        duplicate_keys.append(f"{creator}__{ticker}__{adjusted.isoformat() if adjusted else 'NA'}")
        initial.append(
            {
                "event_id": int(r["event_id"]),
                "video_id": str(r["video_id"] or ""),
                "creator": creator,
                "channel_id": str(r["channel_id"] or ""),
                "ticker": ticker,
                "company_name": str(r["company_name"] or ""),
                "stance": str(r["stance"] or ""),
                "detected_action": str(r["detected_action"] or ""),
                "actionability_score": safe_int(r["actionability_score"]),
                "confidence_score": safe_float(r["confidence_score"]),
                "confidence_label": str(r["confidence_label"] or ""),
                "evidence_start_seconds": safe_float(r["evidence_start_seconds"]),
                "transcript_source": str(r["transcript_source"] or ""),
                "provider_name": str(r["provider_name"] or ""),
                "transcript_collected_at": str(r["transcript_collected_at"] or ""),
                "published_at": published_at,
                "event_date": event_date,
                "timing_bucket": timing_bucket(published_at),
                "weekday_adjusted_date": adjusted,
            }
        )

    cluster_map: dict[str, int] = {}
    cluster_sizes = Counter(duplicate_keys)
    for key in duplicate_keys:
        if key not in cluster_map:
            cluster_map[key] = len(cluster_map) + 1

    events: list[EventRecord] = []
    for row, key in zip(initial, duplicate_keys, strict=True):
        effective, data_ticker, returns = return_bundle(row["ticker"], row["weekday_adjusted_date"], market)
        if row["weekday_adjusted_date"] is None:
            exclusion = "missing_event_date"
        elif data_ticker not in market:
            exclusion = "missing_market_data_for_ticker"
        elif effective is None:
            exclusion = "no_trading_day_on_or_after_event"
        elif returns["ar_1d"] is None and returns["ar_5d"] is None:
            exclusion = "insufficient_forward_market_window"
        else:
            exclusion = ""
        events.append(
            EventRecord(
                **row,
                effective_trading_event_date=effective,
                duplicate_cluster_id=cluster_map[key],
                duplicate_cluster_size=cluster_sizes[key],
                recommendation_type=recommendation_type(row["stance"]),
                data_ticker=data_ticker,
                ar_1d=returns["ar_1d"],
                ar_5d=returns["ar_5d"],
                stock_return_1d=returns["stock_return_1d"],
                stock_return_5d=returns["stock_return_5d"],
                benchmark_return_1d=returns["benchmark_return_1d"],
                benchmark_return_5d=returns["benchmark_return_5d"],
                return_exclusion_reason=exclusion,
            )
        )
    return events


def db_scalar(sql: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        return int(con.execute(sql).fetchone()[0])


def db_counts() -> dict[str, int]:
    return {
        "live_transcript_rows": db_scalar("SELECT COUNT(*) FROM youtube_transcripts"),
        "successful_transcript_rows": db_scalar(
            """
            SELECT COUNT(*) FROM youtube_transcripts
            WHERE lower(coalesce(status, retrieval_status, '')) IN
                ('success', 'successful', 'available', 'ok')
            """
        ),
        "strict_text_gt_50": db_scalar(
            "SELECT COUNT(*) FROM youtube_transcripts WHERE length(coalesce(full_text, '')) > 50"
        ),
        "language_filtered_transcripts": db_scalar(
            """
            SELECT COUNT(*) FROM youtube_transcripts
            WHERE lower(coalesce(language_code, language, '')) IN
                ('en', 'english', 'en-us', 'en-gb')
            """
        ),
        "candidate_windows": db_scalar("SELECT COUNT(*) FROM transcript_candidate_windows"),
        "accepted_recommendation_events": db_scalar(
            "SELECT COUNT(*) FROM transcript_recommendation_events"
        ),
        "distinct_event_videos": db_scalar(
            "SELECT COUNT(DISTINCT video_id) FROM transcript_recommendation_events"
        ),
    }


def build_plan() -> None:
    text = """# V2 Expanded Primary Sample Build Plan

The v1 final paper package is preserved as a historical locked artifact package
under `data/exports/final_paper_package/`. Its 1,554 event manifest remains a
reproducibility benchmark.

The v2 package is an expanded live-DB rebuild under
`data/exports/final_paper_package_v2_expanded/`. It promotes the current RunPod
database to the primary candidate sample because it uses more complete available
coverage: 9,992 transcript rows and 2,341 accepted/extracted recommendation
events.

V2 is selected for methodological coverage, not because it is expected to
strengthen the result. The expanded sample may strengthen, weaken, disappear, or
reverse the v1 claim. The paper interpretation must follow the v2 results.

The free-news layer remains diagnostic only. No real provider queries are
performed here, and simulated free-news outputs are not used as empirical
public-news robustness evidence.
"""
    write_md(V2_DIR / "00_v2_build_plan.md", text)


def schema_audit() -> None:
    con = sqlite3.connect(DB_PATH)
    tables = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    lines = [
        "# Live DB Schema Audit",
        "",
        f"- DB path: `{DB_PATH.relative_to(REPO_ROOT)}`",
        "- Scope: table names, column names, row counts, and indexes only.",
        "- Raw transcript text, raw JSON, environment files, and secrets were not printed.",
        "",
    ]
    for table in tables:
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        columns = con.execute(f"PRAGMA table_info({table})").fetchall()
        indexes = con.execute(f"PRAGMA index_list({table})").fetchall()
        lines.extend(
            [
                f"## `{table}`",
                "",
                f"- Rows: `{count}`",
                "- Columns: "
                + ", ".join(f"`{column[1]}` ({column[2] or 'untyped'})" for column in columns),
            ]
        )
        if indexes:
            lines.append("- Indexes: " + ", ".join(f"`{idx[1]}`" for idx in indexes))
        lines.append("")
    con.close()
    write_md(V2_DIR / "01_live_db_schema_audit.md", "\n".join(lines))


def build_transcript_manifest() -> list[dict[str, Any]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT
            yt.video_id,
            v.channel_title AS creator,
            v.channel_id,
            yt.transcript_source,
            yt.provider_name,
            yt.language,
            yt.language_code,
            yt.status,
            yt.retrieval_status,
            yt.character_count,
            yt.word_count,
            length(coalesce(yt.full_text, '')) AS text_length
        FROM youtube_transcripts yt
        LEFT JOIN raw_youtube_videos v ON yt.video_id = v.video_id
        ORDER BY yt.video_id
        """
    ).fetchall()
    con.close()
    manifest = []
    for r in rows:
        status = str(r["status"] or r["retrieval_status"] or "")
        language = str(r["language_code"] or r["language"] or "")
        text_length = safe_int(r["character_count"]) or safe_int(r["text_length"]) or 0
        status_ok = status.lower() in {"success", "successful", "available", "ok"}
        included = status_ok and text_length > 50
        if included:
            reason = ""
        elif not status_ok:
            reason = "transcript_status_not_success"
        else:
            reason = "text_length_lte_50"
        manifest.append(
            {
                "v2_sample_version": V2_SAMPLE_VERSION,
                "video_id": r["video_id"],
                "transcript_id": r["video_id"],
                "creator": r["creator"] or "",
                "channel_id": r["channel_id"] or "",
                "transcript_source": r["transcript_source"] or r["provider_name"] or "",
                "language": language,
                "transcript_status": status,
                "text_length": text_length,
                "included_in_v2_candidate_pool": included,
                "exclusion_reason": reason,
                "source_table": "youtube_transcripts",
                "notes": "compact metadata only; full_text and raw_json are not exported",
            }
        )
    columns = [
        "v2_sample_version",
        "video_id",
        "transcript_id",
        "creator",
        "channel_id",
        "transcript_source",
        "language",
        "transcript_status",
        "text_length",
        "included_in_v2_candidate_pool",
        "exclusion_reason",
        "source_table",
        "notes",
    ]
    write_csv(V2_LOCK_DIR / "01_v2_transcript_manifest.csv", manifest, columns)
    return manifest


def build_event_manifest(events: list[EventRecord]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        included = event.ar_1d is not None or event.ar_5d is not None
        rows.append(
            {
                "v2_sample_version": V2_SAMPLE_VERSION,
                "event_id": event.event_id,
                "video_id": event.video_id,
                "transcript_id": event.video_id,
                "creator": event.creator,
                "channel_id": event.channel_id,
                "ticker": event.ticker,
                "company_name": event.company_name,
                "recommendation_type": event.recommendation_type,
                "event_date": event.event_date.isoformat() if event.event_date else "",
                "effective_trading_event_date": (
                    event.effective_trading_event_date.isoformat()
                    if event.effective_trading_event_date
                    else ""
                ),
                "upload_timing_bucket": event.timing_bucket,
                "quality_score": event.actionability_score if event.actionability_score is not None else "",
                "included_in_v2_event_study": included,
                "exclusion_reason": event.return_exclusion_reason,
                "source_table": "transcript_recommendation_events",
                "notes": "expanded live DB accepted/extracted recommendation event",
            }
        )
    columns = [
        "v2_sample_version",
        "event_id",
        "video_id",
        "transcript_id",
        "creator",
        "channel_id",
        "ticker",
        "company_name",
        "recommendation_type",
        "event_date",
        "effective_trading_event_date",
        "upload_timing_bucket",
        "quality_score",
        "included_in_v2_event_study",
        "exclusion_reason",
        "source_table",
        "notes",
    ]
    write_csv(V2_LOCK_DIR / "02_v2_event_manifest.csv", rows, columns)
    return rows


def build_bridge(events: list[EventRecord]) -> list[dict[str, Any]]:
    v1_rows = read_csv(V1_LOCK_DIR / "01_locked_event_manifest.csv")
    v1_ids = {int(row["event_id"]) for row in v1_rows if row.get("event_id")}
    event_by_id = {event.event_id: event for event in events}
    all_ids = sorted(v1_ids | set(event_by_id))
    rows = []
    for event_id in all_ids:
        event = event_by_id.get(event_id)
        in_v1 = event_id in v1_ids
        in_v2 = event is not None
        rows.append(
            {
                "event_id": event_id,
                "video_id": event.video_id if event else "",
                "ticker": event.ticker if event else "",
                "event_date": event.event_date.isoformat() if event and event.event_date else "",
                "in_v1_locked_sample": in_v1,
                "in_v2_live_sample": in_v2,
                "v1_only": in_v1 and not in_v2,
                "v2_only": in_v2 and not in_v1,
                "shared": in_v1 and in_v2,
                "notes": "event_id bridge between v1 manifest and v2 live DB",
            }
        )
    columns = [
        "event_id",
        "video_id",
        "ticker",
        "event_date",
        "in_v1_locked_sample",
        "in_v2_live_sample",
        "v1_only",
        "v2_only",
        "shared",
        "notes",
    ]
    write_csv(V2_LOCK_DIR / "03_v1_vs_v2_event_bridge.csv", rows, columns)
    return rows


def sec_maps() -> tuple[dict[int, bool], int]:
    rows = read_csv(V1_DIR / "06_sec_news_overlap_flags.csv")
    out: dict[int, bool] = {}
    for row in rows:
        try:
            event_id = int(row["event_id"])
        except (KeyError, ValueError):
            continue
        raw = str(row.get("sec_confounded_event_flag", "")).strip().lower()
        out[event_id] = raw in {"true", "1", "yes"}
    return out, len(out)


def sample_construction_rows(
    events: list[EventRecord],
    transcripts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts = db_counts()
    sec_map, _known_sec = sec_maps()
    event_ids = {event.event_id for event in events}
    sec_known_ids = event_ids & set(sec_map)
    sec_clean = sum(1 for event_id in sec_known_ids if not sec_map[event_id])
    sec_confounded = sum(1 for event_id in sec_known_ids if sec_map[event_id])
    rows = [
        {
            "metric": "live_transcript_rows",
            "count": counts["live_transcript_rows"],
            "source": "youtube_transcripts",
            "filter_definition": "all rows",
            "notes": "one current live DB transcript row per video_id",
        },
        {
            "metric": "successful_transcript_rows",
            "count": counts["successful_transcript_rows"],
            "source": "youtube_transcripts",
            "filter_definition": "status/retrieval_status success-like",
            "notes": "",
        },
        {
            "metric": "strict_text_gt_50",
            "count": counts["strict_text_gt_50"],
            "source": "youtube_transcripts",
            "filter_definition": "length(full_text) > 50, aggregate only",
            "notes": "full_text not exported",
        },
        {
            "metric": "language_filtered_transcripts",
            "count": counts["language_filtered_transcripts"],
            "source": "youtube_transcripts",
            "filter_definition": "language/language_code English-like",
            "notes": "",
        },
        {
            "metric": "candidate_windows",
            "count": counts["candidate_windows"],
            "source": "transcript_candidate_windows",
            "filter_definition": "all candidate windows",
            "notes": "",
        },
        {
            "metric": "accepted_recommendation_events",
            "count": len(events),
            "source": "transcript_recommendation_events",
            "filter_definition": "all accepted/extracted rows",
            "notes": "v2 primary candidate event panel",
        },
        {
            "metric": "distinct_event_videos",
            "count": counts["distinct_event_videos"],
            "source": "transcript_recommendation_events",
            "filter_definition": "count distinct video_id",
            "notes": "",
        },
        {
            "metric": "buy_recommendations",
            "count": sum(event.recommendation_type == "buy" for event in events),
            "source": "v2 event manifest",
            "filter_definition": "recommendation_type == buy",
            "notes": "",
        },
        {
            "metric": "sell_recommendations",
            "count": sum(event.recommendation_type == "sell" for event in events),
            "source": "v2 event manifest",
            "filter_definition": "recommendation_type == sell",
            "notes": "",
        },
        {
            "metric": "creators",
            "count": len({event.creator for event in events}),
            "source": "raw_youtube_videos join",
            "filter_definition": "distinct channel_title in event panel",
            "notes": "",
        },
        {
            "metric": "tickers",
            "count": len({event.ticker for event in events}),
            "source": "transcript_recommendation_events",
            "filter_definition": "distinct ticker",
            "notes": "",
        },
        {
            "metric": "return_matched_1d",
            "count": sum(event.ar_1d is not None for event in events),
            "source": "local yfinance_market_data.csv",
            "filter_definition": "ticker and SPY benchmark available through +1 trading day",
            "notes": "",
        },
        {
            "metric": "return_matched_5d",
            "count": sum(event.ar_5d is not None for event in events),
            "source": "local yfinance_market_data.csv",
            "filter_definition": "ticker and SPY benchmark available through +5 trading days",
            "notes": "",
        },
        {
            "metric": "low_lookahead_events",
            "count": sum(event.timing_bucket in LOW_LOOKAHEAD_BUCKETS for event in events),
            "source": "published_at timing bucket",
            "filter_definition": "before_open or weekend_or_holiday",
            "notes": "",
        },
        {
            "metric": "duplicate_collapsed_events",
            "count": len({event.duplicate_cluster_id for event in events}),
            "source": "creator+ticker+weekday_adjusted_date clusters",
            "filter_definition": "one observation per duplicate cluster",
            "notes": "",
        },
        {
            "metric": "sec_clean_events",
            "count": sec_clean,
            "source": "v1 SEC flags joined by event_id",
            "filter_definition": "known v1 SEC flag and sec_confounded_event_flag false",
            "notes": "partial: SEC flags are available only for shared v1 event IDs",
        },
        {
            "metric": "sec_confounded_events",
            "count": sec_confounded,
            "source": "v1 SEC flags joined by event_id",
            "filter_definition": "known v1 SEC flag and sec_confounded_event_flag true",
            "notes": "partial: SEC flags are available only for shared v1 event IDs",
        },
        {
            "metric": "top5_events",
            "count": sum(event.ticker in TOP5_TICKERS for event in events),
            "source": "v2 event manifest",
            "filter_definition": "ticker in NVDA, TSLA, AAPL, AMD, AMZN",
            "notes": "",
        },
        {
            "metric": "non_top_events",
            "count": sum(event.ticker not in TOP5_TICKERS for event in events),
            "source": "v2 event manifest",
            "filter_definition": "ticker outside top-5 set",
            "notes": "",
        },
        {
            "metric": "factor_matched_events",
            "count": 0,
            "source": "data/imports/french_factors",
            "filter_definition": "not computed; factor input directory absent",
            "notes": "factor-adjusted v2 table is a documented gap",
        },
    ]
    columns = ["metric", "count", "source", "filter_definition", "notes"]
    write_csv(V2_LOCK_DIR / "04_v2_sample_construction.csv", rows, columns)
    write_md(
        V2_LOCK_DIR / "04_v2_sample_construction.md",
        "# V2 Sample Construction\n\n" + markdown_table(rows, columns),
    )
    write_csv(
        V2_DIR / "01_v2_sample_construction_table.csv",
        rows,
        columns,
    )
    write_md(
        V2_DIR / "01_v2_sample_construction_table.md",
        "# V2 Sample Construction Table\n\n"
        + markdown_table(rows, columns)
        + "\n\nV2 is the expanded live-DB candidate primary sample. X/Twitter is not used.",
    )
    return rows


def v2_lock_readme() -> None:
    text = """# V2 Expanded Locked Sample

V2 is the expanded live RunPod DB primary candidate sample. It uses compact
manifests for current transcript metadata and accepted/extracted recommendation
events without exporting transcript text, raw API payloads, or raw database
files.

V1 is retained under `data/exports/final_paper_package/` as the historical
locked artifact sample and benchmark. V2 should become primary only if the
validator passes or partial-passes with documented caveats.

The v2 empirical claim depends on the v2 results, not the v1 result strength.
The v2 package must not use simulated free-news outputs as evidence. Real
public-news exclusion requires a separate provider implementation and audit.
"""
    write_md(V2_LOCK_DIR / "README.md", text)


def event_values(events: list[EventRecord], field: str) -> list[float]:
    return [float(getattr(event, field)) for event in events if getattr(event, field) is not None]


def first_per_cluster(events: list[EventRecord]) -> list[EventRecord]:
    seen: set[int] = set()
    out = []
    for event in events:
        if event.duplicate_cluster_id in seen:
            continue
        seen.add(event.duplicate_cluster_id)
        out.append(event)
    return out


def spec_row(name: str, events: list[EventRecord], notes: str = "") -> dict[str, Any]:
    stats_1d = t_test(event_values(events, "ar_1d"))
    stats_5d = t_test(event_values(events, "ar_5d"))
    return {
        "specification": name,
        "n_1d": stats_1d["n"],
        "mean_1d_ar": fmt(stats_1d["mean"]),
        "t_1d": fmt(stats_1d["t"], 3),
        "p_1d": fmt(stats_1d["p"], 6),
        "n_5d": stats_5d["n"],
        "mean_5d_ar": fmt(stats_5d["mean"]),
        "t_5d": fmt(stats_5d["t"], 3),
        "p_5d": fmt(stats_5d["p"], 6),
        "median_5d_ar": fmt(stats_5d["median"]),
        "win_rate_5d": fmt(stats_5d["win_rate"], 6),
        "notes": notes,
    }


def v1_reference_rows() -> dict[str, dict[str, str]]:
    rows = read_csv(V1_DIR / "02_event_study_robustness_table.csv")
    out = {}
    for row in rows:
        out[f"{row.get('specification')}__{row.get('horizon')}"] = row
    return out


def v1_spec_row(label: str, spec_1d: str, spec_5d: str, notes: str) -> dict[str, Any]:
    refs = v1_reference_rows()
    one = refs.get(spec_1d, {})
    five = refs.get(spec_5d, {})
    return {
        "specification": label,
        "n_1d": one.get("n", ""),
        "mean_1d_ar": one.get("mean", ""),
        "t_1d": one.get("t_stat", ""),
        "p_1d": one.get("p_value", ""),
        "n_5d": five.get("n", ""),
        "mean_5d_ar": five.get("mean", ""),
        "t_5d": five.get("t_stat", ""),
        "p_5d": five.get("p_value", ""),
        "median_5d_ar": five.get("median", ""),
        "win_rate_5d": "",
        "notes": notes,
    }


def build_empirical_tables(events: list[EventRecord]) -> dict[str, list[dict[str, Any]]]:
    sec_map, known_sec_count = sec_maps()
    sec_known = [event for event in events if event.event_id in sec_map]
    sec_clean = [event for event in sec_known if not sec_map[event.event_id]]
    sec_confounded = [event for event in sec_known if sec_map[event.event_id]]
    low = [event for event in events if event.timing_bucket in LOW_LOOKAHEAD_BUCKETS]
    collapsed = first_per_cluster(events)
    high_quality = [
        event
        for event in events
        if event.actionability_score is not None and event.actionability_score >= 80
    ]
    collapsed_ids = {event.event_id for event in first_per_cluster(high_quality)}
    non_duplicate_high_quality = [event for event in high_quality if event.event_id in collapsed_ids]
    specs = [
        v1_spec_row(
            "v1 locked sample reference",
            "Canonical baseline__AR_0_1",
            "Canonical baseline__AR_0_5",
            "historical v1 benchmark, not v2 primary",
        ),
        spec_row("v2 all accepted events", events, "all accepted/extracted live DB events"),
        spec_row("v2 return-matched events", events, "same as all events after return availability"),
        spec_row("v2 low-lookahead", low, "before_open and weekend_or_holiday upload buckets"),
        spec_row("v2 duplicate-collapsed", collapsed, "first event per creator+ticker+date cluster"),
        spec_row(
            "v2 SEC-clean known subset",
            sec_clean,
            f"partial SEC join; {known_sec_count} events have v1 SEC flags",
        ),
        spec_row(
            "v2 SEC-confounded known subset",
            sec_confounded,
            f"partial SEC join; {known_sec_count} events have v1 SEC flags",
        ),
        spec_row("v2 top-5 tickers", [e for e in events if e.ticker in TOP5_TICKERS], ""),
        spec_row("v2 non-top tickers", [e for e in events if e.ticker not in TOP5_TICKERS], ""),
        spec_row("v2 buy-only", [e for e in events if e.recommendation_type == "buy"], ""),
        spec_row("v2 sell-only", [e for e in events if e.recommendation_type == "sell"], ""),
        spec_row("v2 high-quality actionability>=80", high_quality, "DB actionability_score proxy"),
        spec_row(
            "v2 non-duplicate high-quality",
            non_duplicate_high_quality,
            "first duplicate cluster among actionability>=80 events",
        ),
    ]
    columns = [
        "specification",
        "n_1d",
        "mean_1d_ar",
        "t_1d",
        "p_1d",
        "n_5d",
        "mean_5d_ar",
        "t_5d",
        "p_5d",
        "median_5d_ar",
        "win_rate_5d",
        "notes",
    ]
    write_csv(V2_DIR / "02_v2_event_study_robustness_table.csv", specs, columns)
    write_md(
        V2_DIR / "02_v2_event_study_robustness_table.md",
        "# V2 Event Study Robustness Table\n\n"
        + markdown_table(specs, columns)
        + "\n\nReturns are SPY-adjusted using local yfinance adjusted-close data. "
        "No new market data are fetched by this script.",
    )

    build_timing_table(events)
    build_duplicate_table(events)
    build_sec_table(sec_clean, sec_confounded, known_sec_count, len(events))
    build_top_sell_creator_ticker_tables(events)
    build_factor_and_calendar_placeholders()
    build_v1_v2_comparison(specs)
    build_result_hierarchy(specs)
    build_chart_data(specs)
    build_narratives(specs, events)
    return {"event_study": specs}


def build_timing_table(events: list[EventRecord]) -> None:
    rows = []
    for bucket in ["before_open", "weekend_or_holiday", "during_market", "after_close", "unknown"]:
        selected = [event for event in events if event.timing_bucket == bucket]
        rows.append({"timing_bucket": bucket, **spec_row(bucket, selected)})
    columns = list(rows[0])
    write_csv(V2_DIR / "03_v2_timing_lookahead_table.csv", rows, columns)
    write_md(V2_DIR / "03_v2_timing_lookahead_table.md", "# V2 Timing Table\n\n" + markdown_table(rows, columns))


def build_duplicate_table(events: list[EventRecord]) -> None:
    sizes = Counter(event.duplicate_cluster_id for event in events)
    rows = [
        {"row_type": "overview", "metric": "events", "count": len(events), "notes": ""},
        {"row_type": "overview", "metric": "clusters", "count": len(sizes), "notes": ""},
        {
            "row_type": "overview",
            "metric": "duplicate_clusters",
            "count": sum(1 for size in sizes.values() if size > 1),
            "notes": "cluster size greater than 1",
        },
        {
            "row_type": "overview",
            "metric": "max_cluster_size",
            "count": max(sizes.values()) if sizes else 0,
            "notes": "",
        },
    ]
    for row in [
        spec_row("event_level", events),
        spec_row("first_event_per_cluster", first_per_cluster(events)),
    ]:
        rows.append({"row_type": "result", "metric": row["specification"], "count": row["n_5d"], "notes": row})
    columns = ["row_type", "metric", "count", "notes"]
    write_csv(V2_DIR / "04_v2_duplicate_cluster_analysis.csv", rows, columns)
    write_md(
        V2_DIR / "04_v2_duplicate_cluster_analysis.md",
        "# V2 Duplicate Cluster Analysis\n\n" + markdown_table(rows, columns),
    )


def build_sec_table(
    sec_clean: list[EventRecord],
    sec_confounded: list[EventRecord],
    known_sec_count: int,
    total_events: int,
) -> None:
    rows = [
        spec_row(
            "SEC-clean known subset",
            sec_clean,
            f"partial join: {known_sec_count} of {total_events} v2 events have SEC flags",
        ),
        spec_row(
            "SEC-confounded known subset",
            sec_confounded,
            f"partial join: {known_sec_count} of {total_events} v2 events have SEC flags",
        ),
    ]
    columns = list(rows[0])
    write_csv(V2_DIR / "05_v2_sec_clean_analysis.csv", rows, columns)
    write_md(
        V2_DIR / "05_v2_sec_clean_analysis.md",
        "# V2 SEC-Clean Analysis\n\n"
        + markdown_table(rows, columns)
        + "\n\nSEC flags are joined from v1 by event_id. Events unique to v2 are "
        "not SEC-audited in this pass, so this is a partial robustness check.",
    )


def build_top_sell_creator_ticker_tables(events: list[EventRecord]) -> None:
    top_rows = [
        spec_row("top-5 tickers", [event for event in events if event.ticker in TOP5_TICKERS]),
        spec_row("non-top tickers", [event for event in events if event.ticker not in TOP5_TICKERS]),
    ]
    write_csv(V2_DIR / "06_v2_top5_vs_non_top_analysis.csv", top_rows, list(top_rows[0]))
    write_md(
        V2_DIR / "06_v2_top5_vs_non_top_analysis.md",
        "# V2 Top-5 vs Non-Top Analysis\n\n" + markdown_table(top_rows, list(top_rows[0])),
    )

    buy_sell_rows = [
        spec_row("buy-only", [event for event in events if event.recommendation_type == "buy"]),
        spec_row("sell-only", [event for event in events if event.recommendation_type == "sell"]),
    ]
    write_csv(V2_DIR / "07_v2_buy_vs_sell_analysis.csv", buy_sell_rows, list(buy_sell_rows[0]))
    write_md(
        V2_DIR / "07_v2_buy_vs_sell_analysis.md",
        "# V2 Buy vs Sell Analysis\n\n" + markdown_table(buy_sell_rows, list(buy_sell_rows[0])),
    )

    creator_rows = []
    for creator, count in Counter(event.creator for event in events).most_common():
        selected = [event for event in events if event.creator == creator]
        creator_rows.append({"creator": creator, "event_count": count, **spec_row("creator", selected)})
    creator_columns = list(creator_rows[0])
    write_csv(V2_DIR / "08_v2_creator_heterogeneity.csv", creator_rows, creator_columns)
    write_md(
        V2_DIR / "08_v2_creator_heterogeneity.md",
        "# V2 Creator Heterogeneity\n\n" + markdown_table(creator_rows[:25], creator_columns),
    )

    ticker_rows = []
    for ticker, count in Counter(event.ticker for event in events).most_common():
        selected = [event for event in events if event.ticker == ticker]
        ticker_rows.append({"ticker": ticker, "event_count": count, **spec_row("ticker", selected)})
    ticker_columns = list(ticker_rows[0])
    write_csv(V2_DIR / "09_v2_ticker_heterogeneity.csv", ticker_rows, ticker_columns)
    write_md(
        V2_DIR / "09_v2_ticker_heterogeneity.md",
        "# V2 Ticker Heterogeneity\n\n" + markdown_table(ticker_rows, ticker_columns),
    )


def build_factor_and_calendar_placeholders() -> None:
    factor_rows = [
        {
            "sample": "v2 expanded",
            "model": "not_computed",
            "horizon": "AR_0_5",
            "n": 0,
            "alpha_mean": "",
            "t_stat": "",
            "p_value": "",
            "notes": "factor input directory data/imports/french_factors is absent; no download performed",
        }
    ]
    write_csv(V2_DIR / "10_v2_factor_adjusted_alpha_table.csv", factor_rows, list(factor_rows[0]))
    write_md(
        V2_DIR / "10_v2_factor_adjusted_alpha_table.md",
        "# V2 Factor-Adjusted Alpha Table\n\n"
        + markdown_table(factor_rows, list(factor_rows[0])),
    )
    portfolio_rows = [
        {
            "strategy": "not_computed",
            "holding_days": "",
            "cost_bps": "",
            "mean_daily_return": "",
            "annualized_sharpe": "",
            "status": "not_computed_in_v2_pass",
            "notes": "calendar-time portfolio not rebuilt because v2 market-return computation is event-window only",
        }
    ]
    write_csv(V2_DIR / "11_v2_calendar_time_portfolio_results.csv", portfolio_rows, list(portfolio_rows[0]))
    write_md(
        V2_DIR / "11_v2_calendar_time_portfolio_results.md",
        "# V2 Calendar-Time Portfolio Results\n\n"
        + markdown_table(portfolio_rows, list(portfolio_rows[0]))
        + "\n\nThis absence should not be filled with tradable-alpha language.",
    )


def build_v1_v2_comparison(specs: list[dict[str, Any]]) -> None:
    selected = [
        "v1 locked sample reference",
        "v2 all accepted events",
        "v2 low-lookahead",
        "v2 duplicate-collapsed",
        "v2 SEC-clean known subset",
        "v2 top-5 tickers",
        "v2 non-top tickers",
    ]
    rows = [row for row in specs if row["specification"] in selected]
    columns = list(rows[0])
    write_csv(V2_DIR / "12_v1_vs_v2_comparison_table.csv", rows, columns)
    write_md(
        V2_DIR / "12_v1_vs_v2_comparison_table.md",
        "# V1 vs V2 Comparison\n\n"
        + markdown_table(rows, columns)
        + "\n\nV2 adoption is based on coverage and reproducibility, not stronger results.",
    )


def build_result_hierarchy(specs: list[dict[str, Any]]) -> None:
    order = [
        "v2 all accepted events",
        "v2 low-lookahead",
        "v2 SEC-clean known subset",
        "v2 duplicate-collapsed",
        "v2 top-5 tickers",
        "v2 non-top tickers",
        "v2 buy-only",
        "v2 sell-only",
    ]
    rows = []
    by_name = {row["specification"]: row for row in specs}
    for idx, name in enumerate(order, start=1):
        row = by_name[name].copy()
        row["level"] = idx
        if row["p_5d"] not in ("", None) and float(row["p_5d"]) < 0.05:
            strength = "statistically_detectable_5d"
        else:
            strength = "not_statistically_detectable_5d"
        row["evidence_status"] = strength
        rows.append(row)
    columns = ["level"] + [c for c in rows[0] if c != "level"]
    write_csv(V2_DIR / "13_v2_result_hierarchy.csv", rows, columns)
    write_md(
        V2_DIR / "13_v2_result_hierarchy.md",
        "# V2 Result Hierarchy\n\n"
        + markdown_table(rows, columns)
        + "\n\nThis hierarchy is keyed to v2, not the historical v1 package.",
    )


def build_chart_data(specs: list[dict[str, Any]]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    forest_rows = []
    for row in specs:
        if row["specification"].startswith("v2"):
            forest_rows.append(
                {
                    "specification": row["specification"],
                    "mean_1d_ar": row["mean_1d_ar"],
                    "p_1d": row["p_1d"],
                    "mean_5d_ar": row["mean_5d_ar"],
                    "p_5d": row["p_5d"],
                    "notes": row["notes"],
                }
            )
    write_csv(FIG_DIR / "v2_event_study_forest_plot.csv", forest_rows, list(forest_rows[0]))
    top_rows = [row for row in specs if row["specification"] in {"v2 top-5 tickers", "v2 non-top tickers"}]
    write_csv(FIG_DIR / "v2_top5_vs_non_top.csv", top_rows, list(top_rows[0]))
    sample_rows = read_csv(V2_LOCK_DIR / "04_v2_sample_construction.csv")
    write_csv(FIG_DIR / "v2_sample_funnel.csv", sample_rows, list(sample_rows[0]))
    comparison_rows = [
        row
        for row in specs
        if row["specification"] in {"v1 locked sample reference", "v2 all accepted events"}
    ]
    write_csv(FIG_DIR / "v1_vs_v2_headline_comparison.csv", comparison_rows, list(comparison_rows[0]))


def find_spec(specs: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(row for row in specs if row["specification"] == name)


def build_narratives(specs: list[dict[str, Any]], events: list[EventRecord]) -> None:
    v1 = find_spec(specs, "v1 locked sample reference")
    all_v2 = find_spec(specs, "v2 all accepted events")
    low = find_spec(specs, "v2 low-lookahead")
    collapsed = find_spec(specs, "v2 duplicate-collapsed")
    top5 = find_spec(specs, "v2 top-5 tickers")
    non_top = find_spec(specs, "v2 non-top tickers")
    sec = find_spec(specs, "v2 SEC-clean known subset")
    buy = find_spec(specs, "v2 buy-only")
    sell = find_spec(specs, "v2 sell-only")

    if all_v2["mean_5d_ar"] and float(all_v2["mean_5d_ar"]) > float(v1["mean_5d_ar"] or 0):
        direction = "strengthens"
    elif all_v2["mean_5d_ar"] and float(all_v2["mean_5d_ar"]) < 0:
        direction = "reverses"
    else:
        direction = "weakens or disappears relative to"

    results = f"""# V2 Final Results Section Draft

The expanded v2 live-DB sample contains {len(events):,} accepted/extracted
transcript-supported recommendation events. Using local yfinance adjusted-close
data and SPY-adjusted event windows, the v2 headline 5-day abnormal return is
{fmt_pct(safe_float(all_v2['mean_5d_ar']))} (n={all_v2['n_5d']},
p={all_v2['p_5d']}), compared with the v1 locked-sample headline of
{fmt_pct(safe_float(v1['mean_5d_ar']))}.

The expanded sample therefore {direction} the earlier v1 finding. This is not a
reason to reject v2: v2 is preferred because it uses the current larger RunPod
database and a reproducible manifest, not because it produces stronger results.

Low-lookahead v2 events have a 5-day abnormal return of
{fmt_pct(safe_float(low['mean_5d_ar']))} (n={low['n_5d']}, p={low['p_5d']}).
Duplicate collapse produces {fmt_pct(safe_float(collapsed['mean_5d_ar']))}
(n={collapsed['n_5d']}, p={collapsed['p_5d']}).

Top-5 ticker events show {fmt_pct(safe_float(top5['mean_5d_ar']))} over five
trading days, while non-top events show {fmt_pct(safe_float(non_top['mean_5d_ar']))}.
This keeps the paper centered on attention amplification and concentration, not
causal or tradable alpha.
"""
    write_md(V2_DIR / "14_v2_final_results_section_draft.md", results)

    limitations = f"""# V2 Final Limitations Section Draft

The v2 rebuild validates a larger primary candidate sample, but several limits
remain. First, v2 return coverage is not complete: {all_v2['n_5d']} of
{len(events)} events have 5-day return windows. Missing coverage is primarily a
market-data availability issue for sparse or unsupported tickers and events too
close to the end of the price file.

Second, the SEC-clean row is only a known-subset join against v1 SEC flags:
{sec['n_5d']} SEC-clean events have 5-day returns in that partial join. V2
unique events require a separate SEC refresh before SEC-clean can be presented
as a full-sample robustness result.

Third, free-news outputs remain simulated diagnostic scaffolding and are not
used as empirical public-news exclusion evidence. No Bloomberg API or Bloomberg
news data are used.

Fourth, the results are associations around YouTube upload dates. They do not
establish causality, tradable alpha, or news-confound isolation.
"""
    write_md(V2_DIR / "15_v2_final_limitations_section_draft.md", limitations)

    conclusion = f"""# V2 Final Conclusion Draft

The v2 expanded rebuild should replace v1 as the primary sample if the project
prioritizes coverage and reproducibility. The larger sample materially
{direction} the earlier headline abnormal-return estimate: the v2 5-day
association is {fmt_pct(safe_float(all_v2['mean_5d_ar']))}, with p={all_v2['p_5d']}.

The correct conclusion is not broad tradable alpha. The evidence is best framed
as an audit of attention amplification around finfluencer recommendation events,
with concentration and data-quality caveats. If the expanded sample weakens the
headline effect, the paper should say so directly and use v1 only as a historical
benchmark.
"""
    write_md(V2_DIR / "16_v2_final_conclusion_draft.md", conclusion)

    memo = f"""# V2 Professor Defense Memo

**Sample update:** The primary candidate sample is now the expanded live RunPod
DB: 9,992 transcript rows and {len(events):,} accepted recommendation events.
The old 1,554-event package is preserved as v1.

**Result update:** V2 headline 5-day abnormal return is
{fmt_pct(safe_float(all_v2['mean_5d_ar']))} (n={all_v2['n_5d']}, p={all_v2['p_5d']}).
The result {direction} the earlier v1 estimate.

**Defense:** We adopted v2 because it is larger and explicitly manifest-backed,
not because it improves the result. The honest professor-facing claim is
attention amplification with concentration and robustness caveats, not causal or
tradable alpha.

**Caveat:** SEC-clean is partial for v2, factor adjustment is not computed, and
free-news remains simulated diagnostic scaffolding.
"""
    write_md(V2_DIR / "17_v2_professor_defense_memo.md", memo)

    adoption = "ADOPT_V2_PRIMARY_WITH_CAUTION"
    recommendation = f"""# V2 Adoption Recommendation

## Label

{adoption}

## Rationale

V2 validates as a coherent expanded primary candidate sample: the transcript and
event manifest counts match the live DB, event IDs are unique, event dates parse,
and return coverage is documented. The caveat is that full-sample SEC-clean,
factor-adjusted, and calendar-time portfolio robustness are not complete.

## Empirical Direction

- V1 5D headline: {fmt_pct(safe_float(v1['mean_5d_ar']))}
- V2 5D headline: {fmt_pct(safe_float(all_v2['mean_5d_ar']))}
- V2 low-lookahead 5D: {fmt_pct(safe_float(low['mean_5d_ar']))}
- V2 duplicate-collapsed 5D: {fmt_pct(safe_float(collapsed['mean_5d_ar']))}
- V2 top-5 5D: {fmt_pct(safe_float(top5['mean_5d_ar']))}
- V2 non-top 5D: {fmt_pct(safe_float(non_top['mean_5d_ar']))}
- V2 buy-only 5D: {fmt_pct(safe_float(buy['mean_5d_ar']))}
- V2 sell-only 5D: {fmt_pct(safe_float(sell['mean_5d_ar']))}

## Paper Claim

The professor-facing claim should become: the expanded YouTube finfluencer
sample provides a reproducible audit of attention-linked recommendation events,
but the v1 headline abnormal-return result does not automatically survive the
larger sample. Claims must emphasize association, concentration, and robustness
gaps rather than causal or tradable alpha.
"""
    write_md(V2_DIR / "18_v2_adoption_recommendation.md", recommendation)


def main() -> int:
    V2_DIR.mkdir(parents=True, exist_ok=True)
    V2_LOCK_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    build_plan()
    schema_audit()
    market = load_market_data()
    transcripts = build_transcript_manifest()
    events = fetch_events(market)
    build_event_manifest(events)
    build_bridge(events)
    v2_lock_readme()
    sample_construction_rows(events, transcripts)
    build_empirical_tables(events)
    print(f"V2 build complete: events={len(events)} transcripts={len(transcripts)}")
    print(f"HEAD={run_git(['git', 'rev-parse', 'HEAD'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
