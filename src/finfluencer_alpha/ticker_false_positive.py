from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .config import EXPORTS_DIR, ensure_data_dirs
from .db import connect, init_db

EXCLUSION_FIELDS = [
    "exclusion_id",
    "event_id",
    "window_id",
    "ticker",
    "reason",
    "evidence_excerpt",
    "action",
    "created_at",
]


def _ensure_exclusion_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transcript_event_exclusions (
            exclusion_id INTEGER PRIMARY KEY,
            event_id INTEGER,
            window_id INTEGER,
            ticker TEXT NOT NULL,
            reason TEXT,
            evidence_excerpt TEXT,
            action TEXT DEFAULT 'exclude',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_exclusions_ticker
        ON transcript_event_exclusions(ticker)
        """
    )
    conn.commit()


def _audit_dir() -> Path:
    path = EXPORTS_DIR / "audits"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _report_ready_dir() -> Path:
    path = EXPORTS_DIR / "report_ready"
    path.mkdir(parents=True, exist_ok=True)
    return path


def audit_ticker_false_positives(
    ticker: str = "YOU",
) -> dict[str, Path]:
    init_db()
    ensure_data_dirs()
    _ensure_exclusion_table(connect())
    ticker = ticker.upper()

    with connect() as conn:
        windows = conn.execute(
            """
            SELECT tcw.*,
                   rv.channel_title, rv.title AS video_title,
                   rv.published_at AS video_published_at
            FROM transcript_candidate_windows tcw
            JOIN raw_youtube_videos rv ON rv.video_id = tcw.video_id
            WHERE tcw.ticker = ?
            ORDER BY tcw.created_at DESC
            """,
            (ticker,),
        ).fetchall()

        events = conn.execute(
            """
            SELECT tre.*,
                   rv.channel_title, rv.title AS video_title,
                   rv.published_at AS video_published_at
            FROM transcript_recommendation_events tre
            JOIN raw_youtube_videos rv ON rv.video_id = tre.video_id
            WHERE tre.ticker = ?
            ORDER BY tre.created_at DESC
            """,
            (ticker,),
        ).fetchall()

    audit_rows: list[dict[str, Any]] = []

    for w in windows:
        ew = w["evidence_window"] or ""
        fat = w["focused_action_text"] or ""
        evidence_lower = (ew + " " + fat).lower()

        has_cashtag = f"${ticker.lower()}" in evidence_lower or f"${ticker}" in (ew + " " + fat)
        has_clear_secure = "clear secure" in evidence_lower or "clear" in evidence_lower
        has_exchange = any(
            prefix in (ew + " " + fat)
            for prefix in [f"NYSE: {ticker}", f"NASDAQ: {ticker}", f"nyse: {ticker}", f"nasdaq: {ticker}"]
        )
        has_stock_context = any(
            phrase in evidence_lower
            for phrase in [
                f"{ticker.lower()} stock", f"{ticker.lower()} shares",
                f"{ticker.lower()} earnings", f"{ticker.lower()} revenue",
                f"buy {ticker.lower()}", f"sell {ticker.lower()}",
                f"long {ticker.lower()}", f"short {ticker.lower()}",
            ]
        )

        appears_ordinary = False
        if ticker in ("YOU",):
            ordinary_phrases = [
                "you should", "you know", "you can", "if you", "when you",
                "what you", "how you", "why you", "that you", "and you",
                "for you", "with you", "to you", "of you", "do you",
                "thank you", "love you", "are you", "did you",
            ]
            appears_ordinary = any(phrase in evidence_lower for phrase in ordinary_phrases)

        if has_cashtag or has_clear_secure or has_exchange or has_stock_context:
            recommendation = "keep"
        elif appears_ordinary:
            recommendation = "exclude_false_positive"
        else:
            recommendation = "manual_review"

        audit_rows.append({
            "type": "candidate_window",
            "id": w["candidate_window_id"],
            "ticker": ticker,
            "video_id": w["video_id"],
            "channel_title": w["channel_title"] or "",
            "video_title": (w["video_title"] or "")[:120],
            "evidence_window": (ew)[:300],
            "focused_action_text": (fat)[:200],
            "has_cashtag": str(has_cashtag),
            "has_clear_secure": str(has_clear_secure),
            "has_exchange_syntax": str(has_exchange),
            "has_stock_context": str(has_stock_context),
            "appears_ordinary_word": str(appears_ordinary),
            "recommended_action": recommendation,
            "accepted_event": str(w.get("accepted_event_flag", 0)),
        })

    for e in events:
        ew = e["evidence_window"] or ""
        evidence_lower = ew.lower()

        has_cashtag = f"${ticker.lower()}" in evidence_lower
        has_clear_secure = "clear secure" in evidence_lower
        has_exchange = any(
            prefix in ew
            for prefix in [f"NYSE: {ticker}", f"NASDAQ: {ticker}"]
        )
        has_stock_context = any(
            phrase in evidence_lower
            for phrase in [
                f"{ticker.lower()} stock", f"{ticker.lower()} shares",
                f"buy {ticker.lower()}", f"sell {ticker.lower()}",
            ]
        )
        appears_ordinary = False
        if ticker in ("YOU",):
            ordinary_phrases = [
                "you should", "you know", "you can", "if you", "when you",
                "what you", "how you", "why you", "that you", "and you",
                "for you", "with you", "to you", "do you", "thank you",
            ]
            appears_ordinary = any(phrase in evidence_lower for phrase in ordinary_phrases)

        if has_cashtag or has_clear_secure or has_exchange or has_stock_context:
            recommendation = "keep"
        elif appears_ordinary:
            recommendation = "exclude_false_positive"
        else:
            recommendation = "manual_review"

        audit_rows.append({
            "type": "recommendation_event",
            "id": e["transcript_event_id"],
            "ticker": ticker,
            "video_id": e["video_id"],
            "channel_title": e["channel_title"] or "",
            "video_title": (e["video_title"] or "")[:120],
            "evidence_window": (ew)[:300],
            "focused_action_text": "",
            "has_cashtag": str(has_cashtag),
            "has_clear_secure": str(has_clear_secure),
            "has_exchange_syntax": str(has_exchange),
            "has_stock_context": str(has_stock_context),
            "appears_ordinary_word": str(appears_ordinary),
            "recommended_action": recommendation,
            "accepted_event": "1",
        })

    audit_csv_path = _audit_dir() / f"ticker_false_positive_audit_{ticker.lower()}.csv"
    summary_txt_path = _report_ready_dir() / "ticker_false_positive_audit_summary.txt"

    with audit_csv_path.open("w", newline="", encoding="utf-8") as f:
        if audit_rows:
            writer = csv.DictWriter(f, fieldnames=list(audit_rows[0].keys()))
            writer.writeheader()
            writer.writerows(audit_rows)
        else:
            f.write("type,id,ticker,video_id,channel_title,recommended_action\n")

    windows_count = len(windows)
    events_count = len(events)
    exclude_count = sum(1 for r in audit_rows if r["recommended_action"] == "exclude_false_positive")
    keep_count = sum(1 for r in audit_rows if r["recommended_action"] == "keep")
    review_count = sum(1 for r in audit_rows if r["recommended_action"] == "manual_review")

    summary = (
        f"Ticker False Positive Audit — {ticker}\n"
        f"{'=' * 50}\n"
        f"Candidate windows with ticker {ticker}: {windows_count}\n"
        f"Accepted events with ticker {ticker}: {events_count}\n"
        f"Total audit rows: {len(audit_rows)}\n"
        f"  Keep (has cashtag/exchange/alias/stock context): {keep_count}\n"
        f"  Exclude as false positive (ordinary word): {exclude_count}\n"
        f"  Manual review needed: {review_count}\n"
    )

    with summary_txt_path.open("w", encoding="utf-8") as f:
        f.write(summary)

    return {
        "audit_csv": audit_csv_path,
        "summary_txt": summary_txt_path,
    }


class QuarantineResult:
    def __init__(self, dry_run: bool, windows_excluded: int, events_excluded: int):
        self.dry_run = dry_run
        self.windows_excluded = windows_excluded
        self.events_excluded = events_excluded


def quarantine_false_positive_tickers(
    ticker: str = "YOU",
    dry_run: bool = True,
    reason: str = "common_word_false_positive",
) -> QuarantineResult:
    init_db()
    ensure_data_dirs()
    ticker = ticker.upper()

    with connect() as conn:
        _ensure_exclusion_table(conn)

        windows = conn.execute(
            """
            SELECT candidate_window_id, video_id, evidence_window, focused_action_text
            FROM transcript_candidate_windows
            WHERE ticker = ?
            """,
            (ticker,),
        ).fetchall()

        events = conn.execute(
            """
            SELECT transcript_event_id, video_id, evidence_window
            FROM transcript_recommendation_events
            WHERE ticker = ?
            """,
            (ticker,),
        ).fetchall()

        windows_to_exclude = []
        for w in windows:
            ew = (w["evidence_window"] or "") + " " + (w["focused_action_text"] or "")
            ew_lower = ew.lower()
            if _is_ordinary_word_evidence(ew_lower, ticker):
                windows_to_exclude.append(w)

        events_to_exclude = []
        for e in events:
            ew = (e["evidence_window"] or "").lower()
            if _is_ordinary_word_evidence(ew, ticker):
                events_to_exclude.append(e)

        if not dry_run:
            for w in windows_to_exclude:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO transcript_event_exclusions
                    (event_id, window_id, ticker, reason, evidence_excerpt, action)
                    VALUES (?, ?, ?, ?, ?, 'exclude')
                    """,
                    (
                        None,
                        w["candidate_window_id"],
                        ticker,
                        reason,
                        (w["evidence_window"] or "")[:500],
                    ),
                )
            for e in events_to_exclude:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO transcript_event_exclusions
                    (event_id, window_id, ticker, reason, evidence_excerpt, action)
                    VALUES (?, ?, ?, ?, ?, 'exclude')
                    """,
                    (
                        e["transcript_event_id"],
                        None,
                        ticker,
                        reason,
                        (e["evidence_window"] or "")[:500],
                    ),
                )
            conn.commit()

    return QuarantineResult(
        dry_run=dry_run,
        windows_excluded=len(windows_to_exclude),
        events_excluded=len(events_to_exclude),
    )


def _is_ordinary_word_evidence(evidence_lower: str, ticker: str) -> bool:
    if f"${ticker.lower()}" in evidence_lower:
        return False
    if "clear secure" in evidence_lower:
        return False
    if any(prefix in evidence_lower for prefix in [f"nyse: {ticker.lower()}", f"nasdaq: {ticker.lower()}"]):
        return False
    for phrase in [
        f"{ticker.lower()} stock", f"{ticker.lower()} shares",
        f"{ticker.lower()} earnings", f"{ticker.lower()} revenue",
        f"buy {ticker.lower()}", f"sell {ticker.lower()}",
        f"long {ticker.lower()}", f"short {ticker.lower()}",
    ]:
        if phrase in evidence_lower:
            return False
    ordinary = [
        f"{ticker.lower()} should", f"{ticker.lower()} know", f"{ticker.lower()} can",
        f"if {ticker.lower()}", f"when {ticker.lower()}", f"what {ticker.lower()}",
        f"how {ticker.lower()}", f"why {ticker.lower()}", f"that {ticker.lower()}",
        f"and {ticker.lower()}", f"for {ticker.lower()}", f"with {ticker.lower()}",
        f"to {ticker.lower()}", f"of {ticker.lower()}", f"do {ticker.lower()}",
        f"thank {ticker.lower()}", f"love {ticker.lower()}", f"are {ticker.lower()}",
    ]
    if any(phrase in evidence_lower for phrase in ordinary):
        return True
    return False


def get_excluded_event_ids(conn) -> set[int]:
    rows = conn.execute(
        "SELECT event_id FROM transcript_event_exclusions WHERE event_id IS NOT NULL"
    ).fetchall()
    return {r["event_id"] for r in rows}


def get_excluded_window_ids(conn) -> set[int]:
    rows = conn.execute(
        "SELECT window_id FROM transcript_event_exclusions WHERE window_id IS NOT NULL"
    ).fetchall()
    return {r["window_id"] for r in rows}


def count_high_risk_only_targets(conn) -> int:
    from .ticker_extract import HIGH_RISK_TICKERS

    placeholders = ",".join("?" * len(HIGH_RISK_TICKERS))
    row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT tm.source_id) as cnt
        FROM ticker_mentions tm
        JOIN raw_youtube_videos rv ON rv.video_id = tm.source_id
        WHERE tm.ticker IN ({placeholders})
          AND tm.platform = 'youtube'
          AND COALESCE(rv.excluded_flag, 0) = 0
          AND rv.video_id NOT IN (
            SELECT video_id FROM youtube_transcripts WHERE status = 'available'
          )
        """,
        tuple(HIGH_RISK_TICKERS),
    ).fetchone()
    return row["cnt"] or 0
