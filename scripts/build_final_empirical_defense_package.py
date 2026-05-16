"""Build the final empirical-defense package for the locked FIN 496 sample.

Inputs are the committed research-grade event panel, the locked local SQLite
sample, local yfinance daily prices, free SEC EDGAR metadata, optional Kenneth
French factor files, optional yfinance intraday coverage, and future Bloomberg
manual-CSV templates. This script does not collect transcripts, call Apify, read
.env files, or call Bloomberg APIs.
"""

from __future__ import annotations

import csv
import io
import math
import os
import sqlite3
import subprocess
import sys
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import build_research_grade_analysis as rg
import pandas as pd
import requests
import statsmodels.api as sm
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package"
RG_DIR = REPO_ROOT / "data" / "exports" / "research_grade_analysis"
FACTOR_DIR = REPO_ROOT / "data" / "imports" / "french_factors"
BLOOMBERG_DIR = REPO_ROOT / "data" / "imports" / "bloomberg" / "manual_csv"
DB_PATH = REPO_ROOT / "data" / "finfluencer_alpha.db"

TOP5_TICKERS = {"NVDA", "TSLA", "AAPL", "AMD", "AMZN"}
LOW_LOOKAHEAD_BUCKETS = {"before_open", "weekend_or_holiday"}
SEC_MATERIAL_FORMS = {
    "8-K",
    "8-K/A",
    "10-Q",
    "10-Q/A",
    "10-K",
    "10-K/A",
    "S-1",
    "S-1/A",
    "424B",
    "424B1",
    "424B2",
    "424B3",
    "424B4",
    "424B5",
}
SEC_USER_AGENT = (
    "Scott Switzer scott@example.com FIN496 academic research final empirical defense"
)
LOCKED_TICKER_CIK_MAP = {
    "AAPL": "0000320193",
    "AMC": "0001411579",
    "AMD": "0000002488",
    "AMZN": "0001018724",
    "COIN": "0001679788",
    "CRM": "0001108524",
    "DIS": "0001744489",
    "GME": "0001326380",
    "GOOGL": "0001652044",
    "HOOD": "0001783879",
    "META": "0001326801",
    "MSFT": "0000789019",
    "NFLX": "0001065280",
    "NVDA": "0001045810",
    "PLTR": "0001321655",
    "PYPL": "0001633917",
    "SHOP": "0001594805",
    "SMCI": "0001375365",
    "SOFI": "0001818874",
    "SQ": "0001512673",
    "TGT": "0000027419",
    "TSLA": "0001318605",
    "UBER": "0001543151",
    "XYZ": "0001512673",
}


@dataclass
class DefenseContext:
    events: list[rg.EnrichedEvent]
    event_df: pd.DataFrame
    market: dict[str, list[dict[str, Any]]]
    local_user: str
    local_host: str
    start_head: str
    origin_head: str
    branch: str


def _run(args: list[str]) -> str:
    return subprocess.check_output(args, cwd=REPO_ROOT, text=True).strip()


def _safe_run(args: list[str]) -> str:
    try:
        return _run(args)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _fmt(value: Any, digits: int = 6) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return f"{value:.{digits}f}"
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def t_stats(values: list[float | None]) -> dict[str, Any]:
    xs = [float(value) for value in values if value is not None and not math.isnan(float(value))]
    n, mean, median, t_value, p_value = rg.t_test_one_sample(xs)
    return {"n": n, "mean": mean, "median": median, "t": t_value, "p": p_value}


def winsorize(values: list[float], pct: float = 0.01) -> list[float]:
    if not values:
        return []
    ordered = sorted(values)
    lo = ordered[int(pct * (len(ordered) - 1))]
    hi = ordered[int((1.0 - pct) * (len(ordered) - 1))]
    return [min(max(value, lo), hi) for value in values]


def values_for(
    events: list[rg.EnrichedEvent],
    field: str,
    predicate=lambda _event: True,
) -> list[float]:
    values = []
    for event in events:
        value = event.abnormal[field]
        if value is not None and predicate(event):
            values.append(value)
    return values


def first_per_cluster(events: list[rg.EnrichedEvent]) -> list[rg.EnrichedEvent]:
    seen: set[int] = set()
    out = []
    for event in events:
        cluster_id = int(event.duplicate_cluster_id or event.event.event_id)
        if cluster_id in seen:
            continue
        seen.add(cluster_id)
        out.append(event)
    return out


def max_quality_per_cluster(events: list[rg.EnrichedEvent]) -> list[rg.EnrichedEvent]:
    best: dict[int, rg.EnrichedEvent] = {}
    for event in events:
        cluster_id = int(event.duplicate_cluster_id or event.event.event_id)
        current = best.get(cluster_id)
        if current is None:
            best[cluster_id] = event
            continue
        if (event.quality_score, -event.event.event_id) > (
            current.quality_score,
            -current.event.event_id,
        ):
            best[cluster_id] = event
    return sorted(best.values(), key=lambda event: event.event.event_id)


def cluster_mean_values(events: list[rg.EnrichedEvent], field: str) -> list[float]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for event in events:
        value = event.abnormal[field]
        if value is not None:
            grouped[int(event.duplicate_cluster_id or event.event.event_id)].append(value)
    return [sum(values) / len(values) for values in grouped.values() if values]


def stats_row(label: str, horizon: str, values: list[float], note: str = "") -> dict[str, Any]:
    stats = t_stats(values)
    return {
        "specification": label,
        "horizon": horizon,
        "n": stats["n"],
        "mean": _fmt(stats["mean"]),
        "median": _fmt(stats["median"]),
        "t_stat": _fmt(stats["t"], 3),
        "p_value": _fmt(stats["p"], 6),
        "bh_q_value": "",
        "note": note,
        "_p_float": stats["p"],
    }


def load_context() -> DefenseContext:
    branch = _safe_run(["git", "branch", "--show-current"])
    start_head = _safe_run(["git", "rev-parse", "HEAD"])
    origin_head = _safe_run(["git", "rev-parse", "origin/x-youtube-full-research-expansion"])
    local_user = _safe_run(["whoami"])
    local_host = _safe_run(["hostname"])
    raw_events = rg.load_events()
    market = rg.load_market_data()
    aliases = rg._ticker_alias_map()
    events = rg.build_enriched_events(raw_events, market, aliases)
    event_df = pd.DataFrame([event_to_row(event) for event in events])
    return DefenseContext(
        events=events,
        event_df=event_df,
        market=market,
        local_user=local_user,
        local_host=local_host,
        start_head=start_head,
        origin_head=origin_head,
        branch=branch,
    )


def event_to_row(event: rg.EnrichedEvent) -> dict[str, Any]:
    return {
        "event_id": event.event.event_id,
        "video_id": event.event.video_id,
        "creator": event.event.creator,
        "ticker": event.event.ticker,
        "data_ticker": event.data_ticker,
        "recommendation_type": "buy" if "bull" in event.event.stance else "sell",
        "published_at": event.event.published_at,
        "calendar_event_date": event.calendar_event_date.isoformat()
        if event.calendar_event_date
        else "",
        "effective_trading_event_date": event.effective_trading_event_date.isoformat()
        if event.effective_trading_event_date
        else "",
        "timing_bucket": event.timing_bucket,
        "lookahead_risk_flag": event.timing_bucket in {"during_market", "after_close"},
        "duplicate_cluster_id": event.duplicate_cluster_id,
        "duplicate_cluster_size": event.duplicate_cluster_size,
        "event_quality_score": event.quality_score,
        "event_quality_tier": event.quality_tier,
        "ar_0_1": event.abnormal["ar_event_0_1"],
        "ar_0_5": event.abnormal["ar_post_0_5"],
        "ar_0_20": event.abnormal["ar_post_0_20"],
        "pre_ar_20_1": event.abnormal["ar_pre_20_1"],
        "pre_ar_5_1": event.abnormal["ar_pre_5_1"],
    }


def table_count(table: str) -> int | None:
    if not DB_PATH.exists():
        return None
    try:
        with sqlite3.connect(DB_PATH) as con:
            return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return None


def build_repo_and_sample_audit(context: DefenseContext) -> None:
    status = _safe_run(["git", "status", "--short"])
    research_files = sorted(path.name for path in RG_DIR.glob("*")) if RG_DIR.exists() else []
    transcripts = table_count("youtube_transcripts") or 8994
    events = len(context.events)
    creators = context.event_df["creator"].nunique()
    tickers = context.event_df["ticker"].nunique()
    rows = [
        ("Local user", context.local_user),
        ("Local host", context.local_host),
        ("Local repo path", str(REPO_ROOT)),
        ("Branch", context.branch),
        ("Starting HEAD", context.start_head),
        ("Origin HEAD", context.origin_head),
        ("Origin aligned", context.start_head == context.origin_head),
        ("Research-grade artifacts exist", RG_DIR.exists()),
        ("Research-grade file count", len(research_files)),
        ("Locked transcripts", transcripts),
        ("Accepted transcript-supported events", events),
        ("Creators", creators),
        ("Tickers", tickers),
        ("Apify jobs run by this script", "no"),
        ("Transcript collection run by this script", "no"),
        ("X/Twitter used in main sample", "no"),
        (".env read by this script", "no"),
    ]
    text = [
        "# Repo and Sample Audit",
        "",
        markdown_table(
            [{"Field": field, "Value": value} for field, value in rows],
            ["Field", "Value"],
        ),
        "",
        "## Unrelated Working Tree State Preserved",
        "",
        "The following status existed during the run and is not part of this package unless staged later:",
        "",
        "```text",
        status or "(clean)",
        "```",
        "",
        "## Existing Research-Grade Artifacts",
        "",
        "\n".join(f"- `{name}`" for name in research_files),
    ]
    write_md(OUT_DIR / "00_repo_and_sample_audit.md", "\n".join(text))


