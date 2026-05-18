"""News label sensitivity bounds for BHAR table."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_v2_public_news_confound_master_layer as ncm  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = utils.OUT_DIR / "news_sensitivity_bounds"
PANEL_PATH = utils.OUT_DIR / "news_confound_master" / "news_confound_event_panel.csv"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not PANEL_PATH.exists():
        print("Missing news_confound_event_panel.csv — run build_v2_public_news_confound_master_layer.py first.")
        return 1
    panel = pd.read_csv(PANEL_PATH)
    returns = ncm.load_forward_returns()
    merged = returns.merge(panel, on="event_id", how="left", suffixes=("", "_p"))
    top5 = merged["top5_flag"].astype(str).str.lower().eq("true")
    align = merged.get("analyst_alignment_event_time", pd.Series("", index=merged.index)).fillna("")

    def add_slice(
        rows: list[dict[str, Any]],
        name: str,
        mask: pd.Series,
        status_col: str = "news_clean_status_final",
    ) -> None:
        if status_col not in merged.columns:
            status_col = "news_clean_status"
        sub = merged[mask.fillna(False)]
        for label in sub[status_col].dropna().unique():
            for h in ("5D", "21D", "63D"):
                g = sub[(sub["horizon"] == h) & (sub["status"] == "computed") & (sub[status_col] == label)]
                st = ncm.return_stats(g["spy_bhar"])
                rows.append({"slice": name, "news_label": str(label), "horizon": h, **st})

    rows: list[dict[str, Any]] = []
    m_all = pd.Series(True, index=merged.index)
    add_slice(rows, "full_sample", m_all)
    if "news_clean_status_final" in merged.columns:
        for ncs, label in (
            ("official_confounded", "exclude_official"),
            ("media_confounded", "exclude_media"),
            ("market_implied_confounded", "exclude_market_implied"),
            ("unknown_news_coverage", "unknown_only"),
        ):
            add_slice(rows, label, m_all & merged["news_clean_status_final"].eq(ncs))
        add_slice(
            rows,
            "exclude_official_and_media",
            m_all
            & ~merged["news_clean_status_final"].isin(["official_confounded", "media_confounded"]),
        )
        add_slice(rows, "multi_source_clean_only", m_all & merged["news_clean_status_final"].eq("multi_source_clean"))
    ext = merged.get("provider_success_count_external", pd.Series(0, index=merged.index))
    qc = merged.get("news_coverage_quality_score", pd.Series(-1, index=merged.index))
    add_slice(rows, "external_success_ge_2", m_all & (pd.to_numeric(ext, errors="coerce").fillna(0) >= 2))
    add_slice(rows, "coverage_quality_ge_3", m_all & (pd.to_numeric(qc, errors="coerce").fillna(-1) >= 3))
    evy = pd.to_datetime(merged["event_date"], errors="coerce").dt.year
    add_slice(rows, "fnspid_years_1999_2023", m_all & evy.between(1999, 2023))
    add_slice(rows, "exclude_2024_2026", m_all & ~evy.between(2024, 2026, inclusive="both"))
    add_slice(rows, "years_2024_2026_only", m_all & evy.between(2024, 2026, inclusive="both"))

    summary_top = merged[top5 & align.eq("analyst_bullish_aligned")]
    summary_nt = merged[~top5 & align.eq("analyst_bullish_aligned")]
    for h in ("5D", "21D", "63D"):
        a = summary_top[(summary_top["horizon"] == h) & (summary_top["status"] == "computed")]["spy_bhar"]
        b = summary_nt[(summary_nt["horizon"] == h) & (summary_nt["status"] == "computed")]["spy_bhar"]
        rows.append(
            {
                "slice": "bullish_top5_vs_nontop_mean_diff",
                "news_label": "all_labels_mixed",
                "horizon": h,
                "n": len(a) + len(b),
                "mean": float(a.mean() - b.mean()) if len(a) and len(b) else "",
                "median": "",
                "t_stat": "",
                "p_value": "",
                "winsorized_mean": "",
                "warning_flag": "overlap_window" if h != "5D" else "",
            }
        )

    pd.DataFrame(rows).to_csv(OUT / "news_sensitivity_bounds_return_table.csv", index=False)
    md = """# News sensitivity bounds\n\nSee `news_sensitivity_bounds_return_table.csv`. Overlapping horizons (21D/63D) are descriptive only.\n"""
    (OUT / "news_sensitivity_bounds_summary.md").write_text(md, encoding="utf-8")
    claim = """# News sensitivity claim matrix\n\nBounds bracket primary results under alternative news-clean assumptions. Unknown coverage is never treated as clean in headline claims.\n"""
    (OUT / "news_sensitivity_claim_matrix.md").write_text(claim, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
