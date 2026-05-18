"""Compact paper robustness diagnostics (calendar portfolios, placebos, pretrends, shrinkage, audit)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT = utils.OUT_DIR / "paper_robustness"
EXHIBITS = utils.OUT_DIR / "final_exhibits"
LIT_DOC = REPO_ROOT / "docs" / "LITERATURE_POSITIONING.md"


def _safe_top(df: pd.DataFrame) -> pd.Series:
    return df["top5_flag"].astype(str).str.lower().isin({"true", "1"})


def _manifest_with_top5(manifest: pd.DataFrame) -> pd.DataFrame:
    m = manifest.copy()
    if "top5_flag" not in m.columns and "ticker" in m.columns:
        m["top5_flag"] = m["ticker"].astype(str).isin(utils.TOP5)
    return m


def calendar_portfolios(long: pd.DataFrame, manifest: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    manifest = _manifest_with_top5(manifest)
    fwd = long[(long["window_type"] == "forward") & long["horizon"].isin(["21D", "63D", "126D"])].copy()
    fwd = fwd[fwd["status"] == "computed"].dropna(subset=["spy_bhar"])
    base = manifest[["event_id", "event_date", "ticker", "top5_flag", "creator"]].merge(
        fwd[["event_id", "horizon", "spy_bhar"]], on="event_id", how="inner"
    )
    base["event_month"] = pd.to_datetime(base["event_date"], errors="coerce").dt.to_period("M").astype(str)
    rows: list[dict] = []
    for (ym, horizon), g in base.groupby(["event_month", "horizon"]):
        n = len(g)
        if n == 0:
            continue
        ew = float(g["spy_bhar"].mean())
        w = np.ones(n) / n
        cap = 0.05
        wc = np.minimum(w, cap)
        wc = wc / wc.sum()
        cw = float((g["spy_bhar"].astype(float) * wc).sum())
        rows.append(
            {
                "calendar_month": ym,
                "horizon": horizon,
                "n_events": n,
                "equal_weight_mean_spy_bhar": round(ew, 6),
                "capped_weight_mean_spy_bhar": round(cw, 6),
            }
        )
    port = pd.DataFrame(rows).sort_values(["calendar_month", "horizon"])
    summ = []
    for horizon, sub in port.groupby("horizon"):
        v = sub["equal_weight_mean_spy_bhar"].astype(float)
        summ.append(
            {
                "horizon": horizon,
                "n_months": int(len(sub)),
                "mean_monthly_ew_portfolio": round(float(v.mean()), 6),
                "std_monthly_ew": round(float(v.std(ddof=1)), 6) if len(v) > 1 else "",
                "t_naive_mean_over_months": round(float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))), 4)
                if len(v) > 1 and float(v.std(ddof=1)) > 0
                else "",
                "note": "Diagnostic EW calendar-time slice; not a tradable mandate.",
            }
        )
    alpha_df = pd.DataFrame(summ)
    body = (
        "# Calendar-time portfolio diagnostic\n\n"
        + utils.md_table(alpha_df.to_dict("records"))
        + "\n\nNo Fama–French factors are bundled in this export; treat as raw mean SPY-BHAR slices, not alpha vs FF.\n"
    )
    return port, alpha_df, body


def pretrend_momentum(long: pd.DataFrame, manifest: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    manifest = _manifest_with_top5(manifest)
    pre_map = {
        "pre_-63_-1": "pre_63_22_proxy",
        "pre_-21_-1": "pre_21_2_proxy",
        "pre_-5_-1": "pre_5_1_proxy",
    }
    post_map = {"5D": "post_5", "21D": "post_21", "63D": "post_63"}
    wide = manifest[["event_id", "ticker", "creator", "top5_flag", "event_date"]].drop_duplicates("event_id")
    for label, colname in pre_map.items():
        sub = long[(long["window_type"] == "pre") & (long["horizon"] == label) & (long["status"] == "computed")][
            ["event_id", "spy_bhar"]
        ].rename(columns={"spy_bhar": colname})
        wide = wide.merge(sub, on="event_id", how="left")
    for h, col in post_map.items():
        sub = long[(long["window_type"] == "forward") & (long["horizon"] == h) & (long["status"] == "computed")][
            ["event_id", "spy_bhar"]
        ].rename(columns={"spy_bhar": col})
        wide = wide.merge(sub, on="event_id", how="left")

    cols = [c for c in wide.columns if c.startswith("pre_") or c.startswith("post_")]
    wide[cols] = wide[cols].apply(pd.to_numeric, errors="coerce")

    def classify(row: pd.Series) -> str:
        pre = row.get("pre_5_1_proxy")
        post = row.get("post_21")
        if pd.isna(pre) or pd.isna(post):
            return ""
        if pre * post > 0:
            return "continuation_or_stack"
        return "reversal_or_contrast"

    wide["momentum_tag_21d"] = wide.apply(classify, axis=1)
    body = "# Pre-trend / momentum decomposition\n\n" + utils.md_table(
        wide.head(25).to_dict("records"),
        limit=25,
    )
    return wide, body


def creator_shrinkage(long: pd.DataFrame, manifest: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    sub = long[(long["window_type"] == "forward") & (long["horizon"] == "21D") & (long["status"] == "computed")][
        ["event_id", "spy_bhar"]
    ]
    base = manifest[["event_id", "creator"]].merge(sub, on="event_id", how="inner")
    base["spy_bhar"] = pd.to_numeric(base["spy_bhar"], errors="coerce")
    base = base.dropna(subset=["spy_bhar", "creator"])
    mu = float(base["spy_bhar"].mean())
    cm = base.groupby("creator")["spy_bhar"].mean()
    var_between = float(cm.var(ddof=1)) if len(cm) > 1 else 0.0
    # Shrink creator means toward global mean (informal James–Stein style weight).
    rows = []
    for creator, grp in base.groupby("creator"):
        n = int(len(grp))
        x = float(grp["spy_bhar"].mean())
        s2 = float(grp["spy_bhar"].var(ddof=1)) if n > 1 else 0.0
        se = (s2 / n) ** 0.5 if n > 0 else float("nan")
        shrink = n / (n + max(1.0, mu**2 + 1e-9))  # stabilizer; informal
        x_js = (1 - shrink) * mu + shrink * x
        rows.append(
            {
                "creator": creator,
                "n_events": n,
                "raw_mean_21d_spy_bhar": round(x, 6),
                "std_err_mean": round(se, 6) if se == se else "",
                "shrinkage_weight_on_raw": round(float(shrink), 4),
                "shrinkage_adjusted_mean": round(float(x_js), 6),
                "ci_note": "Do not interpret small-n creator means as skill.",
            }
        )
    out = pd.DataFrame(rows).sort_values("n_events", ascending=False)
    meta = pd.DataFrame(
        [
            {"metric": "global_mean_21d_spy_bhar", "value": round(mu, 6)},
            {"metric": "across_creator_var_of_means", "value": round(var_between, 8)},
            {"metric": "creators_tabulated", "value": len(out)},
        ]
    )
    body = (
        "## Creator skill shrinkage (diagnostic)\n\n"
        + utils.md_table(meta.to_dict("records"))
        + "\n\n"
        + utils.md_table(out.head(40).to_dict("records"), limit=40)
        + "\n\n**Warning:** shrinkage is illustration-only; it does not establish causal creator skill.\n"
    )
    return out, body


def placebo_summary(long: pd.DataFrame, manifest: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    manifest = _manifest_with_top5(manifest)
    rng = np.random.default_rng(496)
    rows_out: list[dict] = []
    for horizon in ("5D", "21D", "63D"):
        sub = long[(long["window_type"] == "forward") & (long["horizon"] == horizon) & (long["status"] == "computed")][
            ["event_id", "spy_bhar"]
        ].copy()
        sub["spy_bhar"] = pd.to_numeric(sub["spy_bhar"], errors="coerce")
        frame = manifest[["event_id", "ticker", "top5_flag", "event_date"]].merge(sub, on="event_id", how="inner").dropna(
            subset=["spy_bhar"]
        )
        frame["year"] = pd.to_datetime(frame["event_date"], errors="coerce").dt.year
        top = _safe_top(frame)
        obs = float(frame.loc[top, "spy_bhar"].mean() - frame.loc[~top, "spy_bhar"].mean())
        diffs: list[float] = []
        for _ in range(400):
            shuffled = frame.copy()
            shuffled["spy_bhar"] = rng.permutation(shuffled["spy_bhar"].values)
            tt = _safe_top(shuffled)
            diffs.append(float(shuffled.loc[tt, "spy_bhar"].mean() - shuffled.loc[~tt, "spy_bhar"].mean()))
        pct = float(np.mean(np.array(diffs) >= obs)) if diffs else float("nan")
        rows_out.append(
            {
                "placebo_type": "label_shuffle_spy_bhar_within_sample",
                "horizon_days": horizon,
                "observed_top5_minus_nontop": round(obs, 6),
                "permutation_p_upper_tail": round(pct, 4),
                "n_events": int(len(frame)),
            }
        )
        alt = frame.copy()
        alt["placebo_bhar"] = alt.groupby("year")["spy_bhar"].transform(
            lambda s: rng.choice(s.to_numpy(), size=len(s), replace=True) if len(s) else s
        )
        tt = _safe_top(alt)
        obs2 = float(alt.loc[top, "placebo_bhar"].mean() - alt.loc[~top, "placebo_bhar"].mean())
        rows_out.append(
            {
                "placebo_type": "year_stratified_random_draw_per_event",
                "horizon_days": horizon,
                "observed_top5_minus_nontop": round(obs2, 6),
                "permutation_p_upper_tail": "",
                "n_events": int(len(alt)),
            }
        )
    df = pd.DataFrame(rows_out)
    body = (
        "# Placebo / permutation diagnostics\n\n"
        "Label shuffles destroy pairing between `top5_flag` and realized returns; large observed gaps vs permutations "
        "would suggest mechanical alignment in data.\n\n"
        + utils.md_table(df.to_dict("records"))
    )
    return df, body


def extraction_audit(manifest: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    rows = []
    for col in [
        "confidence_score",
        "actionability_score",
        "recommendation_type",
        "upload_timing_bucket",
        "low_lookahead_flag",
        "duplicate_collapsed_flag",
    ]:
        if col not in manifest.columns:
            continue
        vc = manifest[col].fillna("").astype(str).value_counts().head(25)
        for val, cnt in vc.items():
            rows.append({"field": col, "value": val, "count": int(cnt)})
    dup = (
        int(manifest["duplicate_collapsed_flag"].astype(str).str.lower().eq("true").sum())
        if "duplicate_collapsed_flag" in manifest.columns
        else 0
    )
    rows.append({"field": "_summary", "value": "duplicate_collapsed_events", "count": dup})
    df = pd.DataFrame(rows)
    body = "# Recommendation extraction audit (manifest-level)\n\n" + utils.md_table(df.head(80).to_dict("records"), limit=80)
    return df, body


def write_literature() -> None:
    LIT_DOC.parent.mkdir(parents=True, exist_ok=True)
    table = """