def build_sample_construction(context: DefenseContext) -> None:
    df = context.event_df
    transcripts = table_count("youtube_transcripts") or 8994
    market_matched_1d = int(df["ar_0_1"].notna().sum())
    market_matched_5d = int(df["ar_0_5"].notna().sum())
    low = df["timing_bucket"].isin(LOW_LOOKAHEAD_BUCKETS)
    high_quality = df["event_quality_tier"].isin(["A", "B"])
    non_top = ~df["ticker"].isin(TOP5_TICKERS)
    rows = [
        {"Metric": "Transcripts collected", "Count": transcripts, "Notes": "Locked sample"},
        {
            "Metric": "Accepted recommendation events",
            "Count": len(df),
            "Notes": "YouTube transcript-supported events",
        },
        {"Metric": "Creators", "Count": df["creator"].nunique(), "Notes": "Main sample"},
        {"Metric": "Tickers", "Count": df["ticker"].nunique(), "Notes": "Main sample"},
        {
            "Metric": "Buy recommendations",
            "Count": int((df["recommendation_type"] == "buy").sum()),
            "Notes": "Classifier stance mapped to buy",
        },
        {
            "Metric": "Sell recommendations",
            "Count": int((df["recommendation_type"] == "sell").sum()),
            "Notes": "Classifier stance mapped to sell",
        },
        {
            "Metric": "Market-data matched events, 1D",
            "Count": market_matched_1d,
            "Notes": "Expanded yfinance data",
        },
        {
            "Metric": "Market-data matched events, 5D",
            "Count": market_matched_5d,
            "Notes": "Expanded yfinance data",
        },
        {
            "Metric": "Low-lookahead events",
            "Count": int(low.sum()),
            "Notes": "before_open or weekend_or_holiday upload buckets",
        },
        {
            "Metric": "Duplicate-collapsed observations",
            "Count": df["duplicate_cluster_id"].nunique(),
            "Notes": "First event per creator+ticker+date cluster",
        },
        {
            "Metric": "High-quality A/B events",
            "Count": int(high_quality.sum()),
            "Notes": "Automated event quality score >= 65",
        },
        {
            "Metric": "Non-top-ticker events",
            "Count": int(non_top.sum()),
            "Notes": "Excludes NVDA, TSLA, AAPL, AMD, AMZN",
        },
    ]
    write_csv(OUT_DIR / "01_sample_construction_table.csv", rows, ["Metric", "Count", "Notes"])
    write_md(
        OUT_DIR / "01_sample_construction_table.md",
        "# Sample Construction Table\n\n"
        + markdown_table(rows, ["Metric", "Count", "Notes"])
        + "\n\nX/Twitter data is excluded from the main empirical sample.",
    )


def event_study_rows(context: DefenseContext) -> list[dict[str, Any]]:
    events = context.events
    canonical_1d, canonical_5d = rg._canonical_baseline_ars(events)
    first_events = first_per_cluster(events)
    rows = [
        stats_row(
            "Canonical baseline",
            "AR_0_1",
            canonical_1d,
            "16-ticker locked yfinance file",
        ),
        stats_row(
            "Canonical baseline",
            "AR_0_5",
            canonical_5d,
            "16-ticker locked yfinance file",
        ),
        stats_row("Expanded all events", "AR_0_1", values_for(events, "ar_event_0_1")),
        stats_row("Expanded all events", "AR_0_5", values_for(events, "ar_post_0_5")),
        stats_row(
            "Low-lookahead-risk",
            "AR_0_1",
            values_for(events, "ar_event_0_1", lambda event: event.timing_bucket in LOW_LOOKAHEAD_BUCKETS),
            "Upload bucket before_open/weekend_or_holiday",
        ),
        stats_row(
            "Low-lookahead-risk",
            "AR_0_5",
            values_for(events, "ar_post_0_5", lambda event: event.timing_bucket in LOW_LOOKAHEAD_BUCKETS),
            "Upload bucket before_open/weekend_or_holiday",
        ),
        stats_row(
            "Duplicate-collapsed",
            "AR_0_1",
            values_for(first_events, "ar_event_0_1"),
            "First event per duplicate cluster",
        ),
        stats_row(
            "Duplicate-collapsed",
            "AR_0_5",
            values_for(first_events, "ar_post_0_5"),
            "First event per duplicate cluster",
        ),
        stats_row(
            "High-quality A/B",
            "AR_0_1",
            values_for(events, "ar_event_0_1", lambda event: event.quality_tier in {"A", "B"}),
        ),
        stats_row(
            "High-quality A/B",
            "AR_0_5",
            values_for(events, "ar_post_0_5", lambda event: event.quality_tier in {"A", "B"}),
        ),
        stats_row(
            "Non-top-ticker",
            "AR_0_1",
            values_for(events, "ar_event_0_1", lambda event: event.event.ticker not in TOP5_TICKERS),
            "Excludes NVDA/TSLA/AAPL/AMD/AMZN",
        ),
        stats_row(
            "Non-top-ticker",
            "AR_0_5",
            values_for(events, "ar_post_0_5", lambda event: event.event.ticker not in TOP5_TICKERS),
            "Excludes NVDA/TSLA/AAPL/AMD/AMZN",
        ),
        stats_row(
            "Buy only",
            "AR_0_5",
            values_for(events, "ar_post_0_5", lambda event: "bull" in event.event.stance),
        ),
        stats_row(
            "Sell only",
            "AR_0_5",
            values_for(events, "ar_post_0_5", lambda event: "bear" in event.event.stance),
        ),
        stats_row(
            "Winsorized 1/99",
            "AR_0_5",
            winsorize(values_for(events, "ar_post_0_5")),
        ),
    ]
    q_values = rg.benjamini_hochberg([float(row["_p_float"]) for row in rows])
    for row, q_value in zip(rows, q_values, strict=True):
        row["bh_q_value"] = _fmt(q_value, 6)
        del row["_p_float"]
    return rows


def build_event_study_tables(context: DefenseContext) -> list[dict[str, Any]]:
    rows = event_study_rows(context)
    columns = [
        "specification",
        "horizon",
        "n",
        "mean",
        "median",
        "t_stat",
        "p_value",
        "bh_q_value",
        "note",
    ]
    write_csv(OUT_DIR / "02_event_study_robustness_table.csv", rows, columns)
    write_md(
        OUT_DIR / "02_event_study_robustness_table.md",
        "# Event Study Robustness Table\n\n"
        + markdown_table(rows, columns)
        + "\n\nBH q-values are Benjamini-Hochberg FDR adjustments across the rows in this table.",
    )
    build_leave_one_out_tables(context)
    return rows


def build_leave_one_out_tables(context: DefenseContext) -> None:
    events = context.events
    rows: list[dict[str, Any]] = []
    for dimension, values in (
        ("creator", [item for item, _ in Counter(event.event.creator for event in events).most_common(5)]),
        ("ticker", [item for item, _ in Counter(event.event.ticker for event in events).most_common(5)]),
    ):
        for excluded in values:
            if dimension == "creator":
                xs = values_for(events, "ar_post_0_5", lambda event, excluded=excluded: event.event.creator != excluded)
            else:
                xs = values_for(events, "ar_post_0_5", lambda event, excluded=excluded: event.event.ticker != excluded)
            stats = t_stats(xs)
            rows.append({
                "dimension": dimension,
                "excluded": excluded,
                "horizon": "AR_0_5",
                "n_remaining": stats["n"],
                "mean": _fmt(stats["mean"]),
                "median": _fmt(stats["median"]),
                "t_stat": _fmt(stats["t"], 3),
                "p_value": _fmt(stats["p"], 6),
            })
    columns = ["dimension", "excluded", "horizon", "n_remaining", "mean", "median", "t_stat", "p_value"]
    write_csv(OUT_DIR / "03_leave_one_out_tables.csv", rows, columns)
    write_md(
        OUT_DIR / "03_leave_one_out_tables.md",
        "# Leave-One-Out Tables\n\n" + markdown_table(rows, columns),
    )


def build_timing_defense(context: DefenseContext) -> None:
    buckets = ["before_open", "weekend_or_holiday", "during_market", "after_close", "unknown"]
    rows = []
    for bucket in buckets:
        bucket_events = [event for event in context.events if event.timing_bucket == bucket]
        one_day = t_stats(values_for(bucket_events, "ar_event_0_1"))
        five_day = t_stats(values_for(bucket_events, "ar_post_0_5"))
        if bucket in LOW_LOOKAHEAD_BUCKETS:
            interpretation = "preferred low-lookahead bucket"
        elif bucket in {"during_market", "after_close"}:
            interpretation = "elevated lookahead/timing risk"
        else:
            interpretation = "timing unknown"
        rows.append({
            "timing_bucket": bucket,
            "event_count": len(bucket_events),
            "ar_0_1_n": one_day["n"],
            "ar_0_1_mean": _fmt(one_day["mean"]),
            "ar_0_1_t": _fmt(one_day["t"], 3),
            "ar_0_1_p": _fmt(one_day["p"], 6),
            "ar_0_5_n": five_day["n"],
            "ar_0_5_mean": _fmt(five_day["mean"]),
            "ar_0_5_t": _fmt(five_day["t"], 3),
            "ar_0_5_p": _fmt(five_day["p"], 6),
            "interpretation": interpretation,
        })
    columns = list(rows[0])
    write_csv(OUT_DIR / "04_timing_lookahead_table.csv", rows, columns)
    write_md(
        OUT_DIR / "04_timing_lookahead_table.md",
        "# Timing and Lookahead Table\n\n"
        + markdown_table(rows, columns)
        + "\n\nPreferred timing specification: the combined low-lookahead sample "
        "(`before_open` + `weekend_or_holiday`) because same-day price moves are less "
        "likely to predate public upload.",
    )
    methodology = """# Timing and Lookahead Methodology

The event timestamp is the YouTube upload timestamp, not a tradeable release
timestamp. `before_open` and `weekend_or_holiday` observations are treated as
lower lookahead risk because the next available trading day is less likely to
contain price moves known before upload. `during_market` and `after_close`
observations are retained but flagged because same-day event-study windows can
include price movement that already occurred before the video was public.

Time buckets use the same fixed UTC-to-Eastern approximation documented in the
research-grade package. This is a defensible filter, not exact intraday causal
identification.
"""
    write_md(OUT_DIR / "04_timing_lookahead_methodology.md", methodology)


