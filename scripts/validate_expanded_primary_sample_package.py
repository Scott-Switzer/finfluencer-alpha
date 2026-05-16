from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "finfluencer_alpha.db"
V2_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
V2_LOCK_DIR = V2_DIR / "locked_sample_v2"

EVENT_MANIFEST = V2_LOCK_DIR / "02_v2_event_manifest.csv"
TRANSCRIPT_MANIFEST = V2_LOCK_DIR / "01_v2_transcript_manifest.csv"
SAMPLE_CONSTRUCTION = V2_LOCK_DIR / "04_v2_sample_construction.csv"
RESULTS = V2_DIR / "02_v2_event_study_robustness_table.csv"
HIERARCHY = V2_DIR / "13_v2_result_hierarchy.csv"
ADOPTION = V2_DIR / "18_v2_adoption_recommendation.md"

REQUIRED_FILES = [
    V2_DIR / "00_v2_build_plan.md",
    V2_DIR / "01_live_db_schema_audit.md",
    TRANSCRIPT_MANIFEST,
    EVENT_MANIFEST,
    V2_LOCK_DIR / "03_v1_vs_v2_event_bridge.csv",
    SAMPLE_CONSTRUCTION,
    V2_LOCK_DIR / "04_v2_sample_construction.md",
    V2_LOCK_DIR / "README.md",
    V2_DIR / "01_v2_sample_construction_table.csv",
    V2_DIR / "01_v2_sample_construction_table.md",
    RESULTS,
    V2_DIR / "02_v2_event_study_robustness_table.md",
    V2_DIR / "03_v2_timing_lookahead_table.csv",
    V2_DIR / "03_v2_timing_lookahead_table.md",
    V2_DIR / "04_v2_duplicate_cluster_analysis.csv",
    V2_DIR / "04_v2_duplicate_cluster_analysis.md",
    V2_DIR / "05_v2_sec_clean_analysis.csv",
    V2_DIR / "05_v2_sec_clean_analysis.md",
    V2_DIR / "06_v2_top5_vs_non_top_analysis.csv",
    V2_DIR / "06_v2_top5_vs_non_top_analysis.md",
    V2_DIR / "07_v2_buy_vs_sell_analysis.csv",
    V2_DIR / "07_v2_buy_vs_sell_analysis.md",
    V2_DIR / "08_v2_creator_heterogeneity.csv",
    V2_DIR / "08_v2_creator_heterogeneity.md",
    V2_DIR / "09_v2_ticker_heterogeneity.csv",
    V2_DIR / "09_v2_ticker_heterogeneity.md",
    V2_DIR / "10_v2_factor_adjusted_alpha_table.csv",
    V2_DIR / "10_v2_factor_adjusted_alpha_table.md",
    V2_DIR / "11_v2_calendar_time_portfolio_results.csv",
    V2_DIR / "11_v2_calendar_time_portfolio_results.md",
    V2_DIR / "12_v1_vs_v2_comparison_table.csv",
    V2_DIR / "12_v1_vs_v2_comparison_table.md",
    HIERARCHY,
    V2_DIR / "13_v2_result_hierarchy.md",
    V2_DIR / "14_v2_final_results_section_draft.md",
    V2_DIR / "15_v2_final_limitations_section_draft.md",
    V2_DIR / "16_v2_final_conclusion_draft.md",
    V2_DIR / "17_v2_professor_defense_memo.md",
    ADOPTION,
    V2_DIR / "figures_data" / "v2_event_study_forest_plot.csv",
    V2_DIR / "figures_data" / "v2_top5_vs_non_top.csv",
    V2_DIR / "figures_data" / "v2_sample_funnel.csv",
    V2_DIR / "figures_data" / "v1_vs_v2_headline_comparison.csv",
]

