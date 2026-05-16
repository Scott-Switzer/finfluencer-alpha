from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
CREATOR_DIR = OUT_DIR / "creator_deep_dive"
CREATOR_DIR.mkdir(parents=True, exist_ok=True)


def event_df() -> pd.DataFrame:
    events = base.fetch_events(base.load_market_data())
    return pd.DataFrame(
        [
            {
                "event_id": e.event_id,
                "creator": e.creator,
                "channel_id": e.channel_id,
                "ticker": e.ticker,
                "top5": e.ticker in base.TOP5_TICKERS,
                "buy": e.recommendation_type == "buy",
                "quality": e.actionability_score,
                "timing": e.timing_bucket,
                "duplicate_cluster_id": e.duplicate_cluster_id,
                "duplicate_cluster_size": e.duplicate_cluster_size,
                "ar_1d": e.ar_1d,
                "ar_5d": e.ar_5d,
            }
            for e in events
        ]
    )


def summarize_group(group: pd.DataFrame) -> dict[str, str]:
    values_1d = group["ar_1d"].dropna().astype(float).tolist()
    values_5d = group["ar_5d"].dropna().astype(float).tolist()
    stats_1d = base.t_test(values_1d)
    stats_5d = base.t_test(values_5d)
    return {
        "mean_1d_ar": base.fmt(stats_1d["mean"]),
        "mean_5d_ar": base.fmt(stats_5d["mean"]),
        "t_5d": base.fmt(stats_5d["t"], 3),
        "p_5d": base.fmt(stats_5d["p"], 6),
        "median_5d_ar": base.fmt(stats_5d["median"]),
        "win_rate_5d": base.fmt(stats_5d["win_rate"]),
    }