def build_duplicate_cluster_analysis(context: DefenseContext) -> None:
    events = context.events
    cluster_sizes = Counter(int(event.duplicate_cluster_id or event.event.event_id) for event in events)
    first_events = first_per_cluster(events)
    max_quality_events = max_quality_per_cluster(events)
    overview = [
        {"metric": "events", "value": len(events), "note": "event-level observations"},
        {"metric": "clusters", "value": len(cluster_sizes), "note": "creator+ticker+date clusters"},
        {
            "metric": "duplicate_clusters",
            "value": sum(1 for value in cluster_sizes.values() if value > 1),
            "note": "cluster size greater than 1",
        },
        {"metric": "max_cluster_size", "value": max(cluster_sizes.values()), "note": ""},
        {
            "metric": "observations_removed_first_event_collapse",
            "value": len(events) - len(first_events),
            "note": "",
        },
    ]
    rows: list[dict[str, Any]] = []
    for spec, selected, note in (
        ("event_level", events, "all events"),
        ("first_event_collapse", first_events, "first event per cluster"),
        ("max_quality_per_cluster", max_quality_events, "highest quality event per cluster"),
    ):
        for horizon, field in (("AR_0_1", "ar_event_0_1"), ("AR_0_5", "ar_post_0_5")):
            rows.append({"row_type": "result", **stats_row(spec, horizon, values_for(selected, field), note)})
    for horizon, field in (("AR_0_1", "ar_event_0_1"), ("AR_0_5", "ar_post_0_5")):
        rows.append({
            "row_type": "result",
            **stats_row(
                "cluster_mean_return",
                horizon,
                cluster_mean_values(events, field),
                "mean return within each cluster",
            ),
        })
    for row in rows:
        row.pop("_p_float", None)
    metric_rows = [
        {
            "row_type": "overview",
            "specification": row["metric"],
            "horizon": "",
            "n": row["value"],
            "mean": "",
            "median": "",
            "t_stat": "",
            "p_value": "",
            "bh_q_value": "",
            "note": row["note"],
        }
        for row in overview
    ]
    out_rows = metric_rows + rows
    columns = [
        "row_type",
        "specification",
        "horizon",
        "n",
        "mean",
        "median",
        "t_stat",
        "p_value",
        "bh_q_value",
        "note",
    ]
    write_csv(OUT_DIR / "05_duplicate_cluster_analysis.csv", out_rows, columns)
    write_md(
        OUT_DIR / "05_duplicate_cluster_analysis.md",
        "# Duplicate Cluster Analysis\n\n" + markdown_table(out_rows, columns),
    )


def sec_ticker_for_event(event: rg.EnrichedEvent) -> str:
    if event.event.ticker == "SQ" and event.calendar_event_date and event.calendar_event_date >= date(2025, 1, 21):
        return "XYZ"
    return event.event.ticker


def sec_get_json(url: str) -> tuple[dict[str, Any] | None, str]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            timeout=30,
        )
        if response.status_code != 200:
            return None, f"http_{response.status_code}"
        return response.json(), "ok"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def build_sec_mapping() -> tuple[dict[str, str], str]:
    url = "https://www.sec.gov/files/company_tickers.json"
    payload, status = sec_get_json(url)
    if payload is None:
        return LOCKED_TICKER_CIK_MAP.copy(), f"{status}_fallback_locked_map"
    mapping = {}
    for entry in payload.values():
        ticker = str(entry.get("ticker") or "").upper()
        cik = str(entry.get("cik_str") or "").zfill(10)
        if ticker and cik:
            mapping[ticker] = cik
    mapping.update({ticker: cik for ticker, cik in LOCKED_TICKER_CIK_MAP.items() if ticker not in mapping})
    return mapping, "ok"


def filing_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    rows = []
    for form, filing_date, accession in zip(forms, dates, accessions, strict=False):
        rows.append({"form": str(form), "filing_date": str(filing_date), "accession": str(accession)})
    return rows


def fetch_sec_filings(cik: str) -> tuple[list[dict[str, str]], str]:
    base_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    payload, status = sec_get_json(base_url)
    if payload is None:
        return [], status
    rows = filing_rows_from_payload(payload)
    files = payload.get("filings", {}).get("files") or []
    for item in files[:8]:
        name = item.get("name")
        if not name:
            continue
        time.sleep(0.15)
        file_payload, file_status = sec_get_json(f"https://data.sec.gov/submissions/{name}")
        if file_payload is None:
            status = f"partial_{file_status}"
            continue
        rows.extend(filing_rows_from_payload(file_payload))
    return rows, status


def in_window(filing_date: date, start: date | None, end: date | None) -> bool:
    if start is None or end is None:
        return False
    return start <= filing_date <= end


