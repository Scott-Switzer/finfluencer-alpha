from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package" / "locked_sample"
FINAL_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package"
RG_DIR = REPO_ROOT / "data" / "exports" / "research_grade_analysis"

EVENT_MANIFEST = LOCK_DIR / "01_locked_event_manifest.csv"
TRANSCRIPT_MANIFEST = LOCK_DIR / "02_locked_transcript_manifest.csv"
RECONCILIATION = LOCK_DIR / "03_locked_sample_reconciliation.csv"
TIMELINE = RG_DIR / "05_event_timeline_dataset.csv"
SEC_FLAGS = FINAL_DIR / "06_sec_news_overlap_flags.csv"
FREE_NEWS_FLAGS = FINAL_DIR / "free_news" / "02_free_news_event_flags.csv"
SAMPLE_TABLE = FINAL_DIR / "01_sample_construction_table.csv"
EVENT_STUDY_TABLE = FINAL_DIR / "02_event_study_robustness_table.csv"
COUNT_AUDIT = FINAL_DIR / "40_runpod_count_reconciliation_audit.csv"

REQUIRED_EVENT_COLUMNS = {
    "locked_sample_version",
    "event_id",
    "source_video_id",
    "video_id",
    "transcript_id",
    "creator",
    "channel_id",
    "ticker",
    "company_name",
    "recommendation_type",
    "event_date",
    "effective_trading_event_date",
    "transcript_source",
    "extraction_source_file",
    "event_return_source_file",
    "in_final_event_study",
    "in_sec_clean_analysis",
    "in_low_lookahead_analysis",
    "in_duplicate_collapsed_analysis",
    "in_factor_analysis",
    "in_free_news_scaffold",
    "notes",
}

REQUIRED_TRANSCRIPT_COLUMNS = {
    "locked_sample_version",
    "video_id",
    "transcript_id",
    "creator",
    "channel_id",
    "transcript_source",
    "language",
    "transcript_status",
    "text_length_bucket",
    "included_in_locked_sample",
    "exclusion_reason",
    "source_file_or_table",
    "notes",
}

REQUIRED_RECON_COLUMNS = {
    "metric",
    "count",
    "source",
    "filter_definition",
    "reproducibility_status",
    "notes",
}

FORBIDDEN_TRANSCRIPT_COLUMNS = {"full_text", "raw_json", "segments", "transcript_text", "text"}
FORBIDDEN_NEWS_COLUMNS = {"article_body", "body", "content", "raw_json", "full_text", "text"}


def load_csv(path: Path, failures: list[str]) -> pd.DataFrame:
    if not path.exists():
        failures.append(f"missing file: {path.relative_to(REPO_ROOT)}")
        return pd.DataFrame()
    return pd.read_csv(path)


def require_columns(name: str, df: pd.DataFrame, required: set[str], failures: list[str]) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        failures.append(f"{name} missing required columns: {missing}")


