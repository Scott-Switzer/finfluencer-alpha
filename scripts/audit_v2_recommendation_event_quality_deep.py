"""Deep event-quality audit: concentration, repetition, and cross-horizon coherence (metadata-only)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "event_quality_deep_audit"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = utils.event_manifest()
    manifest["top5_flag"] = manifest["ticker"].astype(str).isin(utils.TOP5)

    ticker_counts = manifest.groupby("ticker", as_index=False).size().rename(columns={"size": "event_count_ticker"})
    creator_counts = manifest.groupby("creator", as_index=False).size().rename(columns={"size": "event_count_creator"})
    m = manifest.merge(ticker_counts, on="ticker", how="left").merge(creator_counts, on="creator", how="left")

    panel = utils.long_panel()
    sub = panel[(panel["window_type"] == "forward") & panel["horizon"].isin(["5D", "21D", "63D", "126D"])].drop_duplicates(
        subset=["event_id", "horizon"]
    )
    pivot = sub.pivot_table(index="event_id", columns="horizon", values="spy_bhar", aggfunc="first")
    coh_rows = []
    for eid, row in pivot.iterrows():
        vals = [utils.clean_float(row.get(h)) for h in ["5D", "21D", "63D", "126D"]]
        vals = [v for v in vals if v is not None]
        same_sign = len({v > 0 for v in vals}) <= 1 if vals else False
        coh_rows.append({"event_id": int(eid), "n_horizons_observed": len(vals), "bhars_same_sign_all_observed": same_sign})
    coh = pd.DataFrame(coh_rows)
    deep = m.merge(coh, on="event_id", how="left")
    deep["ticker_concentration_tier"] = pd.cut(
        deep["event_count_ticker"], bins=[0, 1, 3, 10, 10_000], labels=["single", "low", "medium", "high"]
    ).astype(str)
    deep["creator_burst_tier"] = pd.cut(
        deep["event_count_creator"], bins=[0, 5, 15, 50, 10_000], labels=["low", "medium", "high", "very_high"]
    ).astype(str)
    deep["deep_quality_risk_score"] = (
        deep["event_count_ticker"].clip(upper=50) / 50.0 * 30
        + deep["event_count_creator"].clip(upper=80) / 80.0 * 30
        + (~deep["top5_flag"]).astype(float) * 20
        + (5 - deep["quality_score"].fillna(2).clip(1, 5)).astype(float) / 4.0 * 20
    ).round(1)

    cols = [c for c in deep.columns if c]
    utils.write_csv(OUT_DIR / "01_event_quality_deep_scores.csv", deep.to_dict("records"), cols)

    risk_summary = (
        deep.groupby(["ticker_concentration_tier", "creator_burst_tier"], dropna=False)
        .agg(events=("event_id", "count"), mean_risk=("deep_quality_risk_score", "mean"))
        .reset_index()
    )
    utils.table_pair(OUT_DIR / "02_concentration_risk_summary", risk_summary.to_dict("records"), "Concentration Risk Summary")

    merged = utils.forward_panel().merge(
        deep[["event_id", "deep_quality_risk_score", "bhars_same_sign_all_observed"]], on="event_id", how="left"
    )
    med = float(merged["deep_quality_risk_score"].median())
    q75 = float(merged["deep_quality_risk_score"].quantile(0.75))
    masks = {
        "low_deep_risk": merged["deep_quality_risk_score"].astype(float) <= med,
        "high_deep_risk": merged["deep_quality_risk_score"].astype(float) > q75,
        "coherent_sign_5_21_63_126": merged["bhars_same_sign_all_observed"].astype(str).str.lower().eq("true"),
    }
    rows = []
    for name, mask in masks.items():
        m2 = mask.fillna(False)
        sub = merged.loc[m2]
        rows.extend(
            utils.summarize_return_panel(sub, "spy_bhar", {name: pd.Series(True, index=sub.index)})
        )
    utils.table_pair(OUT_DIR / "03_deep_quality_return_slices", rows, "Deep Quality Return Slices")

    utils.write_md(
        OUT_DIR / "04_deep_audit_memo.md",
        "Deep Event Quality Audit Memo",
        "Metadata-only depth pass: ticker/creator concentration, proxy confidence inversion, and coarse BHAR sign "
        "coherence across 5D–126D. Does not export transcript text. High risk scores highlight names/creators needing "
        "manual review; they are not automatic exclusions.",
    )
    print("Deep event quality audit complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