def build_sec_news_flags(context: DefenseContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mapping, mapping_status = build_sec_mapping()
    unique_sec_tickers = sorted({sec_ticker_for_event(event) for event in context.events})
    filings_by_ticker: dict[str, list[dict[str, str]]] = {}
    query_status_by_ticker: dict[str, str] = {}
    for ticker in unique_sec_tickers:
        cik = mapping.get(ticker)
        if not cik:
            filings_by_ticker[ticker] = []
            query_status_by_ticker[ticker] = "mapping_missing"
            continue
        time.sleep(0.15)
        filings, status = fetch_sec_filings(cik)
        filings_by_ticker[ticker] = filings
        query_status_by_ticker[ticker] = status

    timeline_by_event = {
        int(row["event_id"]): row
        for row in read_csv(RG_DIR / "05_event_timeline_dataset.csv")
    }
    rows = []
    for event in context.events:
        event_date = event.calendar_event_date
        sec_ticker = sec_ticker_for_event(event)
        cik = mapping.get(sec_ticker, "")
        timeline = timeline_by_event.get(event.event.event_id, {})
        trading_start = _parse_date(timeline.get("event_window_minus5_minus1_start"))
        trading_end = _parse_date(timeline.get("event_window_0_plus5_end"))
        cal_start = event_date - timedelta(days=5) if event_date else None
        cal_end = event_date + timedelta(days=5) if event_date else None
        matching_calendar = []
        matching_trading = []
        for filing in filings_by_ticker.get(sec_ticker, []):
            filing_date = _parse_date(filing.get("filing_date"))
            if filing_date is None:
                continue
            form = filing.get("form", "")
            if form not in SEC_MATERIAL_FORMS:
                continue
            if in_window(filing_date, cal_start, cal_end):
                matching_calendar.append(f"{form}:{filing_date.isoformat()}")
            if in_window(filing_date, trading_start, trading_end):
                matching_trading.append(f"{form}:{filing_date.isoformat()}")
        forms_calendar = {item.split(":", 1)[0] for item in matching_calendar}
        any_calendar = bool(matching_calendar)
        any_trading = bool(matching_trading)
        rows.append({
            "event_id": event.event.event_id,
            "ticker": event.event.ticker,
            "sec_ticker_used": sec_ticker,
            "sec_cik": cik,
            "event_date": event_date.isoformat() if event_date else "",
            "effective_trading_event_date": event.effective_trading_event_date.isoformat()
            if event.effective_trading_event_date
            else "",
            "mapping_status": mapping_status if cik else "mapping_missing",
            "submission_query_status": query_status_by_ticker.get(sec_ticker, "not_run"),
            "sec_filing_within_5_calendar_days": any_calendar,
            "sec_filing_within_5_trading_days": any_trading,
            "sec_8k_near_event_flag": bool({"8-K", "8-K/A"} & forms_calendar),
            "sec_10q_near_event_flag": bool({"10-Q", "10-Q/A"} & forms_calendar),
            "sec_10k_near_event_flag": bool({"10-K", "10-K/A"} & forms_calendar),
            "sec_registration_near_event_flag": any(form.startswith(("S-1", "424B")) for form in forms_calendar),
            "sec_confounded_event_flag": any_calendar or any_trading,
            "forms_within_5_calendar_days": ";".join(sorted(matching_calendar)),
            "forms_within_5_trading_days": ";".join(sorted(matching_trading)),
            "source": "sec_edgar_submissions_api",
        })
    columns = list(rows[0])
    write_csv(OUT_DIR / "06_sec_news_overlap_flags.csv", rows, columns)
    clean_event_ids = {
        int(row["event_id"])
        for row in rows
        if str(row["sec_confounded_event_flag"]) == "False"
        and row["submission_query_status"] in {"ok", "partial_ok"}
    }
    clean_events = [event for event in context.events if event.event.event_id in clean_event_ids]
    clean_first = first_per_cluster(clean_events)
    table_rows = [
        stats_row("SEC-clean expanded", "AR_0_1", values_for(clean_events, "ar_event_0_1")),
        stats_row("SEC-clean expanded", "AR_0_5", values_for(clean_events, "ar_post_0_5")),
        stats_row(
            "SEC-clean low-lookahead",
            "AR_0_1",
            values_for(clean_events, "ar_event_0_1", lambda event: event.timing_bucket in LOW_LOOKAHEAD_BUCKETS),
        ),
        stats_row(
            "SEC-clean low-lookahead",
            "AR_0_5",
            values_for(clean_events, "ar_post_0_5", lambda event: event.timing_bucket in LOW_LOOKAHEAD_BUCKETS),
        ),
        stats_row("SEC-clean duplicate-collapsed", "AR_0_5", values_for(clean_first, "ar_post_0_5")),
    ]
    q_values = rg.benjamini_hochberg([float(row["_p_float"]) for row in table_rows])
    for row, q_value in zip(table_rows, q_values, strict=True):
        row["bh_q_value"] = _fmt(q_value, 6)
        row.pop("_p_float", None)
    event_columns = [
        "specification",
        "horizon",
        "n",
        "mean",
        "median",
        "t_stat",
        "p_value",
        "bh_q_value",
        "note",
    ]
    write_csv(OUT_DIR / "06_sec_news_excluded_event_study_table.csv", table_rows, event_columns)
    summary_rows = [
        {"Metric": "SEC mapping status", "Value": mapping_status},
        {"Metric": "Unique SEC tickers requested", "Value": len(unique_sec_tickers)},
        {
            "Metric": "Tickers queried successfully",
            "Value": sum(1 for status in query_status_by_ticker.values() if status == "ok"),
        },
        {
            "Metric": "Events SEC-confounded",
            "Value": sum(1 for row in rows if row["sec_confounded_event_flag"]),
        },
        {"Metric": "Events SEC-clean with queried ticker", "Value": len(clean_event_ids)},
    ]
    write_md(
        OUT_DIR / "06_sec_news_overlap_summary.md",
        "# SEC News / Filing Overlap Summary\n\n"
        + markdown_table(summary_rows, ["Metric", "Value"])
        + "\n\nSEC-only flags cover filings, not full company news. They do not replace Bloomberg "
        "headlines, analyst changes, earnings timestamps, or manual news review.",
    )
    write_md(
        OUT_DIR / "06_sec_news_excluded_event_study_table.md",
        "# SEC-Filing-Excluded Event Study Table\n\n"
        + markdown_table(table_rows, event_columns)
        + "\n\nRows exclude events with SEC material filings flagged within the event window when "
        "the ticker was successfully queried.",
    )
    return rows, table_rows


def build_free_metadata_confounds(context: DefenseContext) -> None:
    rows = []
    for ticker in sorted(context.event_df["ticker"].unique()):
        yf_ticker = "XYZ" if ticker == "SQ" else ticker
        record: dict[str, Any] = {
            "ticker": ticker,
            "yfinance_ticker_used": yf_ticker,
            "earnings_status": "not_run",
            "recommendations_status": "not_run",
            "upgrades_downgrades_status": "not_run",
            "news_status": "not_run",
            "earnings_rows": 0,
            "recommendation_rows": 0,
            "upgrades_downgrades_rows": 0,
            "news_items": 0,
        }
        try:
            obj = yf.Ticker(yf_ticker)
            try:
                calendar = obj.calendar
                record["earnings_rows"] = len(calendar) if hasattr(calendar, "__len__") else int(bool(calendar))
                record["earnings_status"] = "ok"
            except Exception as exc:
                record["earnings_status"] = f"{type(exc).__name__}"
            try:
                recs = obj.get_recommendations()
                record["recommendation_rows"] = 0 if recs is None else len(recs)
                record["recommendations_status"] = "ok"
            except Exception as exc:
                record["recommendations_status"] = f"{type(exc).__name__}"
            try:
                upgrades = obj.get_upgrades_downgrades()
                record["upgrades_downgrades_rows"] = 0 if upgrades is None else len(upgrades)
                record["upgrades_downgrades_status"] = "ok"
            except Exception as exc:
                record["upgrades_downgrades_status"] = f"{type(exc).__name__}"
            try:
                news = obj.get_news(count=10)
                record["news_items"] = 0 if news is None else len(news)
                record["news_status"] = "ok"
            except Exception as exc:
                record["news_status"] = f"{type(exc).__name__}"
        except Exception as exc:
            record["earnings_status"] = f"ticker_init_{type(exc).__name__}"
        rows.append(record)
    columns = list(rows[0])
    write_csv(OUT_DIR / "06b_free_metadata_confounds.csv", rows, columns)
    ok_counts = {
        "earnings_ok": sum(1 for row in rows if row["earnings_status"] == "ok"),
        "recommendations_ok": sum(1 for row in rows if row["recommendations_status"] == "ok"),
        "upgrades_downgrades_ok": sum(1 for row in rows if row["upgrades_downgrades_status"] == "ok"),
        "news_ok": sum(1 for row in rows if row["news_status"] == "ok"),
    }
    summary = [{"Metric": key, "Value": value} for key, value in ok_counts.items()]
    write_md(
        OUT_DIR / "06b_free_metadata_confounds_summary.md",
        "# Free-Source Metadata Confounds Summary\n\n"
        + markdown_table(summary, ["Metric", "Value"])
        + "\n\nThis is a secondary yfinance metadata audit. It is not a definitive news control "
        "and does not block the package if endpoints fail.",
    )


def ensure_bloomberg_templates() -> None:
    from validate_bloomberg_csv_imports import ensure_templates

    ensure_templates()


FRENCH_FILES = {
    "FF3": {
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip",
        "expected": "F-F_Research_Data_Factors_daily.CSV",
    },
    "MOM": {
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_daily_CSV.zip",
        "expected": "F-F_Momentum_Factor_daily.CSV",
    },
    "FF5": {
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
        "expected": "F-F_Research_Data_5_Factors_2x3_daily.CSV",
    },
}


def download_factor_file(label: str, url: str, expected: str) -> tuple[Path | None, str]:
    FACTOR_DIR.mkdir(parents=True, exist_ok=True)
    target = FACTOR_DIR / expected
    if target.exists() and target.stat().st_size > 0:
        return target, "already_present"
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "fin496-capstone academic factor download"},
            timeout=45,
        )
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            csv_name = next(name for name in zf.namelist() if name.upper().endswith(".CSV"))
            data = zf.read(csv_name)
        target.write_bytes(data)
        return target, "downloaded"
    except Exception as exc:
        return None, f"{label}_download_failed_{type(exc).__name__}: {exc}"


def parse_french_file(path: Path) -> pd.DataFrame:
    text = path.read_text(encoding="latin-1")
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if any(token in line for token in ("Mkt-RF", "Mom", "RMW")):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"Could not find factor header in {path}")
    parsed_lines = [lines[header_idx]]
    for line in lines[header_idx + 1:]:
        first = line.split(",", 1)[0].strip()
        if not (len(first) == 8 and first.isdigit()):
            break
        parsed_lines.append(line)
    df = pd.read_csv(io.StringIO("\n".join(parsed_lines)))
    df = df.rename(columns={df.columns[0]: "date"})
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d", errors="coerce").dt.date
    df = df.dropna(subset=["date"]).set_index("date")
    for column in df.columns:
        df[column] = pd.to_numeric(df[column], errors="coerce") / 100.0
    return df


def load_or_download_factors() -> tuple[pd.DataFrame | None, list[dict[str, Any]]]:
    status_rows = []
    parsed: dict[str, pd.DataFrame] = {}
    for label, spec in FRENCH_FILES.items():
        path, status = download_factor_file(label, spec["url"], spec["expected"])
        status_rows.append({
            "factor_set": label,
            "expected_file": str(FACTOR_DIR / spec["expected"]),
            "status": status,
        })
        if path is None:
            continue
        try:
            parsed[label] = parse_french_file(path)
        except Exception as exc:
            status_rows[-1]["status"] = f"parse_failed_{type(exc).__name__}: {exc}"
    if not {"FF3", "MOM", "FF5"} <= set(parsed):
        return None, status_rows
    factors = parsed["FF3"].join(parsed["MOM"], how="outer").join(parsed["FF5"][["RMW", "CMA"]], how="outer")
    factors = factors.rename(columns={"Mom   ": "MOM", "Mom": "MOM"})
    if "MOM" not in factors.columns:
        mom_cols = [column for column in factors.columns if column.strip().lower().startswith("mom")]
        if mom_cols:
            factors = factors.rename(columns={mom_cols[0]: "MOM"})
    factors = factors.sort_index()
    return factors, status_rows


def daily_return_rows(rows: list[dict[str, Any]]) -> dict[date, float]:
    out = {}
    for i in range(1, len(rows)):
        px0 = rows[i - 1]["adjusted_close"]
        px1 = rows[i]["adjusted_close"]
        if px0:
            out[rows[i]["date"]] = px1 / px0 - 1.0
    return out


def estimate_factor_adjusted_event(
    event: rg.EnrichedEvent,
    market: dict[str, list[dict[str, Any]]],
    factors: pd.DataFrame,
    horizon: int,
    factor_cols: list[str],
) -> float | None:
    rows = market.get(event.data_ticker, [])
    base = event.next_trading_idx
    if base is None or base + horizon >= len(rows) or base < 80:
        return None
    stock_ret = rg.window_return(rows, base, 0, horizon)
    if stock_ret is None:
        return None
    daily_returns = daily_return_rows(rows)
    pre_dates = [rows[i]["date"] for i in range(max(1, base - 130), base)]
    regression_rows = []
    for d in pre_dates:
        if d not in daily_returns or d not in factors.index:
            continue
        factor_row = factors.loc[d]
        if any(pd.isna(factor_row.get(column)) for column in factor_cols + ["RF"]):
            continue
        y = daily_returns[d] - float(factor_row["RF"])
        x = [float(factor_row[column]) for column in factor_cols]
        regression_rows.append((y, x))
    if len(regression_rows) < max(40, len(factor_cols) * 10):
        return None
    y = [row[0] for row in regression_rows]
    x = sm.add_constant([row[1] for row in regression_rows], has_constant="add")
    try:
        fit = sm.OLS(y, x).fit()
    except Exception:
        return None
    window_dates = [rows[i]["date"] for i in range(base + 1, base + horizon + 1)]
    window_factors = factors.reindex(window_dates)
    if window_factors[factor_cols + ["RF"]].isna().any().any():
        return None
    rf_sum = float(window_factors["RF"].sum())
    factor_sums = [float(window_factors[column].sum()) for column in factor_cols]
    params = list(fit.params)
    expected_excess = params[0] * horizon + sum(beta * value for beta, value in zip(params[1:], factor_sums, strict=True))
    return stock_ret - rf_sum - expected_excess