def main() -> int:
    df = event_df()
    transcript_manifest = pd.read_csv(OUT_DIR / "locked_sample_v2" / "01_v2_transcript_manifest.csv")
    transcript_counts = transcript_manifest.groupby("creator")["video_id"].nunique().to_dict()
    sec_path = OUT_DIR / "sec" / "02_v2_sec_event_flags.csv"
    sec_share = {}
    if sec_path.exists():
        sec = pd.read_csv(sec_path)
        merged = df[["event_id", "creator"]].merge(sec[["event_id", "sec_confounded_flag"]], on="event_id")
        sec_share = merged.groupby("creator")["sec_confounded_flag"].mean().to_dict()
    total_return_sum = df["ar_5d"].dropna().sum()
    rows = []
    ticker_means = df.groupby("ticker")["ar_5d"].mean().to_dict()
    residuals = []
    for _idx, row in df.iterrows():
        residuals.append(row["ar_5d"] - ticker_means.get(row["ticker"], 0.0) if pd.notna(row["ar_5d"]) else None)
    df["ticker_residual_5d"] = residuals
    for creator, group in df.groupby("creator"):
        ret_sum = group["ar_5d"].dropna().sum()
        rows.append(
            {
                "creator": creator,
                "channel_id": group["channel_id"].dropna().iloc[0] if not group.empty else "",
                "transcript_count": int(transcript_counts.get(creator, 0)),
                "event_count": len(group),
                "buy_count": int(group["buy"].sum()),
                "sell_count": int((~group["buy"]).sum()),
                "top5_share": base.fmt(group["top5"].mean()),
                "non_top_share": base.fmt((~group["top5"]).mean()),
                "avg_quality_score": base.fmt(group["quality"].mean()),
                "avg_pre_event_momentum": "",
                **summarize_group(group),
                "duplicate_rate": base.fmt((group["duplicate_cluster_size"] > 1).mean()),
                "low_lookahead_share": base.fmt(group["timing"].isin(base.LOW_LOOKAHEAD_BUCKETS).mean()),
                "SEC_confounded_share": base.fmt(sec_share.get(creator)),
                "return_contribution_share": base.fmt(None if total_return_sum == 0 else ret_sum / total_return_sum),
            }
        )
    rows = sorted(rows, key=lambda row: int(row["event_count"]), reverse=True)
    base.write_csv(CREATOR_DIR / "01_creator_summary.csv", rows, list(rows[0]))
    base.write_md(
        CREATOR_DIR / "01_creator_summary.md",
        "# V2 Creator Summary\n\n" + base.markdown_table(rows, list(rows[0])),
    )
    adjusted_rows = []
    for creator, group in df.groupby("creator"):
        top = group[group["top5"]]
        non = group[~group["top5"]]
        adjusted_rows.append(
            {
                "creator": creator,
                "raw_5d_ar": base.fmt(group["ar_5d"].mean()),
                "top5_adjusted_5d_ar": base.fmt(group["ticker_residual_5d"].mean()),
                "non_top_5d_ar": base.fmt(non["ar_5d"].mean()),
                "residual_creator_signal_after_ticker_controls": base.fmt(group["ticker_residual_5d"].mean()),
                "interpretation": "ticker-mix-adjusted residual, not causal creator skill",
                "top5_event_count": len(top),
                "non_top_event_count": len(non),
            }
        )
    adjusted_rows = sorted(adjusted_rows, key=lambda row: row["creator"])
    base.write_csv(CREATOR_DIR / "02_creator_top5_adjusted.csv", adjusted_rows, list(adjusted_rows[0]))
    base.write_md(
        CREATOR_DIR / "02_creator_top5_adjusted.md",
        "# V2 Creator Top-5 Adjusted Results\n\n"
        + base.markdown_table(adjusted_rows, list(adjusted_rows[0])),
    )
    loo_rows = []
    for creator in sorted(df["creator"].unique()):
        remaining = df[df["creator"] != creator]
        all_stats = base.t_test(remaining["ar_5d"].dropna().astype(float).tolist())
        top_stats = base.t_test(remaining[remaining["top5"]]["ar_5d"].dropna().astype(float).tolist())
        non_stats = base.t_test(remaining[~remaining["top5"]]["ar_5d"].dropna().astype(float).tolist())
        loo_rows.append(
            {
                "removed_creator": creator,
                "remaining_events": len(remaining),
                "headline_5d_mean": base.fmt(all_stats["mean"]),
                "headline_5d_p": base.fmt(all_stats["p"], 6),
                "top5_5d_mean": base.fmt(top_stats["mean"]),
                "top5_5d_p": base.fmt(top_stats["p"], 6),
                "non_top_5d_mean": base.fmt(non_stats["mean"]),
                "non_top_5d_p": base.fmt(non_stats["p"], 6),
            }
        )
    base.write_csv(CREATOR_DIR / "03_creator_leave_one_out.csv", loo_rows, list(loo_rows[0]))
    base.write_md(
        CREATOR_DIR / "03_creator_leave_one_out.md",
        "# V2 Creator Leave-One-Out\n\n" + base.markdown_table(loo_rows, list(loo_rows[0])),
    )
    style_rows = []
    for creator, group in df.groupby("creator"):
        top5_share = group["top5"].mean()
        duplicate_rate = (group["duplicate_cluster_size"] > 1).mean()
        buy_share = group["buy"].mean()
        if top5_share >= 0.75:
            cluster = "top5_concentrated"
        elif duplicate_rate >= 0.40:
            cluster = "duplicate_heavy"
        elif buy_share >= 0.85:
            cluster = "buy_heavy"
        else:
            cluster = "mixed"
        style_rows.append(
            {
                "creator": creator,
                "event_count": len(group),
                "ticker_concentration_top5_share": base.fmt(top5_share),
                "buy_share": base.fmt(buy_share),
                "duplicate_rate": base.fmt(duplicate_rate),
                "style_cluster": cluster,
            }
        )
    base.write_csv(CREATOR_DIR / "04_creator_style_clusters.csv", style_rows, list(style_rows[0]))
    base.write_md(
        CREATOR_DIR / "04_creator_style_clusters.md",
        "# V2 Creator Style Clusters\n\n"
        + base.markdown_table(style_rows, list(style_rows[0]))
        + "\n\nClusters are mechanical descriptors, not subjective reputation labels.",
    )
    top_volume = rows[0]["creator"]
    top_return = max(rows, key=lambda row: float(row["return_contribution_share"] or 0))["creator"]
    memo = f"""# V2 Creator Deep Dive Memo

The largest event-volume creator is `{top_volume}`. The largest positive return
contribution share is `{top_return}`. Creator-level performance should be
interpreted cautiously because ticker mix explains much of the variation.

The ticker-residual table is a diagnostic for whether creator effects remain
after subtracting ticker mean returns; it is not evidence of creator skill. For
the paper, anonymized creator labels are safer unless naming is necessary for a
descriptive sample table.
"""
    base.write_md(CREATOR_DIR / "05_creator_deep_dive_memo.md", memo)
    print("V2 creator deep dive complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
