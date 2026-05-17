from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "confounds"
AV = utils.OUT_DIR / "news_alpha_vantage" / "04_av_event_window_flags.csv"
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
        panel = panel.merge(av[["event_id", "av_news_clean_flag", "av_news_confounded_flag", "av_news_unknown_flag"]], on="event_id", how="left")
    if GD.exists():
        gd = pd.read_csv(GD)
        panel = panel.merge(gd[["event_id", "gdelt_news_clean_flag", "gdelt_news_confounded_flag", "gdelt_news_unknown_flag"]], on="event_id", how="left")
    if SEC.exists():
        sec = pd.read_csv(SEC)
        panel = panel.merge(sec[["event_id", "sec_clean_expanded_flag", "sec_material_event_confounded_flag", "sec_unknown_flag"]], on="event_id", how="left")
    av_clean = bool_col(panel, "av_news_clean_flag")
    av_conf = bool_col(panel, "av_news_confounded_flag")
    av_unknown = bool_col(panel, "av_news_unknown_flag") | (~av_clean & ~av_conf)
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
        lambda r: "master_clean" if r.master_clean else "master_confounded" if r.master_confounded else "master_unknown_not_clean",
        axis=1,
    )
    utils.write_csv(OUT_DIR / "01_v2_master_confound_panel.csv", panel.to_dict("records"), list(panel.columns))
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
    utils.table_pair(OUT_DIR / "02_v2_confound_coverage_summary", summary, "Master Confound Coverage")
    returns = utils.forward_panel().merge(panel[["event_id", "master_clean", "master_confounded", "master_unknown", "public_news_clean"]], on="event_id", how="left")
    masks = {
        "full_sample": pd.Series(True, index=returns.index),
        "master_clean": bool_col(returns, "master_clean"),
        "master_confounded": bool_col(returns, "master_confounded"),
        "master_unknown": bool_col(returns, "master_unknown"),
        "top5_master_clean": bool_col(returns, "top5_flag") & bool_col(returns, "master_clean"),
        "non_top_master_clean": ~bool_col(returns, "top5_flag") & bool_col(returns, "master_clean"),
        "low_lookahead_master_clean": bool_col(returns, "low_lookahead_flag") & bool_col(returns, "master_clean"),
        "duplicate_collapsed_master_clean": bool_col(returns, "duplicate_collapsed_flag") & bool_col(returns, "master_clean"),
    }
    rows = []
    for name, mask in masks.items():
        rows.extend(utils.summarize_return_panel(returns[mask], "spy_bhar", {name: pd.Series(True, index=returns[mask].index)}))
    utils.table_pair(OUT_DIR / "03_v2_clean_confounded_unknown_return_summary", rows, "Clean Confounded Unknown Return Summary")
    utils.write_md(
        OUT_DIR / "04_v2_confound_interpretation.md",
        "Master Confound Interpretation",
        "Master clean requires real public-news coverage and SEC/earnings clean status. Unknown is never treated as clean. If public-news coverage is sparse, master-clean evidence remains partial and should not be presented as full-sample news robustness.",
    )
    print(
        "Master confound panel complete: "
        f"clean={int(master_clean.sum())} confounded={int(master_conf.sum())} unknown={int(master_unknown.sum())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