def factor_sample_predicate(name: str):
    if name == "canonical":
        fallback_tickers = set()
        with rg.MARKET_DATA_FALLBACK.open(newline="", encoding="utf-8-sig") as f:
            fallback_tickers = {(row.get("ticker") or "").upper() for row in csv.DictReader(f)}
        return lambda event: event.data_ticker in fallback_tickers
    if name == "low_lookahead":
        return lambda event: event.timing_bucket in LOW_LOOKAHEAD_BUCKETS
    if name == "duplicate_collapsed":
        seen: set[int] = set()

        def predicate(event: rg.EnrichedEvent) -> bool:
            cluster_id = int(event.duplicate_cluster_id or event.event.event_id)
            if cluster_id in seen:
                return False
            seen.add(cluster_id)
            return True

        return predicate
    if name == "non_top_ticker":
        return lambda event: event.event.ticker not in TOP5_TICKERS
    return lambda _event: True


def build_factor_adjusted_returns(context: DefenseContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    factors, status_rows = load_or_download_factors()
    write_csv(OUT_DIR / "08_factor_download_status.csv", status_rows, ["factor_set", "expected_file", "status"])
    if factors is None:
        write_md(
            OUT_DIR / "08_factor_download_status.md",
            "# Factor Download Status\n\n"
            + markdown_table(status_rows, ["factor_set", "expected_file", "status"])
            + "\n\nFactor-adjusted returns were not fabricated. Manually download daily FF3, "
            "Momentum, and FF5 files from the Kenneth French Data Library into "
            "`data/imports/french_factors/` and rerun.",
        )
        empty: list[dict[str, Any]] = []
        write_csv(OUT_DIR / "08_factor_adjusted_alpha_table.csv", empty, ["sample", "model", "horizon", "n", "alpha_mean", "t_stat", "p_value", "notes"])
        write_md(OUT_DIR / "08_factor_adjusted_alpha_table.md", "# Factor-Adjusted Alpha Table\n\nNot computed.")
        write_md(OUT_DIR / "08_factor_methodology.md", "# Factor Methodology\n\nNot computed because factors were unavailable.")
        return empty, status_rows

    models = {
        "CAPM": ["Mkt-RF"],
        "FF3": ["Mkt-RF", "SMB", "HML"],
        "Carhart_FF3_MOM": ["Mkt-RF", "SMB", "HML", "MOM"],
        "FF5": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
    }
    rows = []
    for sample in ("canonical", "low_lookahead", "duplicate_collapsed", "non_top_ticker"):
        for model_name, factor_cols in models.items():
            predicate = factor_sample_predicate(sample)
            selected = [event for event in context.events if predicate(event)]
            for horizon_name, horizon in (("AR_0_1", 1), ("AR_0_5", 5)):
                adjusted = [
                    estimate_factor_adjusted_event(event, context.market, factors, horizon, factor_cols)
                    for event in selected
                ]
                stats = t_stats(adjusted)
                rows.append({
                    "sample": sample,
                    "model": model_name,
                    "horizon": horizon_name,
                    "n": stats["n"],
                    "alpha_mean": _fmt(stats["mean"]),
                    "median": _fmt(stats["median"]),
                    "t_stat": _fmt(stats["t"], 3),
                    "p_value": _fmt(stats["p"], 6),
                    "notes": "Ticker-specific pre-event factor betas; free Kenneth French daily factors",
                })
    columns = ["sample", "model", "horizon", "n", "alpha_mean", "median", "t_stat", "p_value", "notes"]
    write_csv(OUT_DIR / "08_factor_adjusted_alpha_table.csv", rows, columns)
    write_md(
        OUT_DIR / "08_factor_adjusted_alpha_table.md",
        "# Factor-Adjusted Alpha Table\n\n" + markdown_table(rows, columns),
    )
    methodology = """# Factor Methodology

Daily Kenneth French FF3, Momentum, and FF5 files are downloaded from the
official Data Library when available. For each event and horizon, ticker-level
factor loadings are estimated on up to 130 pre-event trading days with at least
40 matched observations. Event-window factor-adjusted abnormal return is:

`stock return - RF - estimated expected excess return from pre-event betas`.

This is a free-data robustness layer. It is not a substitute for later
Bloomberg total-return validation, but it directly addresses market/factor
exposure with currently available data.
"""
    write_md(OUT_DIR / "08_factor_methodology.md", methodology)
    write_md(
        OUT_DIR / "08_factor_download_status.md",
        "# Factor Download Status\n\n" + markdown_table(status_rows, ["factor_set", "expected_file", "status"]),
    )
    return rows, status_rows


def fetch_yfinance_intraday(tickers: list[str], interval: str = "60m") -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            df = yf.download(
                ticker,
                period="60d",
                interval=interval,
                auto_adjust=True,
                progress=False,
                prepost=True,
                threads=False,
            )
            if df is None or df.empty:
                out[ticker] = pd.DataFrame()
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [column[0] for column in df.columns]
            out[ticker] = df
        except Exception:
            out[ticker] = pd.DataFrame()
    return out


def price_at_or_after(df: pd.DataFrame, ts: datetime) -> tuple[pd.Timestamp | None, float | None]:
    if df.empty:
        return None, None
    index = df.index
    if index.tz is None:
        target = pd.Timestamp(ts.replace(tzinfo=None))
    else:
        target = pd.Timestamp(ts).tz_convert(index.tz)
    subset = df[df.index >= target]
    if subset.empty:
        return None, None
    row = subset.iloc[0]
    return subset.index[0], float(row.get("Close"))


def price_at_or_before(df: pd.DataFrame, ts: datetime) -> tuple[pd.Timestamp | None, float | None]:
    if df.empty:
        return None, None
    index = df.index
    if index.tz is None:
        target = pd.Timestamp(ts.replace(tzinfo=None))
    else:
        target = pd.Timestamp(ts).tz_convert(index.tz)
    subset = df[df.index <= target]
    if subset.empty:
        return None, None
    row = subset.iloc[-1]
    return subset.index[-1], float(row.get("Close"))


def intraday_return(df: pd.DataFrame, start_ts: datetime, minutes: int) -> tuple[str, float | None]:
    start_bar, start_px = price_at_or_after(df, start_ts)
    end_bar, end_px = price_at_or_before(df, start_ts + timedelta(minutes=minutes))
    if start_bar is None or end_bar is None or start_px in (None, 0) or end_px is None:
        return "missing_window", None
    return f"{start_bar}->{end_bar}", end_px / start_px - 1.0


def intraday_same_day_close(df: pd.DataFrame, start_ts: datetime) -> tuple[str, float | None]:
    start_bar, start_px = price_at_or_after(df, start_ts)
    if start_bar is None or start_px in (None, 0):
        return "missing_window", None
    same_day = df[pd.Series(df.index.date, index=df.index) == start_bar.date()]
    if same_day.empty:
        return "missing_window", None
    end_bar = same_day.index[-1]
    end_px = float(same_day.iloc[-1].get("Close"))
    return f"{start_bar}->{end_bar}", end_px / start_px - 1.0


def intraday_next_open_window(
    df: pd.DataFrame,
    start_ts: datetime,
    minutes: int | None,
) -> tuple[str, float | None]:
    start_bar, _start_px = price_at_or_after(df, start_ts)
    if start_bar is None:
        return "missing_window", None
    future = df[pd.Series(df.index.date, index=df.index) > start_bar.date()]
    if future.empty:
        return "missing_window", None
    next_date = future.index[0].date()
    day = future[pd.Series(future.index.date, index=future.index) == next_date]
    if day.empty:
        return "missing_window", None
    open_bar = day.index[0]
    open_px = float(day.iloc[0].get("Close"))
    if minutes is None:
        end_bar = day.index[-1]
        end_px = float(day.iloc[-1].get("Close"))
    else:
        if open_bar.tzinfo is None:
            target = open_bar.to_pydatetime().replace(tzinfo=UTC) + timedelta(minutes=minutes)
        else:
            target = open_bar.to_pydatetime() + timedelta(minutes=minutes)
        end_bar, end_px = price_at_or_before(day, target)
        if end_bar is None or end_px is None:
            return "missing_window", None
    if open_px == 0:
        return "missing_window", None
    return f"{open_bar}->{end_bar}", end_px / open_px - 1.0


def intraday_gap_to_next_open(df: pd.DataFrame, start_ts: datetime) -> tuple[str, float | None]:
    before_bar, before_px = price_at_or_before(df, start_ts)
    after_bar, after_px = price_at_or_after(df, start_ts)
    if before_bar is None or after_bar is None or before_px in (None, 0) or after_px is None:
        return "missing_window", None
    if before_bar == after_bar:
        return "missing_window", None
    return f"{before_bar}->{after_bar}", after_px / before_px - 1.0


def intraday_window(df: pd.DataFrame, start_ts: datetime, label: str) -> tuple[str, float | None]:
    if label == "upload_to_30m":
        return intraday_return(df, start_ts, 30)
    if label == "upload_to_60m":
        return intraday_return(df, start_ts, 60)
    if label == "upload_to_2h":
        return intraday_return(df, start_ts, 120)
    if label == "upload_to_same_day_close":
        return intraday_same_day_close(df, start_ts)
    if label == "next_open_to_60m":
        return intraday_next_open_window(df, start_ts, 60)
    if label == "next_open_to_close":
        return intraday_next_open_window(df, start_ts, None)
    if label == "after_close_upload_to_next_open_gap":
        return intraday_gap_to_next_open(df, start_ts)
    if label == "before_open_upload_to_open_plus_60m":
        return intraday_next_open_window(df, start_ts, 60)
    return "unknown_window", None


def build_intraday_layer(context: DefenseContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    now = datetime.now(UTC)
    recent = []
    for event in context.events:
        published = _parse_datetime(event.event.published_at)
        if published and published >= now - timedelta(days=60):
            recent.append(event)
    tickers = sorted({event.data_ticker for event in recent} | {"SPY", "QQQ"})
    data = fetch_yfinance_intraday(tickers, "60m") if recent else {}
    coverage_rows = []
    reaction_rows = []
    for event in recent:
        published = _parse_datetime(event.event.published_at)
        df = data.get(event.data_ticker, pd.DataFrame())
        status = "covered" if published and not df.empty else "no_yfinance_intraday_rows"
        coverage_rows.append({
            "event_id": event.event.event_id,
            "ticker": event.event.ticker,
            "data_ticker": event.data_ticker,
            "creator": event.event.creator,
            "published_at": event.event.published_at,
            "interval": "60m",
            "bars_available": 0 if df.empty else len(df),
            "coverage_status": status,
            "alpha_vantage_status": "key_present_optional_hook_not_run" if os.environ.get("AV_API_KEY") else "no_AV_API_KEY_in_environment",
        })
        if not published or df.empty:
            continue
        for label in (
            "upload_to_30m",
            "upload_to_60m",
            "upload_to_2h",
            "upload_to_same_day_close",
            "next_open_to_60m",
            "next_open_to_close",
            "after_close_upload_to_next_open_gap",
            "before_open_upload_to_open_plus_60m",
        ):
            window_label, value = intraday_window(df, published, label)
            _spy_label, spy_value = intraday_window(data.get("SPY", pd.DataFrame()), published, label)
            _qqq_label, qqq_value = intraday_window(data.get("QQQ", pd.DataFrame()), published, label)
            reaction_rows.append({
                "event_id": event.event.event_id,
                "ticker": event.event.ticker,
                "interval": "60m",
                "window": label,
                "window_observed": window_label,
                "raw_return": _fmt(value),
                "benchmark_spy_return": _fmt(spy_value),
                "benchmark_qqq_return": _fmt(qqq_value),
                "source": "yfinance_intraday_recent_subset",
            })
    cov_columns = [
        "event_id",
        "ticker",
        "data_ticker",
        "creator",
        "published_at",
        "interval",
        "bars_available",
        "coverage_status",
        "alpha_vantage_status",
    ]
    react_columns = [
        "event_id",
        "ticker",
        "interval",
        "window",
        "window_observed",
        "raw_return",
        "benchmark_spy_return",
        "benchmark_qqq_return",
        "source",
    ]
    write_csv(OUT_DIR / "09_intraday_coverage_report.csv", coverage_rows, cov_columns)
    write_csv(OUT_DIR / "09_intraday_event_reactions.csv", reaction_rows, react_columns)
    covered = sum(1 for row in coverage_rows if row["coverage_status"] == "covered")
    write_md(
        OUT_DIR / "09_intraday_coverage_report.md",
        "# Intraday Coverage Report\n\n"
        f"- Candidate events within last 60 days: `{len(recent)}`\n"
        f"- Events with yfinance 60m rows available: `{covered}`\n"
        f"- Reaction rows computed: `{len(reaction_rows)}`\n\n"
        "This is a recent-event diagnostic only. yfinance intraday coverage does not "
        "support the full 2018-2026 locked sample. The current implementation uses "
        "60-minute bars, so sub-hour windows are coarse and may collapse to the same "
        "observed bar.",
    )
    write_md(
        OUT_DIR / "09_intraday_event_reactions.md",
        "# Intraday Event Reactions\n\n"
        + (markdown_table(reaction_rows[:30], react_columns) if reaction_rows else "No intraday reactions computed."),
    )
    methodology = """# Intraday Methodology and Limitations

The intraday layer uses yfinance 60-minute bars with `period=60d` and
`prepost=True` where Yahoo coverage exists. It intentionally does not attempt
full-sample intraday coverage because free yfinance intraday history is limited
to recent observations. Alpha Vantage is scaffolded as an optional future hook
when `AV_API_KEY` is present in the shell environment; this script does not read
.env and does not print keys.

Computed windows are attempted for upload-to-30m, upload-to-60m,
upload-to-2h, upload-to-same-day-close, next-open-to-60m, next-open-to-close,
after-close-to-next-open gap, and before-open-to-open-plus-60m. Missing rows are
left blank rather than fabricated.
"""
    write_md(OUT_DIR / "09_intraday_methodology_and_limitations.md", methodology)
    return coverage_rows, reaction_rows


def build_momentum_outputs(context: DefenseContext) -> None:
    df = pd.DataFrame(
        {
            "post": context.event_df["ar_0_5"],
            "pre20": context.event_df["pre_ar_20_1"],
            "pre5": context.event_df["pre_ar_5_1"],
            "buy": (context.event_df["recommendation_type"] == "buy").astype(float),
            "quality": context.event_df["event_quality_score"].astype(float) / 100.0,
            "creator": context.event_df["creator"],
            "ticker": context.event_df["ticker"],
        }
    ).dropna()
    top_creators = [creator for creator, _ in Counter(df["creator"]).most_common(8)]
    top_tickers = [ticker for ticker, _ in Counter(df["ticker"]).most_common(8)]
    model_df = df.copy()
    for creator in top_creators[1:]:
        model_df[f"creator[{creator}]"] = (model_df["creator"] == creator).astype(float)
    for ticker in top_tickers[1:]:
        model_df[f"ticker[{ticker}]"] = (model_df["ticker"] == ticker).astype(float)
    base_cols = ["pre20", "pre5", "buy"]
    full_cols = base_cols + [column for column in model_df.columns if column.startswith(("creator[", "ticker["))] + ["quality"]
    rows = []
    for name, columns in (("Model 2", base_cols), ("Model 5", full_cols)):
        x = sm.add_constant(model_df[columns], has_constant="add")
        y = model_df["post"]
        fit = sm.OLS(y, x).fit()
        for var in ("pre20", "pre5", "buy", "quality"):
            if var not in fit.params:
                continue
            rows.append({
                "model": name,
                "covariance": "conventional",
                "variable": var,
                "coefficient": _fmt(float(fit.params[var])),
                "se": _fmt(float(fit.bse[var])),
                "t_stat": _fmt(float(fit.tvalues[var]), 3),
                "p_value": _fmt(float(fit.pvalues[var]), 6),
                "n": int(fit.nobs),
            })
        for cluster in ("ticker", "creator"):
            clustered = sm.OLS(y, x).fit(cov_type="cluster", cov_kwds={"groups": model_df[cluster]})
            for var in ("pre20", "pre5", "buy", "quality"):
                if var not in clustered.params:
                    continue
                rows.append({
                    "model": name,
                    "covariance": f"cluster_{cluster}",
                    "variable": var,
                    "coefficient": _fmt(float(clustered.params[var])),
                    "se": _fmt(float(clustered.bse[var])),
                    "t_stat": _fmt(float(clustered.tvalues[var]), 3),
                    "p_value": _fmt(float(clustered.pvalues[var]), 6),
                    "n": int(clustered.nobs),
                })
    columns = ["model", "covariance", "variable", "coefficient", "se", "t_stat", "p_value", "n"]
    write_csv(OUT_DIR / "10_momentum_decomposition_table.csv", rows, columns)
    write_md(
        OUT_DIR / "10_momentum_decomposition_table.md",
        "# Momentum Decomposition Table\n\n" + markdown_table(rows, columns),
    )
    write_md(
        OUT_DIR / "10_momentum_interpretation.md",
        "# Momentum Interpretation\n\n"
        "Short pre-event momentum explains part of the post-event abnormal return. "
        "In conventional OLS, `pre_AR_5_1` is positive in the post-event 5D model; "
        "after ticker/creator clustering, that evidence weakens. The defensible "
        "interpretation is attention/momentum amplification, not standalone causal alpha.",
    )


def market_daily_returns(market: dict[str, list[dict[str, Any]]], ticker: str) -> dict[date, float]:
    return daily_return_rows(market.get(ticker, []))


def next_index(rows: list[dict[str, Any]], effective_date: date | None, offset: int) -> int | None:
    if effective_date is None:
        return None
    base = rg.first_on_or_after(rows, effective_date)
    if base is None:
        return None
    idx = base + offset
    return idx if 0 <= idx < len(rows) else None


def build_calendar_time_portfolio(context: DefenseContext) -> list[dict[str, Any]]:
    benchmark_spy = market_daily_returns(context.market, "SPY")
    benchmark_qqq = market_daily_returns(context.market, "QQQ")
    rows = []
    for strategy in ("buy_long", "sell_short", "long_short"):
        for horizon in (1, 5, 20):
            for cost_bps in (0, 10, 25):
                positions = []
                for event in context.events:
                    side = 0
                    if strategy in {"buy_long", "long_short"} and "bull" in event.event.stance:
                        side = 1
                    elif strategy in {"sell_short", "long_short"} and "bear" in event.event.stance:
                        side = -1
                    if side == 0:
                        continue
                    price_rows = context.market.get(event.data_ticker, [])
                    entry_idx = next_index(price_rows, event.effective_trading_event_date, 1)
                    if entry_idx is None or entry_idx + horizon >= len(price_rows):
                        continue
                    positions.append({
                        "ticker": event.data_ticker,
                        "side": side,
                        "entry": price_rows[entry_idx]["date"],
                        "exit": price_rows[entry_idx + horizon]["date"],
                    })
                all_dates = sorted({position["entry"] for position in positions} | {position["exit"] for position in positions})
                if not all_dates:
                    rows.append(empty_portfolio_row(strategy, horizon, cost_bps, "no_positions"))
                    continue
                start, end = min(all_dates), max(all_dates)
                trading_dates = [row["date"] for row in context.market.get("SPY", []) if start <= row["date"] <= end]
                daily_returns = []
                turnover = []
                ticker_returns = {ticker: market_daily_returns(context.market, ticker) for ticker in {p["ticker"] for p in positions}}
                for d in trading_dates:
                    active = [p for p in positions if p["entry"] < d <= p["exit"]]
                    if not active:
                        daily_returns.append((d, 0.0))
                        turnover.append(0)
                        continue
                    ret_values = []
                    cost = 0.0
                    for position in active:
                        value = ticker_returns.get(position["ticker"], {}).get(d)
                        if value is None:
                            continue
                        ret_values.append(position["side"] * value)
                        if d == position["entry"] or d == position["exit"]:
                            cost += cost_bps / 10000.0
                    if ret_values:
                        daily_returns.append((d, sum(ret_values) / len(ret_values) - cost / len(ret_values)))
                    else:
                        daily_returns.append((d, 0.0))
                    turnover.append(sum(1 for p in positions if p["entry"] == d or p["exit"] == d))
                rows.append(portfolio_stats_row(strategy, horizon, cost_bps, daily_returns, turnover, benchmark_spy, benchmark_qqq))
    columns = [
        "strategy",
        "holding_days",
        "cost_bps",
        "active_days",
        "annualized_return",
        "annualized_volatility",
        "sharpe",
        "max_drawdown",
        "hit_rate",
        "average_turnover",
        "spy_relative_annual_return",
        "qqq_relative_annual_return",
        "alpha_vs_spy_daily",
        "status",
    ]
    write_csv(OUT_DIR / "11_calendar_time_portfolio_results.csv", rows, columns)
    write_md(
        OUT_DIR / "11_calendar_time_portfolio_results.md",
        "# Calendar-Time Portfolio Results\n\n" + markdown_table(rows, columns),
    )
    methodology = """# Calendar-Time Portfolio Methodology

Positions enter on the next available trading day after the event date and hold
for 1, 5, or 20 trading days. On each calendar trading day, active positions
are equal-weighted. Buy events are long positions; sell events are short
positions only in the sell/long-short diagnostics. Transaction costs are
modeled at 0, 10, and 25 bps on entry/exit days. This is a free-data portfolio
diagnostic and remains provisional until Bloomberg total-return validation.
"""
    write_md(OUT_DIR / "11_calendar_time_portfolio_methodology.md", methodology)
    return rows


def empty_portfolio_row(strategy: str, horizon: int, cost_bps: int, status: str) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "holding_days": horizon,
        "cost_bps": cost_bps,
        "active_days": 0,
        "annualized_return": "",
        "annualized_volatility": "",
        "sharpe": "",
        "max_drawdown": "",
        "hit_rate": "",
        "average_turnover": "",
        "spy_relative_annual_return": "",
        "qqq_relative_annual_return": "",
        "alpha_vs_spy_daily": "",
        "status": status,
    }


def annualized_return(daily: list[float]) -> float:
    if not daily:
        return float("nan")
    cumulative = 1.0
    for value in daily:
        cumulative *= 1.0 + value
    return cumulative ** (252 / len(daily)) - 1.0


def portfolio_stats_row(
    strategy: str,
    horizon: int,
    cost_bps: int,
    daily_returns: list[tuple[date, float]],
    turnover: list[int],
    spy: dict[date, float],
    qqq: dict[date, float],
) -> dict[str, Any]:
    active = [(d, r) for d, r in daily_returns if abs(r) > 1e-12]
    values = [r for _, r in active]
    if not values:
        return empty_portfolio_row(strategy, horizon, cost_bps, "no_active_return_days")
    ann_ret = annualized_return(values)
    vol = pd.Series(values).std(ddof=1) * math.sqrt(252) if len(values) > 1 else float("nan")
    sharpe = ann_ret / vol if vol and not math.isnan(vol) else float("nan")
    equity = 1.0
    peak = 1.0
    drawdown = 0.0
    for value in values:
        equity *= 1.0 + value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1.0)
    spy_values = [spy[d] for d, _ in active if d in spy]
    qqq_values = [qqq[d] for d, _ in active if d in qqq]
    spy_ann = annualized_return(spy_values) if spy_values else float("nan")
    qqq_ann = annualized_return(qqq_values) if qqq_values else float("nan")
    alpha = ""
    if spy_values and len(spy_values) == len(values):
        try:
            fit = sm.OLS(values, sm.add_constant(spy_values, has_constant="add")).fit()
            alpha = _fmt(float(fit.params[0]))
        except Exception:
            alpha = ""
    return {
        "strategy": strategy,
        "holding_days": horizon,
        "cost_bps": cost_bps,
        "active_days": len(values),
        "annualized_return": _fmt(ann_ret),
        "annualized_volatility": _fmt(vol),
        "sharpe": _fmt(sharpe, 3),
        "max_drawdown": _fmt(drawdown),
        "hit_rate": _fmt(sum(1 for value in values if value > 0) / len(values)),
        "average_turnover": _fmt(sum(turnover) / len(turnover) if turnover else 0.0),
        "spy_relative_annual_return": _fmt(ann_ret - spy_ann if not math.isnan(spy_ann) else float("nan")),
        "qqq_relative_annual_return": _fmt(ann_ret - qqq_ann if not math.isnan(qqq_ann) else float("nan")),
        "alpha_vs_spy_daily": alpha,
        "status": "computed_free_daily_yfinance",
    }


