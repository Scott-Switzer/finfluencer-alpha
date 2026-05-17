"""Classify events: relay vs original-like vs ambiguous (original_like ≠ true originality)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import information_environment_utils as ie  # noqa: E402
import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = ie.info_dir("originality_taxonomy")


def classify_row(row: pd.Series) -> str:
    if str(row.get("analyst_data_mode", "")) == "diagnostic_current_only":
        analyst_hist = False
    else:
        analyst_hist = row.get("analyst_data_mode") == "event_time_historical"

    pub_unknown = str(row.get("public_news_unknown", row.get("master_unknown", ""))).lower() in {"true", "1"}
    pub_conf = str(row.get("public_news_confounded", row.get("master_confounded", ""))).lower() in {"true", "1"}
    sec_conf = str(row.get("sec_confounded", "")).lower() in {"true", "1"}

    analyst_relay = int(row.get("analyst_relay_score", 0) or 0) >= 2
    news_relay = int(row.get("news_relay_score", 0) or 0) >= 2
    earn_relay = int(row.get("earnings_relay_score", 0) or 0) >= 2
    mkt_relay = int(row.get("market_move_relay_score", 0) or 0) >= 2
    hype = int(row.get("retail_hype_score", 0) or 0) >= 2
    valuation = int(row.get("valuation_score", 0) or 0) >= 2
    contrarian = bool(row.get("finfluencer_contrarian_to_analyst"))
    market_quiet = str(row.get("market_quiet", "")).lower() in {"true", "1"}

    if pub_unknown and not analyst_hist:
        return "insufficient_external_data"
    if sec_conf or pub_conf or earn_relay or news_relay:
        return "official_news_relay"
    if analyst_relay or str(row.get("analyst_alignment", "")).startswith("analyst_bullish"):
        if analyst_hist or not str(row.get("analyst_alignment", "")).startswith("diagnostic"):
            return "analyst_relay"
    if mkt_relay and not market_quiet:
        return "market_reaction_relay"
    if hype or int(row.get("urgency_score", 0) or 0) >= 2:
        return "retail_hype_attention"
    if valuation and not hype:
        return "valuation_or_fundamental_original_like"
    if contrarian and analyst_hist:
        return "contrarian_original_like"
    return "ambiguous_mixed"


def main() -> int:
    events = rf.build_event_feature_table()
    if events.empty:
        return 0

    paths = {
        "analyst": ie.INFO_ENV / "analyst_relay" / "analyst_relay_event_panel.csv",
        "sentiment": ie.INFO_ENV / "market_sentiment" / "market_sentiment_event_panel.csv",
        "transcript": ie.INFO_ENV / "transcript_narrative_relay" / "transcript_narrative_relay_event_panel.csv",
        "market_implied": utils.OUT_DIR / "market_implied_confounds" / "market_implied_confound_panel.csv",
        "confounds": utils.OUT_DIR / "confounds_expanded" / "01_v2_master_confound_panel_expanded.csv",
    }
    df = events.copy()
    for _name, path in paths.items():
        if path.exists():
            part = pd.read_csv(path)
            drop = [c for c in part.columns if c in df.columns and c != "event_id"]
            df = df.merge(part.drop(columns=drop, errors="ignore"), on="event_id", how="left")

    df["originality_bucket"] = df.apply(classify_row, axis=1)
    df[["event_id", "ticker", "event_date", "recommendation_type", "top5_flag", "originality_bucket"]].to_csv(
        OUT / "information_originality_event_panel.csv", index=False
    )

    fwd = utils.forward_panel(["21D"])
    merged = fwd.merge(df, on="event_id", how="left", suffixes=("", "_orig"))
    tick_col = "ticker" if "ticker" in merged.columns else "ticker_orig"
    rows: list[dict] = []
    for bucket, grp in merged.groupby("originality_bucket"):
        for sample, mask in [
            ("full", pd.Series(True, index=grp.index)),
            ("top5", grp[tick_col].isin(utils.TOP5)),
            ("non_top", ~grp[tick_col].isin(utils.TOP5)),
        ]:
            g = grp.loc[mask]
            stats = utils.t_stats(g["spy_bhar"].dropna().astype(float).tolist())
            rows.append({"bucket": bucket, "sample": sample, "n": stats["n"], "mean_spy_bhar_21d": stats["mean"]})
    utils.write_csv(OUT / "returns_by_originality_bucket.csv", rows, list(rows[0]) if rows else ["bucket"])
    utils.write_md(OUT / "returns_by_originality_bucket.md", "Returns by Originality Bucket", utils.md_table(rows))

    counts = df["originality_bucket"].value_counts().to_dict()
    relay_share = sum(
        counts.get(k, 0)
        for k in [
            "official_news_relay",
            "analyst_relay",
            "market_reaction_relay",
            "retail_hype_attention",
        ]
    ) / max(len(df), 1)

    tax_path = utils.OUT_DIR / "research_frontier" / "creator_skill_taxonomy" / "creator_skill_taxonomy.csv"
    creator_note = ""
    if tax_path.exists():
        tax = pd.read_csv(tax_path)
        merged_c = df.merge(tax[["creator", "taxonomy"]], left_on="creator", right_on="creator", how="left")
        top_tax = (
            merged_c.groupby(["originality_bucket", "taxonomy"]).size().reset_index(name="n").sort_values("n", ascending=False).head(15)
        )
        creator_note = "\n\n### Creator taxonomy cross-tab (top cells)\n" + utils.md_table(top_tax.to_dict("records"))

    summary = f"""# Information originality taxonomy

**original_like ≠ verified originality.**

| Bucket | Count |
| --- | --- |
{chr(10).join(f'| {k} | {v} |' for k, v in sorted(counts.items(), key=lambda x: -x[1]))}

Relay-like share (broad): **{relay_share:.1%}**

Compare `valuation_or_fundamental_original_like` vs relay buckets in `returns_by_originality_bucket.csv`.
Public-news unknown remains unresolved; non-top master-clean **n=0**.
{creator_note}
"""
    utils.write_md(OUT / "information_originality_summary.md", "Information Originality", summary)
    print("Information originality taxonomy complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