| paper_or_stream | data_source | event_definition | return_method | controls | main finding | how_this_project_improves_or_differs | remaining_limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Barber & Odean (attention/performance); correlates | retail trading literature | buys after attention spikes | raw/calendar | limited | attention can drive flows | links influencer salience to liquid mega-caps | not YouTube-specific |
| Finfluencer working papers / preprints | social posts / surveys | post-level recommendations | mixed event windows | varies | heterogeneity common | full transcript lock + SEC/news confounds | causal skill still blocked |
| Event-study surveys (MacKinlay; Kothari-Warner) | generic | discrete events | CAR/BHAR | factor models | benchmark | uses SPY-BHAR + matched diagnostics | overlapping windows; public news gaps |
| News-confound / sentiment | news archives | text dates | event time | text + fundamentals | confounds alter inference | multi-provider + FNSPID historical slice | unknown news never “clean” |

This capstone adds conservative **news_confound_master** classification, **FNSPID** historical media coverage, and explicit **claim discipline** (no broad alpha, no uniform creator skill).
"""
    LIT_DOC.write_text("# Literature positioning\n\n" + table + "\n", encoding="utf-8")
    EXHIBITS.mkdir(parents=True, exist_ok=True)
    (EXHIBITS / "exhibit_literature_positioning.md").write_text(
        "# Exhibit — literature positioning\n\n" + table + "\n", encoding="utf-8"
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    long = utils.long_panel()
    manifest = utils.event_manifest()
    write_literature()

    cal_csv, cal_alpha, cal_md = calendar_portfolios(long, manifest)
    cal_csv.to_csv(OUT / "calendar_time_portfolio_returns.csv", index=False)
    cal_alpha.to_csv(OUT / "calendar_time_alpha_summary.csv", index=False)
    (OUT / "calendar_time_alpha_summary.md").write_text(cal_md, encoding="utf-8")

    pretrend_csv, pretrend_md = pretrend_momentum(long, manifest)
    pretrend_csv.to_csv(OUT / "pretrend_momentum_decomposition.csv", index=False)
    (OUT / "pretrend_momentum_summary.md").write_text(pretrend_md, encoding="utf-8")

    shrink_csv, shrink_md = creator_shrinkage(long, manifest)
    shrink_csv.to_csv(OUT / "creator_skill_shrinkage_summary.csv", index=False)
    (OUT / "creator_skill_shrinkage_summary.md").write_text(shrink_md, encoding="utf-8")

    placebo_csv, placebo_md = placebo_summary(long, manifest)
    placebo_csv.to_csv(OUT / "placebo_permutation_summary.csv", index=False)
    (OUT / "placebo_permutation_summary.md").write_text(placebo_md, encoding="utf-8")

    audit_csv, audit_md = extraction_audit(manifest)
    audit_csv.to_csv(OUT / "recommendation_extraction_audit.csv", index=False)
    (OUT / "recommendation_extraction_audit.md").write_text(audit_md, encoding="utf-8")

    print(f"Paper robustness pack -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