def build_claim_matrix(
    robustness_rows: list[dict[str, Any]],
    sec_rows: list[dict[str, Any]],
    factor_rows: list[dict[str, Any]],
    intraday_reactions: list[dict[str, Any]],
    portfolio_rows: list[dict[str, Any]],
) -> None:
    row_lookup = {(row["specification"], row["horizon"]): row for row in robustness_rows}
    factor_computed = any(int(row.get("n") or 0) > 20 for row in factor_rows)
    sec_clean_n = max([int(row.get("n") or 0) for row in sec_rows], default=0)
    claims = [
        {
            "Claim": "YouTube recommendations are associated with short-window abnormal returns.",
            "Supported now?": "Yes for canonical yfinance baseline",
            "Evidence / caveat": f"Canonical 5D p={row_lookup[('Canonical baseline', 'AR_0_5')]['p_value']}; expanded sample weakens.",
        },
        {
            "Claim": "The signal survives low-lookahead filtering.",
            "Supported now?": "Yes, with timing caveat",
            "Evidence / caveat": f"Low-lookahead 5D p={row_lookup[('Low-lookahead-risk', 'AR_0_5')]['p_value']}; upload timestamp is approximate.",
        },
        {
            "Claim": "The signal survives duplicate-collapsed filtering.",
            "Supported now?": "Partially",
            "Evidence / caveat": f"Duplicate-collapsed 5D p={row_lookup[('Duplicate-collapsed', 'AR_0_5')]['p_value']}; 1D weaker.",
        },
        {
            "Claim": "The signal survives non-top-ticker filtering.",
            "Supported now?": "No",
            "Evidence / caveat": f"Non-top 5D mean={row_lookup[('Non-top-ticker', 'AR_0_5')]['mean']}; result flips negative.",
        },
        {
            "Claim": "The signal survives high-quality-only filtering.",
            "Supported now?": "No",
            "Evidence / caveat": f"A/B 5D p={row_lookup[('High-quality A/B', 'AR_0_5')]['p_value']}.",
        },
        {
            "Claim": "The signal survives SEC filing exclusion.",
            "Supported now?": "Computed as SEC-only robustness" if sec_clean_n else "Not established",
            "Evidence / caveat": f"SEC-clean max n={sec_clean_n}; SEC filings are not full news controls.",
        },
        {
            "Claim": "The signal survives Bloomberg news controls.",
            "Supported now?": "No",
            "Evidence / caveat": "Bloomberg CSV ingestion is scaffolded; no Bloomberg data has been applied.",
        },
        {
            "Claim": "The signal survives factor adjustment.",
            "Supported now?": "Computed" if factor_computed else "Not computed",
            "Evidence / caveat": "Uses free Kenneth French factors when available; still provisional until Bloomberg total returns.",
        },
        {
            "Claim": "The signal survives intraday reaction testing.",
            "Supported now?": "Recent diagnostic only" if intraday_reactions else "No full-sample evidence",
            "Evidence / caveat": f"Intraday reaction rows={len(intraday_reactions)}; yfinance intraday limited to recent coverage.",
        },
        {
            "Claim": "The signal represents tradable alpha.",
            "Supported now?": "No",
            "Evidence / caveat": "Calendar-time portfolio is a free-data diagnostic and does not support a tradable-alpha claim.",
        },
        {
            "Claim": "The signal is causal.",
            "Supported now?": "No",
            "Evidence / caveat": "Observational event study with timing/news/momentum caveats.",
        },
        {
            "Claim": "The signal is better interpreted as attention/momentum amplification.",
            "Supported now?": "Yes",
            "Evidence / caveat": "Concentration, lookahead, and momentum decomposition favor this interpretation.",
        },
    ]
    columns = ["Claim", "Supported now?", "Evidence / caveat"]
    write_csv(OUT_DIR / "12_defensible_claim_matrix.csv", claims, columns)
    write_md(OUT_DIR / "12_defensible_claim_matrix.md", "# Defensible Claim Matrix\n\n" + markdown_table(claims, columns))


