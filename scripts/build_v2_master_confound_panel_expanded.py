"""Master confound panel using expanded Alpha Vantage exports + SEC + GDELT."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "confounds_expanded"
AV = utils.OUT_DIR / "news_alpha_vantage_expanded" / "av_expanded_event_news_panel.csv"
GD = utils.OUT_DIR / "news_gdelt_retry" / "02_gdelt_probe_flags.csv"
SEC = utils.OUT_DIR / "sec_earnings_confounds" / "01_sec_event_flags_expanded.csv"


def bool_col(frame: pd.DataFrame, col: str) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(False, index=frame.index)
    return frame[col].astype(str).str.lower().eq("true")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events = utils.event_manifest()[["event_id", "ticker", "company_name", "event_date", "recommendation_type"]]
    panel = events.copy()
    if AV.exists():
        av = pd.read_csv(AV)
        cols = [
            c
            for c in [
                "av_expanded_news_clean_flag",
                "av_expanded_news_confounded_flag",
                "av_expanded_news_unknown_flag",
            ]
            if c in av.columns
        ]
        if cols:
            panel = panel.merge(av[["event_id"] + cols], on="event_id", how="left")
    if GD.exists():
        gd = pd.read_csv(GD)
        panel = panel.merge(
            gd[["event_id", "gdelt_news_clean_flag", "gdelt_news_confounded_flag", "gdelt_news_unknown_flag"]],
            on="event_id",
            how="left",
        )
    if SEC.exists():
        sec = pd.read_csv(SEC)
        panel = panel.merge(
            sec[["event_id", "sec_clean_expanded_flag", "sec_material_event_confounded_flag", "sec_unknown_flag"]],
            on="event_id",
            how="left",
        )

    av_clean = bool_col(panel, "av_expanded_news_clean_flag")
    av_conf = bool_col(panel, "av_expanded_news_confounded_flag")
    av_unknown = bool_col(panel, "av_expanded_news_unknown_flag") | (~av_clean & ~av_conf)
    gd_clean = bool_col(panel, "gdelt_news_clean_flag")
    gd_conf = bool_col(panel, "gdelt_news_confounded_flag")
    gd_unknown = bool_col(panel, "gdelt_news_unknown_flag") | (~gd_clean & ~gd_conf)
    sec_clean = bool_col(panel, "sec_clean_expanded_flag")
    sec_conf = bool_col(panel, "sec_material_event_confounded_flag")
    sec_unknown = bool_col(panel, "sec_unknown_flag") | (~sec_clean & ~sec_conf)

    public_success = av_clean | av_conf | gd_clean | gd_conf
    public_conf = av_conf | gd_conf
    public_clean = public_success & ~public_conf
    public_unknown = ~public_success | (av_unknown & gd_unknown)
    master_conf = public_conf | sec_conf
    master_clean = public_clean & sec_clean & ~master_conf
    master_unknown = (~master_clean & ~master_conf) | public_unknown | sec_unknown

    panel["public_news_clean"] = public_clean
    panel["public_news_confounded"] = public_conf
    panel["public_news_unknown"] = public_unknown
    panel["sec_clean"] = sec_clean
    panel["sec_confounded"] = sec_conf
    panel["sec_unknown"] = sec_unknown
    panel["master_clean"] = master_clean
    panel["master_confounded"] = master_conf
    panel["master_unknown"] = master_unknown
    panel["reason_codes"] = panel.apply(
        lambda r: "master_clean"
        if r.master_clean
        else "master_confounded"
        if r.master_confounded
        else "master_unknown_not_clean",
        axis=1,
    )
    utils.write_csv(OUT_DIR / "01_v2_master_confound_panel_expanded.csv", panel.to_dict("records"), list(panel.columns))
    summary = [
        {
            "events": len(panel),
            "public_news_clean": int(public_clean.sum()),
            "public_news_confounded": int(public_conf.sum()),
            "public_news_unknown": int(public_unknown.sum()),
            "sec_clean": int(sec_clean.sum()),
            "sec_confounded": int(sec_conf.sum()),
            "sec_unknown": int(sec_unknown.sum()),
            "master_clean": int(master_clean.sum()),
            "master_confounded": int(master_conf.sum()),
            "master_unknown": int(master_unknown.sum()),
        }
    ]
    utils.table_pair(OUT_DIR / "02_v2_confound_coverage_summary_expanded", summary, "Master Confound Coverage Expanded")
    returns = utils.forward_panel().merge(
        panel[["event_id", "master_clean", "master_confounded", "master_unknown", "public_news_clean"]],
        on="event_id",
        how="left",
    )
    masks = {
        "full_sample": pd.Series(True, index=returns.index),
        "master_clean": bool_col(returns, "master_clean"),
        "master_confounded": bool_col(returns, "master_confounded"),
        "master_unknown": bool_col(returns, "master_unknown"),
        "top5_master_clean": bool_col(returns, "top5_flag") & bool_col(returns, "master_clean"),
        "non_top_master_clean": ~bool_col(returns, "top5_flag") & bool_col(returns, "master_clean"),
        "low_lookahead_master_clean": bool_col(returns, "low_lookahead_flag") & bool_col(returns, "master_clean"),
        "duplicate_collapsed_master_clean": bool_col(returns, "duplicate_collapsed_flag")
        & bool_col(returns, "master_clean"),
    }
    rows = []
    for name, mask in masks.items():
        rows.extend(
            utils.summarize_return_panel(
                returns[mask], "spy_bhar", {name: pd.Series(True, index=returns[mask].index)}
            )
        )
    utils.table_pair(
        OUT_DIR / "03_v2_clean_confounded_unknown_return_summary_expanded",
        rows,
        "Clean Confounded Unknown Return Summary Expanded",
    )
    utils.write_md(
        OUT_DIR / "04_v2_confound_interpretation_expanded.md",
        "Master Confound Interpretation Expanded",
        "Uses expanded Alpha Vantage event-level panel where present. Unknown public-news or SEC states are never coded as master-clean. GDELT remains a diagnostic provider.",
    )
    panel_path = OUT_DIR / "01_v2_master_confound_panel_expanded.csv"
    if panel_path.exists():
        panel.to_csv(OUT_DIR / "master_confound_panel_expanded.csv", index=False)
    summary_rows = summary
    utils.write_md(
        OUT_DIR / "master_confound_summary_expanded.md",
        "Master Confound Summary Expanded",
        utils.md_table(summary_rows)
        + "\n\nUnknown public-news or SEC states are never coded as master-clean.",
    )
    returns_path = OUT_DIR / "03_v2_clean_confounded_unknown_return_summary_expanded.md"
    if returns_path.exists():
        returns_path.read_text(encoding="utf-8")
        (OUT_DIR / "returns_by_confound_bucket_expanded.md").write_text(
            returns_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    top5 = utils.TOP5
    non_top_clean = panel[~panel["ticker"].astype(str).isin(top5) & master_clean]
    non_top_n = len(non_top_clean)
    diag = f"""# Non-top master-clean public-news diagnostics

- Non-top master-clean events: **{non_top_n}**
- Top-5 master-clean events: **{int((panel['ticker'].astype(str).isin(top5) & master_clean).sum())}**
- Master clean total: **{int(master_clean.sum())}**

## Interpretation

{"Public-news-clean robustness for **non-top** underperformance is still **not validated** (n=0 or negligible)." if non_top_n < 5 else f"Non-top master-clean n={non_top_n} is small but non-zero; treat return slices as exploratory only."}

Unknown AV/GDELT coverage must never be coded as clean.
"""
    utils.write_md(OUT_DIR / "non_top_clean_news_diagnostics.md", "Non-top Clean News Diagnostics", diag)
    print(
        "Master confound panel expanded complete: "
        f"clean={int(master_clean.sum())} confounded={int(master_conf.sum())} unknown={int(master_unknown.sum())} "
        f"non_top_clean={non_top_n}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