FORBIDDEN_TRANSCRIPT_COLUMNS = {
    "full_text",
    "raw_json",
    "segments",
    "transcript_text",
    "text",
    "evidence_window",
}
FORBIDDEN_NEWS_COLUMNS = {"article_body", "body", "content", "raw_json", "full_text", "text"}
VALID_RECOMMENDATION_TYPES = {"buy", "sell"}


def db_count(sql: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        return int(con.execute(sql).fetchone()[0])


def git_output(args: list[str]) -> str:
    try:
        return subprocess.check_output(args, cwd=REPO_ROOT, text=True).strip()
    except subprocess.CalledProcessError:
        return ""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_csv(path: Path, failures: list[str]) -> pd.DataFrame:
    if not path.exists():
        failures.append(f"missing file: {path.relative_to(REPO_ROOT)}")
        return pd.DataFrame()
    return pd.read_csv(path)


def metric_count(sample: pd.DataFrame, metric: str) -> int | None:
    rows = sample.loc[sample["metric"].eq(metric), "count"]
    if rows.empty:
        return None
    return int(rows.iloc[0])


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    for path in REQUIRED_FILES:
        if not path.exists():
            failures.append(f"missing required v2 output: {path.relative_to(REPO_ROOT)}")

    if failures:
        print("EXPANDED PRIMARY SAMPLE VALIDATION: FAIL")
        for item in failures:
            print(f"FAIL: {item}")
        return 1

    transcripts = load_csv(TRANSCRIPT_MANIFEST, failures)
    events = load_csv(EVENT_MANIFEST, failures)
    sample = load_csv(SAMPLE_CONSTRUCTION, failures)
    results = load_csv(RESULTS, failures)
    hierarchy = load_csv(HIERARCHY, failures)

    forbidden_transcript = sorted(FORBIDDEN_TRANSCRIPT_COLUMNS & set(transcripts.columns))
    if forbidden_transcript:
        failures.append(f"transcript manifest exposes forbidden columns: {forbidden_transcript}")

    for csv_path in V2_DIR.rglob("*.csv"):
        df = pd.read_csv(csv_path, nrows=1)
        forbidden = sorted(FORBIDDEN_NEWS_COLUMNS & set(df.columns))
        if forbidden:
            failures.append(
                f"{csv_path.relative_to(REPO_ROOT)} exposes forbidden raw text/body columns: {forbidden}"
            )

    db_transcripts = db_count("SELECT COUNT(*) FROM youtube_transcripts")
    db_events = db_count("SELECT COUNT(*) FROM transcript_recommendation_events")
    if len(transcripts) != db_transcripts:
        failures.append(f"transcript manifest rows {len(transcripts)} != live DB {db_transcripts}")
    if len(events) != db_events:
        failures.append(f"event manifest rows {len(events)} != live DB {db_events}")

    if events["event_id"].duplicated().any():
        failures.append("duplicate event_id values in v2 event manifest")

    if not pd.to_datetime(events["event_date"], errors="coerce").notna().all():
        failures.append("one or more v2 event dates failed to parse")

    tickers_ok = events["ticker"].astype(str).str.match(r"^[A-Z]{1,5}$").all()
    if not tickers_ok:
        failures.append("one or more ticker values are outside the expected uppercase symbol shape")

    rec_types = set(events["recommendation_type"].dropna().astype(str))
    invalid = sorted(rec_types - VALID_RECOMMENDATION_TYPES)
    if invalid:
        failures.append(f"invalid recommendation_type values: {invalid}")

    if metric_count(sample, "live_transcript_rows") != db_transcripts:
        failures.append("sample construction live_transcript_rows does not match DB")
    if metric_count(sample, "accepted_recommendation_events") != db_events:
        failures.append("sample construction accepted_recommendation_events does not match DB")

    one_day = metric_count(sample, "return_matched_1d")
    five_day = metric_count(sample, "return_matched_5d")
    if one_day is None or five_day is None:
        failures.append("return coverage metrics missing from sample construction")
    elif five_day / db_events < 0.80:
        failures.append("5D return coverage is below 80% of v2 events")

    bridge = pd.read_csv(V2_LOCK_DIR / "03_v1_vs_v2_event_bridge.csv")
    if int(bridge["in_v2_live_sample"].sum()) != db_events:
        failures.append("v1/v2 bridge does not reconcile v2 event count")
    if int(bridge["in_v1_locked_sample"].sum()) != 1554:
        failures.append("v1/v2 bridge does not preserve the 1,554 v1 event count")

    result_names = set(results["specification"].astype(str))
    required_specs = {
        "v1 locked sample reference",
        "v2 all accepted events",
        "v2 low-lookahead",
        "v2 duplicate-collapsed",
        "v2 top-5 tickers",
        "v2 non-top tickers",
        "v2 buy-only",
        "v2 sell-only",
    }
    missing_specs = sorted(required_specs - result_names)
    if missing_specs:
        failures.append(f"missing result specifications: {missing_specs}")

    all_v2 = results.loc[results["specification"].eq("v2 all accepted events")]
    hierarchy_all = hierarchy.loc[hierarchy["specification"].eq("v2 all accepted events")]
    if all_v2.empty or hierarchy_all.empty:
        failures.append("v2 all accepted events missing from results or hierarchy")
    elif int(all_v2["n_5d"].iloc[0]) != int(hierarchy_all["n_5d"].iloc[0]):
        failures.append("result hierarchy n_5d does not match robustness table")

    all_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in V2_DIR.rglob("*.md")
        if path.is_file()
    )
    lowered = all_text.lower()
    if "free-news robustness passed" in lowered or "news-confound controlled" in lowered:
        failures.append("v2 markdown contains overstated free-news/news-confound language")
    if "tradable alpha" in lowered and "not" not in lowered:
        warnings.append("review tradable-alpha wording manually")
    for stale in ["8,994", "8994", "1,554", "1554"]:
        if stale in all_text:
            nearby_ok = any(
                marker in lowered
                for marker in ["v1", "historical", "benchmark", "locked artifact"]
            )
            if not nearby_ok:
                failures.append(f"stale count {stale} appears without v1/historical labeling")

    results_text = read_text(V2_DIR / "14_v2_final_results_section_draft.md")
    if str(int(all_v2["n_5d"].iloc[0])) not in results_text:
        failures.append("final results draft does not mention v2 headline n_5d")

    staged = git_output(["git", "diff", "--cached", "--name-only"]).splitlines()
    unsafe_suffixes = (".db", ".sqlite", ".log", ".bundle", ".patch")
    for name in staged:
        lowered_name = name.lower()
        if ".env" in lowered_name or "env" in Path(name).name.lower():
            failures.append(f"env-like file staged: {name}")
        if lowered_name.endswith(unsafe_suffixes):
            failures.append(f"unsafe raw/log/bundle file staged: {name}")

    if metric_count(sample, "sec_clean_events") is not None:
        sec_total = metric_count(sample, "sec_clean_events") + metric_count(sample, "sec_confounded_events")
        if sec_total < db_events:
            warnings.append("SEC-clean analysis is partial because v2-unique events lack SEC flags")

    if metric_count(sample, "factor_matched_events") == 0:
        warnings.append("factor-adjusted alpha is not computed because factor inputs are absent")

    if failures:
        print("EXPANDED PRIMARY SAMPLE VALIDATION: FAIL")
        for item in failures:
            print(f"FAIL: {item}")
        for item in warnings:
            print(f"WARN: {item}")
        return 1

    verdict = "PARTIAL" if warnings else "PASS"
    print(f"EXPANDED PRIMARY SAMPLE VALIDATION: {verdict}")
    print(f"v2_transcript_rows={len(transcripts)}")
    print(f"v2_event_rows={len(events)}")
    print(f"v2_return_matched_1d={one_day}")
    print(f"v2_return_matched_5d={five_day}")
    for item in warnings:
        print(f"WARN: {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