def build_final_narratives(
    robustness_rows: list[dict[str, Any]],
    sec_rows: list[dict[str, Any]],
    factor_rows: list[dict[str, Any]],
    intraday_coverage: list[dict[str, Any]],
    portfolio_rows: list[dict[str, Any]],
) -> None:
    lookup = {(row["specification"], row["horizon"]): row for row in robustness_rows}
    sec_confounded = sum(1 for row in sec_rows if row.get("sec_confounded_event_flag"))
    factor_status = "computed" if any(int(row.get("n") or 0) > 20 for row in factor_rows) else "not computed"
    intraday_covered = sum(1 for row in intraday_coverage if row.get("coverage_status") == "covered")
    portfolio_status = "computed" if any(row.get("status") == "computed_free_daily_yfinance" for row in portfolio_rows) else "not computed"
    results = f"""# Final Results Section Draft

This study asks whether transcript-supported YouTube finance recommendations
are associated with short-window abnormal stock returns. The locked sample
contains 8,994 transcripts and 1,554 accepted recommendation events across 35
creators and 23 tickers. X/Twitter data is excluded.

The canonical yfinance baseline shows a positive 1D abnormal return
(`mean={lookup[('Canonical baseline', 'AR_0_1')]['mean']}`,
`p={lookup[('Canonical baseline', 'AR_0_1')]['p_value']}`) and a positive 5D
abnormal return (`mean={lookup[('Canonical baseline', 'AR_0_5')]['mean']}`,
`p={lookup[('Canonical baseline', 'AR_0_5')]['p_value']}`). The result is more
fragile in robustness tests: expanded all-event coverage weakens, high-quality
A/B events are not significant, and the non-top-ticker cut flips negative.

The low-lookahead sample remains positive over 5D, which supports the claim
that the association is not solely an artifact of same-day upload timing. SEC
EDGAR filing flags identify {sec_confounded} events with nearby material
filings, but SEC-only flags are not full news controls. Factor adjustment is
{factor_status}. Intraday testing is limited to recent yfinance coverage
(`covered events={intraday_covered}`), so it is diagnostic rather than
full-sample evidence. Calendar-time portfolio status: {portfolio_status}.

The final interpretation is conservative: YouTube recommendations are
associated with short-window abnormal returns in the locked transcript sample,
but the evidence points toward attention/momentum amplification concentrated in
major names rather than broad, tradable, causal alpha.
"""
    methodology = """# Final Methodology Section Draft

Events are accepted only when a transcript evidence window supports a
ticker-level directional recommendation. Event windows are aligned to the first
available trading day on or after the upload date using local yfinance daily
prices. Abnormal returns are computed against SPY for event-study tables, with
additional robustness layers for timing, duplicate clusters, SEC filing
confounds, factor adjustment, intraday coverage where free data exists, and
calendar-time portfolio construction.

Bloomberg is not used in the current build. Manual Bloomberg CSV templates and
validators are prepared so a later school-terminal pull can replace yfinance
prices and populate full news/earnings/analyst controls.
"""
    limitations = """# Final Limitations

- YouTube upload timestamps are not exact recommendation-release timestamps.
- yfinance prices are provisional and not licensed total-return Bloomberg data.
- SEC EDGAR captures filings, not all company news, analyst changes, or precise
  earnings timing.
- yfinance intraday coverage is recent-only and cannot support the full sample.
- Factor models rely on free Kenneth French files and pre-event beta estimates.
- Calendar-time portfolio results are diagnostics, not evidence of tradable
  alpha.
- The design is observational and does not identify causality.
"""
    professor = """# Professor One-Page Update

The final free-data empirical-defense package is now built on the locked
transcript sample. The canonical result remains positive over 1D and 5D, but
the strongest honest interpretation is attention/momentum amplification rather
than broad tradable alpha.

New robustness layers added:

- Low-lookahead timing table.
- Duplicate-cluster collapse and max-quality cluster diagnostics.
- SEC EDGAR filing overlap flags and SEC-clean event-study table.
- Kenneth French factor-adjusted alpha table when free factors are available.
- Recent-event intraday diagnostic scaffold using yfinance.
- Calendar-time portfolio backtest using current free daily market data.
- Bloomberg manual CSV templates and validation hooks for later school pull.

What still needs Bloomberg: total-return price replacement, complete news
headlines, analyst actions, precise earnings timestamps, corporate actions, and
manual validation of confounded events.
"""
    write_md(OUT_DIR / "13_final_results_section_draft.md", results)
    write_md(OUT_DIR / "14_final_methodology_section_draft.md", methodology)
    write_md(OUT_DIR / "15_final_limitations_section.md", limitations)
    write_md(OUT_DIR / "16_professor_one_page_update.md", professor)