def metric_count(recon: pd.DataFrame, metric: str) -> int | None:
    rows = recon.loc[recon["metric"].eq(metric), "count"]
    if rows.empty:
        return None
    return int(rows.iloc[0])


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    events = load_csv(EVENT_MANIFEST, failures)
    transcripts = load_csv(TRANSCRIPT_MANIFEST, failures)
    recon = load_csv(RECONCILIATION, failures)
    timeline = load_csv(TIMELINE, failures)
    sec = load_csv(SEC_FLAGS, failures)
    free = load_csv(FREE_NEWS_FLAGS, failures)
    sample = load_csv(SAMPLE_TABLE, failures)
    event_study = load_csv(EVENT_STUDY_TABLE, failures)
    count_audit = load_csv(COUNT_AUDIT, failures)

    if failures:
        print("LOCKED SAMPLE VALIDATION: FAIL")
        for item in failures:
            print(f"FAIL: {item}")
        return 1

    require_columns("event manifest", events, REQUIRED_EVENT_COLUMNS, failures)
    require_columns("transcript manifest", transcripts, REQUIRED_TRANSCRIPT_COLUMNS, failures)
    require_columns("reconciliation", recon, REQUIRED_RECON_COLUMNS, failures)

    forbidden_transcript = sorted(FORBIDDEN_TRANSCRIPT_COLUMNS & set(transcripts.columns))
    if forbidden_transcript:
        failures.append(f"transcript manifest exposes forbidden columns: {forbidden_transcript}")

    forbidden_news = sorted(FORBIDDEN_NEWS_COLUMNS & set(free.columns))
    if forbidden_news:
        failures.append(f"free-news output exposes raw article/body columns: {forbidden_news}")

    if events["event_id"].duplicated().any():
        dupes = events.loc[events["event_id"].duplicated(), "event_id"].head(10).tolist()
        failures.append(f"duplicate event_id values in event manifest: {dupes}")

    event_ids = set(events["event_id"].astype(int))
    timeline_ids = set(timeline["event_id"].astype(int))
    if event_ids != timeline_ids:
        failures.append(
            "event manifest event_id set does not match research_grade_analysis/05_event_timeline_dataset.csv"
        )

    sec_ids = set(sec["event_id"].astype(int))
    if event_ids != sec_ids:
        failures.append("event manifest event_id set does not match SEC overlap flags")

    free_ids = set(free["event_id"].astype(int))
    if event_ids != free_ids:
        failures.append("event manifest event_id set does not match free-news scaffold flags")

    if len(events) != 1554:
        failures.append(f"expected 1554 locked events, found {len(events)}")

    if metric_count(recon, "locked_final_accepted_events") != len(events):
        failures.append("reconciliation locked_final_accepted_events does not match event manifest rows")

    sample_events = sample.loc[sample["Metric"].eq("Accepted recommendation events"), "Count"]
    if sample_events.empty or int(sample_events.iloc[0]) != len(events):
        failures.append("sample construction accepted-event count does not match event manifest")

    sec_clean_manifest = int(events["in_sec_clean_analysis"].astype(str).str.lower().eq("true").sum())
    sec_clean_flags = int((~sec["sec_confounded_event_flag"].astype(bool)).sum())
    if sec_clean_manifest != sec_clean_flags:
        failures.append("SEC-clean event count mismatch between manifest and SEC flags")

    free_scaffold_count = metric_count(recon, "free_news_scaffold_events")
    if free_scaffold_count != len(free):
        failures.append("free_news_scaffold_events count does not match free-news flag rows")

    real_gdelt = metric_count(recon, "free_news_real_gdelt_events")
    if real_gdelt != 0:
        failures.append("free_news_real_gdelt_events is nonzero; update paper language and validation expectations")

    simulated = metric_count(recon, "free_news_simulated_events")
    if simulated != len(free):
        failures.append("free_news_simulated_events does not match free-news flag rows")

    if metric_count(recon, "locked_final_transcripts") == 8994:
        status = recon.loc[recon["metric"].eq("locked_final_transcripts"), "reproducibility_status"].iloc[0]
        if status != "historical_artifact_not_reconstructible":
            failures.append("8994 transcript count must remain marked as historical_artifact_not_reconstructible")
        warnings.append("8994 transcript count is historical only; no committed transcript-id manifest was found")
    else:
        failures.append("locked_final_transcripts metric missing or not equal to historical count 8994")

    transcript_cols = set(transcripts.columns)
    if "text_length_bucket" not in transcript_cols:
        failures.append("transcript manifest must use text_length_bucket and must not export transcript text")

    if len(transcripts) != metric_count(recon, "live_db_transcript_rows"):
        warnings.append("transcript manifest row count differs from live_db_transcript_rows")

    canonical_5d = event_study.loc[
        event_study["specification"].eq("Canonical baseline") & event_study["horizon"].eq("AR_0_5")
    ]
    if canonical_5d.empty:
        failures.append("canonical AR_0_5 row missing from event-study robustness table")
    else:
        n = int(canonical_5d["n"].iloc[0])
        if n != metric_count(recon, "final_event_study_events_with_returns"):
            failures.append("final_event_study_events_with_returns does not match canonical AR_0_5 n")
        if n >= len(events):
            warnings.append("canonical AR_0_5 n unexpectedly covers all locked events; check return coverage assumptions")

    if "event_id" not in event_study.columns:
        warnings.append("canonical event-study table is aggregate only; event-level canonical return membership file is not committed")

    audit_accepted = count_audit.loc[count_audit["metric"].eq("accepted_recommendation_events"), "count"]
    if audit_accepted.empty or int(audit_accepted.iloc[0]) != len(events):
        failures.append("40_runpod_count_reconciliation_audit accepted count does not match event manifest")

    if failures:
        print("LOCKED SAMPLE VALIDATION: FAIL")
        for item in failures:
            print(f"FAIL: {item}")
        for item in warnings:
            print(f"WARN: {item}")
        return 1

    verdict = "PARTIAL" if warnings else "PASS"
    print(f"LOCKED SAMPLE VALIDATION: {verdict}")
    print(f"locked_event_rows={len(events)}")
    print(f"transcript_manifest_rows={len(transcripts)}")
    print(f"sec_clean_events={sec_clean_flags}")
    print(f"free_news_rows={len(free)}")
    print(f"free_news_real_gdelt_events={real_gdelt}")
    print(f"free_news_simulated_events={simulated}")
    for item in warnings:
        print(f"WARN: {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
