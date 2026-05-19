"""Targeted news/confound audit for largest v2 event-study return moves.

This is a diagnostic robustness layer. It uses existing derived/cached panels
only and does not rebuild the full public-news sample or store raw articles.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "news_extreme_event_audit"
RETURNS_PATH = utils.OUT_DIR / "long_horizon" / "01_v2_long_horizon_event_returns.csv"
EVENT_MANIFEST_PATH = utils.OUT_DIR / "locked_sample_v2" / "02_v2_event_manifest.csv"
NEWS_CONFOUND_PATH = utils.OUT_DIR / "news_confound_master" / "news_confound_event_panel.csv"
SEC_FLAGS_PATH = utils.OUT_DIR / "sec_earnings_confounds" / "01_sec_event_flags_expanded.csv"
FNSPID_PATH = (
    utils.OUT_DIR / "news_confound_master" / "fnspid" / "fnspid_derived_event_panel.csv"
)
FNSPID_WINDOW_PATH = (
    utils.OUT_DIR / "news_confound_master" / "fnspid" / "fnspid_event_window_hits.csv"
)
AV_EXPANDED_PATH = (
    utils.OUT_DIR / "news_alpha_vantage_expanded" / "av_expanded_event_news_panel.csv"
)
AV_LEGACY_FLAGS_PATH = utils.OUT_DIR / "news_alpha_vantage" / "04_av_event_window_flags.csv"
AV_LEGACY_META_PATH = utils.OUT_DIR / "news_alpha_vantage" / "03_av_compact_article_metadata.csv"
GDELT_FLAGS_PATH = utils.OUT_DIR / "news_gdelt_retry" / "02_gdelt_probe_flags.csv"
REAL_GDELT_PROBE_PATH = utils.OUT_DIR / "news" / "02_real_news_probe_event_flags.csv"
FALLBACK_NEWS_PATH = utils.OUT_DIR / "news_fallback" / "02_fallback_news_probe_flags.csv"
MARKET_PATH = utils.OUT_DIR / "market_implied_confounds" / "market_implied_confound_panel.csv"
BLOOMBERG_PATH = (
    utils.OUT_DIR / "bloomberg_validation" / "bloomberg_event_mechanism_features.csv"
)

TOP_N_PER_BUCKET = 25
CAP_AUDITED_EVENTS = 125
BLOOMBERG_NEWS_HEAT_HIGH_MIN = 3.0
BLOOMBERG_ABS_NEWS_SENTIMENT_HIGH_MIN = 0.25
HIGH_ANALYST_COVERAGE_MIN = 75.0
MARKET_ATTENTION_Z_MIN = 1.5


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def one_row_per_event(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "event_id" not in frame.columns:
        return frame
    return frame.sort_values("event_id").drop_duplicates("event_id", keep="first")


def clean_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def boolish(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if value in (None, ""):
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value) and not pd.isna(value)
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def compact_join(values: list[Any], sep: str = "; ") -> str:
    clean: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text.lower() == "nan":
            continue
        if text not in clean:
            clean.append(text)
    return sep.join(clean)


def pct_text(value: Any) -> str:
    out = clean_float(value)
    if out is None:
        return ""
    return f"{100.0 * out:.2f}%"


def select_extreme_events(returns: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = returns[
        (returns["window_type"].astype(str) == "forward")
        & (returns["horizon"].astype(str).isin(["1D", "5D"]))
        & (returns["status"].astype(str) == "computed")
    ].copy()
    work["spy_bhar"] = pd.to_numeric(work["spy_bhar"], errors="coerce")
    work = work.dropna(subset=["event_id", "spy_bhar"])

    selected_rows: list[pd.DataFrame] = []
    bucket_specs = [
        ("positive_1d", "1D", False),
        ("negative_1d", "1D", True),
        ("positive_5d", "5D", False),
        ("negative_5d", "5D", True),
    ]
    for bucket, horizon, ascending in bucket_specs:
        group = work[work["horizon"] == horizon].sort_values("spy_bhar", ascending=ascending)
        top = group.head(TOP_N_PER_BUCKET).copy()
        top["selection_bucket"] = bucket
        top["selection_rank"] = range(1, len(top) + 1)
        selected_rows.append(top)

    selections = pd.concat(selected_rows, ignore_index=True)
    selected_ids = selections["event_id"].drop_duplicates().head(CAP_AUDITED_EVENTS)
    selections = selections[selections["event_id"].isin(selected_ids)].copy()
    membership = (
        selections.groupby("event_id")
        .agg(
            selection_buckets=("selection_bucket", lambda s: compact_join(list(s))),
            selection_bucket_count=("selection_bucket", "nunique"),
            strongest_selection_abs_ar=("spy_bhar", lambda s: float(s.abs().max())),
        )
        .reset_index()
    )
    for bucket, _, _ in bucket_specs:
        ids = set(selections.loc[selections["selection_bucket"] == bucket, "event_id"].astype(int))
        membership[bucket] = membership["event_id"].astype(int).isin(ids)
    return membership, selections


def return_wide(returns: pd.DataFrame) -> pd.DataFrame:
    base = returns[
        (returns["window_type"].astype(str) == "forward")
        & (returns["horizon"].astype(str).isin(["1D", "5D", "21D"]))
    ].copy()
    base["spy_bhar"] = pd.to_numeric(base["spy_bhar"], errors="coerce")
    base["raw_return"] = pd.to_numeric(base["raw_return"], errors="coerce")
    base["benchmark_return"] = pd.to_numeric(base["benchmark_return"], errors="coerce")
    out = pd.DataFrame({"event_id": sorted(base["event_id"].dropna().astype(int).unique())})
    for horizon in ["1D", "5D", "21D"]:
        sub = base[base["horizon"] == horizon].sort_values("event_id").drop_duplicates("event_id")
        rename = {
            "spy_bhar": f"ar_{horizon.lower()}",
            "raw_return": f"raw_return_{horizon.lower()}",
            "benchmark_return": f"benchmark_return_{horizon.lower()}",
            "status": f"return_status_{horizon.lower()}",
            "start_trading_date": f"start_trading_date_{horizon.lower()}",
            "end_trading_date": f"end_trading_date_{horizon.lower()}",
        }
        cols = ["event_id", *[col for col in rename if col in sub.columns]]
        out = out.merge(sub[cols].rename(columns=rename), on="event_id", how="left")
    return out


def merge_source(
    audit: pd.DataFrame,
    source: pd.DataFrame,
    columns: list[str],
    *,
    rename: dict[str, str] | None = None,
) -> pd.DataFrame:
    if source.empty or "event_id" not in source.columns:
        return audit
    rename = rename or {}
    keep = ["event_id", *[col for col in columns if col in source.columns]]
    incoming = one_row_per_event(source[keep]).rename(columns=rename)
    overlap = [col for col in incoming.columns if col != "event_id" and col in audit.columns]
    incoming = incoming.drop(columns=overlap)
    return audit.merge(incoming, on="event_id", how="left")


def parse_av_time(value: Any) -> pd.Timestamp | pd.NaT:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return pd.NaT
    return pd.to_datetime(text[:8], format="%Y%m%d", errors="coerce")


def build_av_metadata_summaries(events: pd.DataFrame) -> pd.DataFrame:
    if not AV_LEGACY_META_PATH.exists():
        return pd.DataFrame(columns=["event_id"])
    meta = pd.read_csv(AV_LEGACY_META_PATH)
    needed = {"ticker", "time_published", "title_truncated", "source_domain"}
    if meta.empty or not needed.issubset(meta.columns):
        return pd.DataFrame(columns=["event_id"])
    meta = meta.copy()
    meta["published_date"] = meta["time_published"].map(parse_av_time)
    meta = meta.dropna(subset=["published_date"])
    by_ticker = {str(ticker): group for ticker, group in meta.groupby(meta["ticker"].astype(str))}
    rows: list[dict[str, Any]] = []
    for _, event in events.iterrows():
        event_date = pd.to_datetime(event.get("event_date"), errors="coerce")
        group = by_ticker.get(str(event.get("ticker")))
        if group is None or pd.isna(event_date):
            rows.append(
                {
                    "event_id": event.get("event_id"),
                    "av_cached_metadata_pm7_count": 0,
                    "av_cached_metadata_top_domains": "",
                    "av_cached_metadata_top_titles": "",
                }
            )
            continue
        window = group[(group["published_date"] - event_date).abs().dt.days <= 7].copy()
        domains = window["source_domain"].dropna().astype(str).head(5).tolist()
        titles = window["title_truncated"].dropna().astype(str).head(3).tolist()
        rows.append(
            {
                "event_id": event.get("event_id"),
                "av_cached_metadata_pm7_count": int(len(window)),
                "av_cached_metadata_top_domains": compact_join(domains),
                "av_cached_metadata_top_titles": compact_join(titles, " || "),
            }
        )
    return pd.DataFrame(rows)


def build_audit_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    returns = read_csv(RETURNS_PATH)
    if returns.empty:
        raise FileNotFoundError(f"Missing return panel: {RETURNS_PATH}")
    membership, selections = select_extreme_events(returns)
    manifest = read_csv(EVENT_MANIFEST_PATH)
    if manifest.empty:
        raise FileNotFoundError(f"Missing event manifest: {EVENT_MANIFEST_PATH}")

    audit = membership.merge(manifest, on="event_id", how="left")
    audit["top5_flag"] = audit["ticker"].astype(str).str.upper().isin(utils.TOP5)
    audit = audit.merge(return_wide(returns), on="event_id", how="left")

    news_cols = [
        "news_clean_status_final",
        "news_clean_status",
        "best_available_news_status",
        "coverage_sensitivity_bucket",
        "official_news_hit",
        "sec_filing_hit",
        "earnings_hit",
        "press_release_hit",
        "any_media_news_hit",
        "market_implied_confounded",
        "provider_success_count_total",
        "provider_success_count_external",
        "provider_hit_count_external",
        "provider_unknown_count",
        "provider_failure_count",
        "provider_quota_limited_count",
        "provider_permission_limited_count",
        "provider_missing_key_count",
        "news_coverage_quality_score",
        "multi_provider_checked_no_hit",
        "multi_source_clean",
        "news_confounded_reason_final",
        "news_confounded_reason",
        "news_window_pre_7d_count",
        "news_window_post_7d_count",
        "alpha_vantage_news_success",
        "alpha_vantage_news_hit",
        "alpha_vantage_news_material_hit",
        "alpha_vantage_news_query_status",
        "gdelt_news_success",
        "gdelt_news_hit",
        "gdelt_news_material_hit",
        "gdelt_news_query_status",
        "fnspid_news_success",
        "fnspid_news_hit",
        "fnspid_news_material_hit",
        "fnspid_news_query_status",
        "fnspid_news_pm7_count",
        "fnspid_hit_sources",
    ]
    audit = merge_source(audit, read_csv(NEWS_CONFOUND_PATH), news_cols)

    sec_cols = [
        "filing_count_pm1",
        "filing_count_pm3",
        "filing_count_pm5",
        "eight_k_pm5_flag",
        "ten_q_or_k_pm5_flag",
        "offering_registration_pm5_flag",
        "ownership_or_insider_pm5_flag",
        "earnings_proxy_flag",
        "sec_material_event_confounded_flag",
        "sec_routine_filing_flag",
        "sec_unknown_flag",
        "sec_clean_expanded_flag",
        "reason_codes",
    ]
    audit = merge_source(audit, read_csv(SEC_FLAGS_PATH), sec_cols, rename={"reason_codes": "sec_reason_codes"})

    fnspid_cols = [
        "fnspid_coverage_available",
        "fnspid_news_hit",
        "fnspid_news_count_pre_1d",
        "fnspid_news_count_post_1d",
        "fnspid_news_count_pre_3d",
        "fnspid_news_count_post_3d",
        "fnspid_news_count_pre_7d",
        "fnspid_news_count_post_7d",
        "fnspid_first_article_date_near_event",
        "fnspid_last_article_date_near_event",
    ]
    audit = merge_source(audit, read_csv(FNSPID_PATH), fnspid_cols)

    fnspid_window_cols = [
        "fnspid_checked",
        "fnspid_total_hits_window",
        "fnspid_sample_titles_redacted_or_short",
        "fnspid_status",
        "fnspid_error_category",
    ]
    audit = merge_source(audit, read_csv(FNSPID_WINDOW_PATH), fnspid_window_cols)

    av_cols = [
        "av_expanded_query_success",
        "window_pm5_article_count",
        "window_pm5_top_source_domains",
        "window_pm5_earnings_news_flag",
        "window_pm5_analyst_news_flag",
        "window_pm5_product_news_flag",
        "window_pm5_legal_regulatory_news_flag",
        "window_pm5_macro_sector_news_flag",
        "window_pm5_major_news_flag",
        "av_expanded_news_confounded_flag",
        "av_expanded_news_clean_flag",
        "av_expanded_news_unknown_flag",
        "reason_codes",
    ]
    audit = merge_source(
        audit,
        read_csv(AV_EXPANDED_PATH),
        av_cols,
        rename={
            "reason_codes": "av_expanded_reason_codes",
            "window_pm5_article_count": "av_expanded_pm5_article_count",
            "window_pm5_top_source_domains": "av_expanded_pm5_top_source_domains",
        },
    )

    legacy_av_cols = [
        "av_query_success",
        "window_pm5_article_count",
        "window_pm5_top_source_domains",
        "window_pm5_major_news_flag",
        "av_news_confounded_flag",
        "av_news_clean_flag",
        "av_news_unknown_flag",
    ]
    audit = merge_source(
        audit,
        read_csv(AV_LEGACY_FLAGS_PATH),
        legacy_av_cols,
        rename={
            "window_pm5_article_count": "av_legacy_pm5_article_count",
            "window_pm5_top_source_domains": "av_legacy_pm5_top_source_domains",
            "window_pm5_major_news_flag": "av_legacy_pm5_major_news_flag",
        },
    )

    gdelt_cols = [
        "gdelt_query_success",
        "gdelt_article_count",
        "gdelt_major_news_flag",
        "gdelt_news_clean_flag",
        "gdelt_news_confounded_flag",
        "gdelt_news_unknown_flag",
        "query_status",
    ]
    audit = merge_source(
        audit,
        read_csv(GDELT_FLAGS_PATH),
        gdelt_cols,
        rename={"query_status": "gdelt_retry_query_status"},
    )

    market_cols = [
        "prior_return_1d",
        "prior_return_5d",
        "prior_return_21d",
        "prior_volatility_21d",
        "prior_abnormal_volume",
        "prior_abs_ret_1d_z",
        "prior_abs_ret_5d_z",
        "prior_abs_ret_21d_z",
        "prior_vol_z",
        "prior_rvol_z",
        "market_quiet",
        "market_active_pre_event",
        "unknown_news_market_quiet",
        "unknown_news_market_active",
    ]
    audit = merge_source(audit, read_csv(MARKET_PATH), market_cols)

    bloomberg_cols = [
        "bloomberg_daily_asof_date",
        "bloomberg_weekly_asof_date",
        "event_px_last",
        "event_volume",
        "event_mkt_cap",
        "event_dollar_volume",
        "event_news_heat",
        "event_news_sentiment",
        "event_bid_ask_spread_pct",
        "event_volume_avg_30d",
        "event_short_int",
        "event_short_int_ratio",
        "event_eqy_rec_cons",
        "event_tot_analyst_rec",
        "event_best_target_price",
        "event_best_eps",
        "event_best_sales",
        "target_price_premium",
        "analyst_consensus_available",
        "analyst_coverage_count_available",
        "estimates_available",
        "news_proxy_available",
        "liquidity_proxy_available",
        "short_interest_available",
    ]
    audit = merge_source(audit, read_csv(BLOOMBERG_PATH), bloomberg_cols)

    audit = merge_source(
        audit,
        read_csv(FALLBACK_NEWS_PATH),
        ["provider", "query_status", "article_count", "top_domains", "top_titles_truncated", "coverage_status"],
        rename={
            "provider": "fallback_provider",
            "query_status": "fallback_query_status",
            "article_count": "fallback_article_count",
            "top_domains": "fallback_top_domains",
            "top_titles_truncated": "fallback_top_titles_truncated",
            "coverage_status": "fallback_coverage_status",
        },
    )
    audit = merge_source(
        audit,
        read_csv(REAL_GDELT_PROBE_PATH),
        [
            "provider",
            "window",
            "query_mode",
            "article_count",
            "top_domains",
            "top_titles_truncated",
            "query_status",
            "provider_error_class",
            "provider_coverage_status",
        ],
        rename={
            "provider": "real_gdelt_provider",
            "window": "real_gdelt_window",
            "query_mode": "real_gdelt_query_mode",
            "article_count": "real_gdelt_article_count",
            "top_domains": "real_gdelt_top_domains",
            "top_titles_truncated": "real_gdelt_top_titles_truncated",
            "query_status": "real_gdelt_query_status",
            "provider_error_class": "real_gdelt_provider_error_class",
            "provider_coverage_status": "real_gdelt_provider_coverage_status",
        },
    )
    audit = audit.merge(build_av_metadata_summaries(audit), on="event_id", how="left")
    return audit, selections


def official_confounded(row: pd.Series) -> bool:
    official_cols = [
        "official_news_hit",
        "sec_filing_hit",
        "earnings_hit",
        "press_release_hit",
        "eight_k_pm5_flag",
        "ten_q_or_k_pm5_flag",
        "offering_registration_pm5_flag",
        "ownership_or_insider_pm5_flag",
        "earnings_proxy_flag",
        "sec_material_event_confounded_flag",
    ]
    return any(boolish(row.get(col)) for col in official_cols)


def media_confounded(row: pd.Series) -> bool:
    media_cols = [
        "any_media_news_hit",
        "alpha_vantage_news_hit",
        "alpha_vantage_news_material_hit",
        "gdelt_news_hit",
        "gdelt_news_material_hit",
        "fnspid_news_hit",
        "fnspid_news_material_hit",
        "av_expanded_news_confounded_flag",
        "av_news_confounded_flag",
        "gdelt_news_confounded_flag",
        "gdelt_major_news_flag",
        "window_pm5_major_news_flag",
        "av_legacy_pm5_major_news_flag",
    ]
    if any(boolish(row.get(col)) for col in media_cols):
        return True
    return (clean_float(row.get("provider_hit_count_external")) or 0.0) > 0


def bloomberg_news_flow_high(row: pd.Series) -> bool:
    heat = clean_float(row.get("event_news_heat"))
    sentiment = clean_float(row.get("event_news_sentiment"))
    return (
        heat is not None
        and heat >= BLOOMBERG_NEWS_HEAT_HIGH_MIN
        or sentiment is not None
        and abs(sentiment) >= BLOOMBERG_ABS_NEWS_SENTIMENT_HIGH_MIN
    )


def market_attention_high(row: pd.Series) -> bool:
    if boolish(row.get("market_active_pre_event")) or boolish(row.get("market_implied_confounded")):
        return True
    z_cols = ["prior_abs_ret_5d_z", "prior_abs_ret_21d_z", "prior_vol_z", "prior_rvol_z"]
    return any(abs(clean_float(row.get(col)) or 0.0) >= MARKET_ATTENTION_Z_MIN for col in z_cols)


def institutionally_followed(row: pd.Series) -> bool:
    coverage = clean_float(row.get("event_tot_analyst_rec"))
    return boolish(row.get("top5_flag")) or (coverage is not None and coverage >= HIGH_ANALYST_COVERAGE_MIN)


def provider_limited(row: pd.Series) -> bool:
    if boolish(row.get("multi_provider_checked_no_hit")) and (clean_float(row.get("provider_success_count_external")) or 0.0) >= 2:
        return False
    limited_counts = [
        "provider_unknown_count",
        "provider_failure_count",
        "provider_quota_limited_count",
        "provider_permission_limited_count",
        "provider_missing_key_count",
    ]
    if any((clean_float(row.get(col)) or 0.0) > 0 for col in limited_counts):
        return True
    limited_status_terms = ("limited", "failed", "missing", "429", "403", "timeout", "not_checked")
    status_cols = [
        "alpha_vantage_news_query_status",
        "gdelt_news_query_status",
        "gdelt_retry_query_status",
        "fnspid_news_query_status",
        "fallback_query_status",
        "real_gdelt_query_status",
    ]
    for col in status_cols:
        status = str(row.get(col, "")).lower()
        if any(term in status for term in limited_status_terms):
            return True
    return (clean_float(row.get("provider_success_count_external")) or 0.0) < 2


def classify_row(row: pd.Series) -> tuple[str, dict[str, bool]]:
    flags = {
        "official_confounded_flag": official_confounded(row),
        "media_confounded_flag": media_confounded(row),
        "bloomberg_news_flow_high_flag": bloomberg_news_flow_high(row),
        "market_attention_high_flag": market_attention_high(row),
        "institutionally_followed_flag": institutionally_followed(row),
        "provider_limited_flag": provider_limited(row),
    }
    strict_clean = (
        boolish(row.get("multi_source_clean"))
        or (
            boolish(row.get("multi_provider_checked_no_hit"))
            and (clean_float(row.get("provider_success_count_external")) or 0.0) >= 2
        )
    )
    if flags["official_confounded_flag"]:
        label = "official_confounded"
    elif flags["media_confounded_flag"]:
        label = "media_confounded"
    elif flags["bloomberg_news_flow_high_flag"]:
        label = "bloomberg_news_flow_high"
    elif flags["market_attention_high_flag"]:
        label = "market_attention_high"
    elif flags["institutionally_followed_flag"]:
        label = "institutionally_followed"
    elif flags["provider_limited_flag"]:
        label = "unresolved_unknown"
    elif strict_clean:
        label = "candidate_clean_extreme"
    else:
        label = "unresolved_unknown"
    flags["candidate_clean_extreme_flag"] = label == "candidate_clean_extreme"
    flags["unresolved_unknown_flag"] = label == "unresolved_unknown"
    return label, flags


def evidence_note(row: pd.Series) -> str:
    pieces = [
        f"1D AR {pct_text(row.get('ar_1d'))}" if pct_text(row.get("ar_1d")) else "",
        f"5D AR {pct_text(row.get('ar_5d'))}" if pct_text(row.get("ar_5d")) else "",
    ]
    if boolish(row.get("official_confounded_flag")):
        pieces.append(
            "official filings/earnings flags: "
            + compact_join(
                [
                    row.get("sec_reason_codes", ""),
                    f"filings_pm5={clean_float(row.get('filing_count_pm5')) or 0:.0f}",
                ]
            )
        )
    if boolish(row.get("media_confounded_flag")):
        pieces.append(
            "media hits/providers: "
            + compact_join(
                [
                    row.get("news_confounded_reason_final", ""),
                    f"external_hits={clean_float(row.get('provider_hit_count_external')) or 0:.0f}",
                    f"fnspid_pm7={clean_float(row.get('fnspid_news_pm7_count')) or 0:.0f}",
                ]
            )
        )
    if boolish(row.get("bloomberg_news_flow_high_flag")):
        pieces.append(
            "Bloomberg news proxy elevated: "
            f"heat={clean_float(row.get('event_news_heat'))}, "
            f"sentiment={clean_float(row.get('event_news_sentiment'))}"
        )
    if boolish(row.get("market_attention_high_flag")):
        pieces.append(
            "pre-event attention active: "
            f"ret21z={clean_float(row.get('prior_abs_ret_21d_z'))}, "
            f"volz={clean_float(row.get('prior_vol_z'))}"
        )
    if boolish(row.get("institutionally_followed_flag")):
        pieces.append(
            "institutional following/high salience: "
            f"analysts={clean_float(row.get('event_tot_analyst_rec'))}, "
            f"top5={boolish(row.get('top5_flag'))}"
        )
    if boolish(row.get("provider_limited_flag")):
        pieces.append(
            "provider coverage incomplete/limited: "
            + compact_join(
                [
                    row.get("best_available_news_status", ""),
                    f"unknown={clean_float(row.get('provider_unknown_count')) or 0:.0f}",
                    row.get("gdelt_retry_query_status", ""),
                ]
            )
        )
    return "; ".join(piece for piece in pieces if piece)[:900]


def classify_audit(audit: pd.DataFrame) -> pd.DataFrame:
    labels: list[str] = []
    flag_rows: list[dict[str, bool]] = []
    for _, row in audit.iterrows():
        label, flags = classify_row(row)
        labels.append(label)
        flag_rows.append(flags)
    flags_df = pd.DataFrame(flag_rows)
    out = pd.concat([audit.reset_index(drop=True), flags_df], axis=1)
    out["classification_label"] = labels
    out["evidence_note"] = out.apply(evidence_note, axis=1)
    out["ar_1d_pct"] = out["ar_1d"].map(pct_text)
    out["ar_5d_pct"] = out["ar_5d"].map(pct_text)
    out = out.sort_values("strongest_selection_abs_ar", ascending=False).reset_index(drop=True)
    return out


def summary_rows(audit: pd.DataFrame, selections: pd.DataFrame) -> list[dict[str, Any]]:
    total = len(audit)
    rows: list[dict[str, Any]] = [
        {
            "metric": "audited_unique_events",
            "count": total,
            "percent": "100.0%",
            "notes": "Unique event IDs selected from top/bottom 25 1D and 5D abnormal returns.",
        }
    ]
    for bucket in ["positive_1d", "negative_1d", "positive_5d", "negative_5d"]:
        count = int(audit[bucket].sum()) if bucket in audit.columns else 0
        rows.append(
            {
                "metric": f"bucket_{bucket}",
                "count": count,
                "percent": f"{100.0 * count / total:.1f}%" if total else "",
                "notes": "Bucket memberships are not mutually exclusive after event-id deduplication.",
            }
        )
    for label in [
        "official_confounded",
        "media_confounded",
        "bloomberg_news_flow_high",
        "market_attention_high",
        "institutionally_followed",
        "unresolved_unknown",
        "candidate_clean_extreme",
    ]:
        count = int((audit["classification_label"] == label).sum())
        rows.append(
            {
                "metric": label,
                "count": count,
                "percent": f"{100.0 * count / total:.1f}%" if total else "",
                "notes": "Primary conservative classification; priority order avoids double-counting.",
            }
        )
    rows.append(
        {
            "metric": "selection_rows_before_dedup",
            "count": len(selections),
            "percent": "",
            "notes": f"{TOP_N_PER_BUCKET} rows requested for each of four return buckets.",
        }
    )
    rows.append(
        {
            "metric": "provider_checks_used",
            "count": "",
            "percent": "",
            "notes": (
                "Existing cached/derived Alpha Vantage, GDELT, FNSPID, fallback provider, "
                "news_confound_master, and Bloomberg proxy layers; no broad news rebuild."
            ),
        }
    )
    return rows


def md_table(frame: pd.DataFrame, columns: list[str], limit: int = 80) -> str:
    if frame.empty:
        return "_No rows._"
    rows = frame[columns].head(limit).fillna("").astype(str).to_dict("records")
    out = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        escaped = [
            row.get(col, "").replace("|", "\\|").replace("\n", " ")
            for col in columns
        ]
        out.append("| " + " | ".join(escaped) + " |")
    return "\n".join(out)


def illustrative_examples(audit: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    ranked = audit.sort_values("strongest_selection_abs_ar", ascending=False).copy()
    examples = ranked.drop_duplicates(["ticker", "event_date"], keep="first").head(limit)
    if len(examples) < limit:
        remaining = ranked[~ranked["event_id"].isin(examples["event_id"])]
        examples = pd.concat([examples, remaining.head(limit - len(examples))], ignore_index=True)
    return examples.head(limit)


def write_outputs(audit: pd.DataFrame, selections: pd.DataFrame) -> pd.DataFrame:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    audit.to_csv(OUT_DIR / "extreme_event_news_audit.csv", index=False)
    summary = pd.DataFrame(summary_rows(audit, selections))
    summary.to_csv(OUT_DIR / "extreme_event_news_audit_summary.csv", index=False)

    language = (
        "The extreme-event news audit examines the largest positive and negative return reactions, "
        "rather than attempting to certify the full sample as news-clean. The audit is diagnostic: "
        "it shows whether the largest return moves coincide with official filings, public-news "
        "indicators, Bloomberg news-flow proxies, market-implied attention, or institutional "
        "following. Events with incomplete provider coverage remain unknown, not clean."
    )
    examples = illustrative_examples(audit)
    summary_md = [
        "# Extreme-Event News Audit Summary",
        "",
        language,
        "",
        "## Counts",
        "",
        md_table(summary, ["metric", "count", "percent", "notes"], limit=40),
        "",
        "## Provider Scope",
        "",
        (
            "Provider checks use existing cached/derived layers only: Alpha Vantage and GDELT "
            "diagnostics, FNSPID/media flags, provider compact-cache summaries, the conservative "
            "news_confound_master panel, Bloomberg News Heat/Sentiment proxies, market-implied "
            "attention, and Bloomberg analyst coverage. No raw article bodies are written."
        ),
        "",
        "## Top Illustrative Examples",
        "",
        md_table(
            examples,
            [
                "event_id",
                "ticker",
                "event_date",
                "selection_buckets",
                "ar_1d_pct",
                "ar_5d_pct",
                "classification_label",
                "evidence_note",
            ],
            limit=10,
        ),
    ]
    (OUT_DIR / "extreme_event_news_audit_summary.md").write_text(
        "\n".join(summary_md) + "\n", encoding="utf-8"
    )

    examples_md = [
        "# Extreme-Event Examples",
        "",
        language,
        "",
        md_table(
            examples,
            [
                "event_id",
                "ticker",
                "company_name",
                "event_date",
                "creator",
                "selection_buckets",
                "ar_1d_pct",
                "ar_5d_pct",
                "classification_label",
                "evidence_note",
            ],
            limit=10,
        ),
    ]
    (OUT_DIR / "extreme_event_examples.md").write_text(
        "\n".join(examples_md) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    audit, selections = build_audit_panel()
    audit = classify_audit(audit)
    summary = write_outputs(audit, selections)
    counts = dict(zip(summary["metric"], summary["count"], strict=False))
    print(f"Extreme-event news audit events: {len(audit)}")
    print(
        "Provider checks used: existing cached/derived AV, GDELT, FNSPID/media, "
        "news_confound_master, Bloomberg proxy, analyst coverage, and market-attention layers"
    )
    for label in [
        "official_confounded",
        "media_confounded",
        "bloomberg_news_flow_high",
        "market_attention_high",
        "institutionally_followed",
        "unresolved_unknown",
        "candidate_clean_extreme",
    ]:
        print(f"{label}: {counts.get(label, 0)}")
    print(f"Outputs written to {OUT_DIR.relative_to(utils.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
