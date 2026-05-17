"""Market-implied activity screen — sensitivity layer, NOT public-news-clean."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = utils.OUT_DIR / "market_implied_confounds"
Z_THRESH_ACTIVE = 1.5
Z_THRESH_QUIET = 1.0


def zscore(series: pd.Series) -> pd.Series:
    s = series.astype(float)
    mu, sd = s.mean(), s.std()
    if sd == 0 or np.isnan(sd):
        return pd.Series(0.0, index=s.index)
    return (s - mu) / sd


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    base = rf.build_event_feature_table()
    if base.empty:
        return 0

    for col in ["prior_return_1d", "prior_return_5d", "prior_return_21d"]:
        if col not in base.columns:
            base[col] = np.nan
    base["prior_abs_ret_1d_z"] = zscore(base.get("prior_return_1d", pd.Series(dtype=float)).abs())
    base["prior_abs_ret_5d_z"] = zscore(base.get("prior_return_5d", pd.Series(dtype=float)).abs())
    base["prior_abs_ret_21d_z"] = zscore(base.get("prior_return_21d", pd.Series(dtype=float)).abs())
    base["prior_vol_z"] = zscore(base.get("prior_abnormal_volume", pd.Series(dtype=float)).fillna(0))
    base["prior_rvol_z"] = zscore(base.get("prior_volatility_21d", pd.Series(dtype=float)).fillna(0))
    base["post_vol_5d_z"] = zscore(base.get("post_vol_5d", pd.Series(dtype=float)).fillna(0))

    sec_conf = base.get("sec_confounded", pd.Series(False, index=base.index)).astype(str).str.lower().eq("true")
    if "sec_material_event_confounded_flag" in base.columns:
        sec_conf = sec_conf | base["sec_material_event_confounded_flag"].astype(str).str.lower().eq("true")
    av_conf = base.get("av_expanded_news_confounded_flag", pd.Series(False, index=base.index)).astype(str).str.lower().eq(
        "true"
    )
    gd_conf = base.get("gdelt_news_confounded_flag", pd.Series(False, index=base.index)).astype(str).str.lower().eq("true")
    av_unk = base.get("av_expanded_news_unknown_flag", pd.Series(True, index=base.index)).astype(str).str.lower().eq("true")

    pre_active = (
        (base["prior_abs_ret_5d_z"].abs() > Z_THRESH_ACTIVE)
        | (base["prior_abs_ret_21d_z"].abs() > Z_THRESH_ACTIVE)
        | (base["prior_vol_z"].abs() > Z_THRESH_ACTIVE)
        | (base["prior_rvol_z"].abs() > Z_THRESH_ACTIVE)
    )
    market_quiet = (
        (base["prior_abs_ret_5d_z"].abs() <= Z_THRESH_QUIET)
        & (base["prior_abs_ret_21d_z"].abs() <= Z_THRESH_QUIET)
        & (base["prior_vol_z"].abs() <= Z_THRESH_QUIET)
    )
    base["market_quiet"] = market_quiet
    base["market_active_pre_event"] = pre_active
    base["official_confounded"] = sec_conf
    base["news_confounded"] = av_conf | gd_conf
    base["unknown_news_market_quiet"] = av_unk & market_quiet
    base["unknown_news_market_active"] = av_unk & pre_active

    base.to_csv(OUT / "market_implied_confound_panel.csv", index=False)

    panel = utils.forward_panel(["5D", "21D", "63D", "126D"])
    merged = panel.merge(base, on="event_id", how="left", suffixes=("", "_feat"))
    tick_col = "ticker" if "ticker" in merged.columns else "ticker_feat"
    merged["top5_flag"] = merged[tick_col].astype(str).isin(utils.TOP5)
    lp = utils.long_panel()
    if "duplicate_collapsed_flag" in lp.columns:
        dc = lp.drop_duplicates("event_id")[["event_id", "duplicate_collapsed_flag"]]
        merged = merged.merge(dc, on="event_id", how="left")
    if "low_lookahead_flag" not in merged.columns and "low_lookahead_flag" in lp.columns:
        merged = merged.merge(lp.drop_duplicates("event_id")[["event_id", "low_lookahead_flag"]], on="event_id", how="left")

    masks = {
        "full_sample": pd.Series(True, index=merged.index),
        "top5": merged["top5_flag"],
        "non_top": ~merged["top5_flag"],
        "non_top_market_quiet": (~merged["top5_flag"]) & merged["market_quiet"].fillna(False),
        "high_conf_market_quiet": merged["high_confidence"].fillna(False).astype(bool)
        & merged["market_quiet"].fillna(False)
        if "high_confidence" in merged.columns
        else pd.Series(False, index=merged.index),
        "dup_collapsed_market_quiet": merged["duplicate_collapsed_flag"].astype(str).str.lower().eq("true")
        & merged["market_quiet"].fillna(False)
        if "duplicate_collapsed_flag" in merged.columns
        else pd.Series(False, index=merged.index),
    }
    rows = []
    for name, mask in masks.items():
        m = mask.reindex(merged.index, fill_value=False).astype(bool)
        rows.extend(utils.summarize_return_panel(merged.loc[m], "spy_bhar", {name: pd.Series(True, index=merged.loc[m].index)}))
    utils.write_csv(OUT / "returns_by_market_confound_bucket.csv", rows, list(rows[0]) if rows else ["sample"])
    utils.table_pair(OUT / "returns_by_market_confound_bucket", rows, "Returns by Market Confound Bucket")

    summary = f"""# Market-implied confound screen

**Not public-news-clean.** This layer flags pre-event market activity using return/volume z-scores.

| Flag | N events |
| --- | --- |
| market_quiet | {int(market_quiet.sum())} |
| market_active_pre_event | {int(pre_active.sum())} |
| unknown_news_market_quiet | {int((av_unk & market_quiet).sum())} |
| unknown_news_market_active | {int((av_unk & pre_active).sum())} |

Use `non_top_market_quiet` return slices as a **sensitivity** check only. Unknown news remains **not clean**.
"""
    utils.write_md(OUT / "market_implied_confound_summary.md", "Market Implied Confound Summary", summary)
    print("Market implied confound screen complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
