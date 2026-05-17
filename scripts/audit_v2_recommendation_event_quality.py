from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "event_quality_audit"


def score_row(row: pd.Series) -> dict[str, object]:
    quality = int(row.get("quality_score", 0) or 0)
    ticker = str(row.ticker)
    rec = str(row.recommendation_type)
    top5 = ticker in utils.TOP5
    low_lookahead = str(row.get("upload_timing_bucket", "")) in {"before_open", "weekend_or_holiday"}
    confidence = min(100, max(20, quality * 20 + (10 if low_lookahead else 0) + (5 if top5 else 0)))
    ambiguous = quality <= 2
    false_positive = len(ticker) <= 2 or ticker in {"ON", "AI"}
    return {
        "event_id": int(row.event_id),
        "video_id": row.video_id,
        "ticker": ticker,
        "company_name": row.company_name,
        "creator": row.creator,
        "publish_date": row.event_date,
        "recommendation_type": rec,
        "event_quality_score": quality,
        "classification_confidence": confidence,
        "direction_confidence": confidence - (10 if rec not in {"buy", "sell"} else 0),
        "ticker_disambiguation_score": 60 if false_positive else 90,
        "evidence_verb_count": 1 if rec in {"buy", "sell"} else 0,
        "explicit_buy_sell_hold_terms": rec,
        "conditional_language_flag": quality <= 2,
        "ambiguous_language_flag": ambiguous,
        "historical_discussion_flag": False,
        "option_or_crypto_confusion_flag": False,
        "ticker_false_positive_risk": false_positive,
        "duplicate_cluster_id": row.get("duplicate_cluster_id", ""),
        "duplicate_nearby_event_count": row.get("duplicate_cluster_size", ""),
        "lookahead_risk_score": 20 if low_lookahead else 70,
        "low_lookahead_flag": low_lookahead,
        "top5_flag": top5,
        "evidence_excerpt_short_hash": utils.safe_hash(row.event_id, row.video_id, ticker, rec),
        "reason_codes": "proxy_quality_from_locked_manifest_no_transcript_text_exported",
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = utils.event_manifest()
    scored = pd.DataFrame([score_row(row) for _, row in manifest.iterrows()])
    scored["confidence_bucket"] = pd.cut(
        scored["classification_confidence"], bins=[0, 49, 74, 100], labels=["low", "medium", "high"]
    ).astype(str)
    utils.write_csv(OUT_DIR / "01_event_quality_scores.csv", scored.to_dict("records"), list(scored.columns))
    distribution = scored.groupby("confidence_bucket", dropna=False).size().reset_index(name="events")
    dist_rows = distribution.to_dict("records")
    utils.table_pair(OUT_DIR / "02_event_quality_distribution", dist_rows, "Event Quality Distribution")
    panel = utils.forward_panel()
    merged = panel.merge(scored[["event_id", "confidence_bucket", "ambiguous_language_flag", "ticker_false_positive_risk"]], on="event_id", how="left")
    masks = {
        "high_confidence": merged["confidence_bucket"].eq("high"),
        "medium_or_high_confidence": merged["confidence_bucket"].isin(["medium", "high"]),
        "excluding_ambiguous": ~merged["ambiguous_language_flag"].astype(str).str.lower().eq("true"),
        "excluding_ticker_false_positive_risk": ~merged["ticker_false_positive_risk"].astype(str).str.lower().eq("true"),
        "top5_high_confidence": merged["top5_flag"].astype(str).str.lower().eq("true") & merged["confidence_bucket"].eq("high"),
        "non_top_high_confidence": ~merged["top5_flag"].astype(str).str.lower().eq("true") & merged["confidence_bucket"].eq("high"),
    }
    rows = []
    for name, mask in masks.items():
        rows.extend(utils.summarize_return_panel(merged[mask], "spy_bhar", {name: pd.Series(True, index=merged[mask].index)}))
    utils.table_pair(OUT_DIR / "03_quality_filtered_return_summary", rows, "Quality Filtered Return Summary")
    examples = scored.sort_values(["classification_confidence", "ticker_false_positive_risk"]).head(50)
    utils.write_csv(OUT_DIR / "04_low_confidence_event_examples.csv", examples.to_dict("records"), list(examples.columns))
    utils.write_md(
        OUT_DIR / "05_event_classification_audit_memo.md",
        "Event Classification Audit Memo",
        "This audit uses metadata/proxy quality fields and does not export transcript text. It is a defensibility screen, not a substitute for manual transcript review. Findings should be stronger only when they survive medium/high-confidence filters and duplicate/lookahead exclusions.",
    )
    print("Event quality audit complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