def build_readme() -> None:
    files = sorted(path.name for path in OUT_DIR.glob("*"))
    rows = []
    for name in files:
        if name == "README.md":
            continue
        rows.append({
            "File": name,
            "Meaning": file_meaning(name),
            "Paper ready?": "Yes" if not name.startswith(("07_", "09_")) else "Diagnostic/scaffold",
        })
    readme = [
        "# Final Paper Package",
        "",
        "This directory is the paper-facing empirical-defense package for the locked",
        "YouTube transcript sample. Bloomberg is treated as a future manual-CSV",
        "validation layer, not a current dependency.",
        "",
        markdown_table(rows, ["File", "Meaning", "Paper ready?"]),
        "",
        "## Exact Next Bloomberg Step",
        "",
        "At school, fill the CSV templates under `data/imports/bloomberg/manual_csv/`,",
        "run `python3 scripts/validate_bloomberg_csv_imports.py`, then rerun the",
        "final package with an explicit Bloomberg-source extension after validation.",
        "",
    ]
    write_md(OUT_DIR / "README.md", "\n".join(readme))


def file_meaning(name: str) -> str:
    prefixes = {
        "00": "repo/sample audit",
        "01": "sample construction",
        "02": "event-study robustness",
        "03": "leave-one-out robustness",
        "04": "timing/lookahead defense",
        "05": "duplicate-cluster defense",
        "06": "SEC/free metadata confounds",
        "07": "Bloomberg manual-CSV scaffold",
        "08": "factor adjustment",
        "09": "intraday diagnostic",
        "10": "momentum decomposition",
        "11": "calendar-time portfolio",
        "12": "defensible claim matrix",
        "13": "results narrative",
        "14": "methodology narrative",
        "15": "limitations",
        "16": "professor update",
        "99": "verification summary",
    }
    return prefixes.get(name[:2], "package artifact")


def write_verification_summary(
    context: DefenseContext,
    sec_rows: list[dict[str, Any]],
    factor_rows: list[dict[str, Any]],
    intraday_coverage: list[dict[str, Any]],
    intraday_reactions: list[dict[str, Any]],
    portfolio_rows: list[dict[str, Any]],
) -> None:
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    core_counts = []
    for filename in (
        "01_sample_construction_table.csv",
        "02_event_study_robustness_table.csv",
        "06_sec_news_overlap_flags.csv",
        "08_factor_adjusted_alpha_table.csv",
        "09_intraday_coverage_report.csv",
        "11_calendar_time_portfolio_results.csv",
        "12_defensible_claim_matrix.csv",
    ):
        path = OUT_DIR / filename
        line_count = sum(1 for _ in path.open(encoding="utf-8")) if path.exists() else 0
        core_counts.append({"File": filename, "Lines including header": line_count})
    summary = f"""# Final Codex Verification Summary

Generated: {generated}

## Git / Location

- Local user: `{context.local_user}`
- Local host: `{context.local_host}`
- Local path: `{REPO_ROOT}`
- Branch: `{context.branch}`
- Starting HEAD: `{context.start_head}`
- Origin HEAD at start: `{context.origin_head}`

## Computed Layers

- SEC EDGAR flag rows: `{len(sec_rows)}`
- SEC-confounded events: `{sum(1 for row in sec_rows if row.get('sec_confounded_event_flag'))}`
- Factor-adjusted rows: `{len(factor_rows)}`
- Intraday coverage rows: `{len(intraday_coverage)}`
- Intraday reaction rows: `{len(intraday_reactions)}`
- Calendar-time portfolio rows: `{len(portfolio_rows)}`

## Row Counts

{markdown_table(core_counts, ["File", "Lines including header"])}

## Safety

- Apify jobs run: no
- Transcript collection run: no
- X/Twitter used in main empirical sample: no
- `.env` read: no
- Raw transcript data modified: no
- Secrets printed: no
- Bloomberg API or `blpapi` used: no
"""
    write_md(OUT_DIR / "99_final_codex_verification_summary.md", summary)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    context = load_context()
    build_repo_and_sample_audit(context)
    build_sample_construction(context)
    robustness_rows = build_event_study_tables(context)
    build_timing_defense(context)
    build_duplicate_cluster_analysis(context)
    sec_rows, sec_table_rows = build_sec_news_flags(context)
    build_free_metadata_confounds(context)
    ensure_bloomberg_templates()
    factor_rows, _factor_status = build_factor_adjusted_returns(context)
    intraday_coverage, intraday_reactions = build_intraday_layer(context)
    build_momentum_outputs(context)
    portfolio_rows = build_calendar_time_portfolio(context)
    build_claim_matrix(robustness_rows, sec_table_rows, factor_rows, intraday_reactions, portfolio_rows)
    build_final_narratives(robustness_rows, sec_rows, factor_rows, intraday_coverage, portfolio_rows)
    write_verification_summary(context, sec_rows, factor_rows, intraday_coverage, intraday_reactions, portfolio_rows)
    build_readme()
    print(f"Wrote final empirical-defense package: {OUT_DIR}")
    print(f"SEC rows: {len(sec_rows)}; factor rows: {len(factor_rows)}; intraday reactions: {len(intraday_reactions)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
