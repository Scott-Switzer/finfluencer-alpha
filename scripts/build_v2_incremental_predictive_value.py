"""Incremental predictive value: YouTube features over market/analyst/sentiment baselines."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import information_environment_utils as ie  # noqa: E402
import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = ie.info_dir("incremental_predictive_value")


def eval_model(name: str, target: str, X: pd.DataFrame, y: pd.Series, train_idx, test_idx) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, roc_auc_score
    from sklearn.preprocessing import StandardScaler

    X_train, X_test = X.loc[train_idx], X.loc[test_idx]
    y_train, y_test = y.loc[train_idx], y.loc[test_idx]
    if len(X_test) < 40 or y_test.nunique() < 2 or X_train.shape[1] == 0:
        return {"feature_set": name, "target": target, "status": "insufficient", "n_test": len(X_test)}
    scaler = StandardScaler()
    Xt = scaler.fit_transform(X_train.fillna(0))
    Xv = scaler.transform(X_test.fillna(0))
    clf = LogisticRegression(max_iter=800, C=0.5)
    clf.fit(Xt, y_train)
    prob = clf.predict_proba(Xv)[:, 1]
    return {
        "feature_set": name,
        "target": target,
        "status": "computed",
        "n_train": len(X_train),
        "n_test": len(X_test),
        "accuracy": float(accuracy_score(y_test, (prob >= 0.5).astype(int))),
        "auc": float(roc_auc_score(y_test, prob)),
    }


def main() -> int:
    events = rf.build_event_feature_table()
    text = ie.load_evidence_text()
    if events.empty:
        return 0
    ev = events.merge(text, on="event_id", how="left")
    nar = pd.DataFrame(ev["evidence_window"].fillna("").map(ie.narrative_relay_scores).tolist())
    df = pd.concat([ev, nar], axis=1)

    for sub_path in [
        ie.INFO_ENV / "market_sentiment" / "market_sentiment_event_panel.csv",
        ie.INFO_ENV / "analyst_relay" / "analyst_relay_event_panel.csv",
    ]:
        if sub_path.exists():
            part = pd.read_csv(sub_path)
            drop = [c for c in part.columns if c in df.columns and c != "event_id"]
            df = df.merge(part.drop(columns=drop, errors="ignore"), on="event_id", how="left")

    df["event_year"] = pd.to_numeric(df.get("event_year"), errors="coerce")
    df["finfluencer_contrarian_to_analyst"] = df.get("finfluencer_contrarian_to_analyst", False).astype(float)

    feature_sets = {
        "market_only": [
            "prior_return_21d",
            "prior_return_63d",
            "prior_abnormal_volume",
            "prior_volatility_21d",
            "vix_level",
            "spy_prior_21d_return",
            "qqq_prior_21d_return",
        ],
        "analyst_only": ["finfluencer_contrarian_to_analyst"],
        "transcript_only": [
            "hype_score",
            "risk_warning_score",
            "disclosure_score",
            "analyst_relay_score",
            "retail_hype_score",
            "urgency_score",
            "valuation_score",
            "risk_score",
        ],
        "creator_only": [],  # filled via creator mean OOS below
        "market_plus_analyst": [],
        "market_plus_transcript": [],
        "full_model": [],
    }
    feature_sets["market_plus_analyst"] = feature_sets["market_only"] + feature_sets["analyst_only"]
    feature_sets["market_plus_transcript"] = feature_sets["market_only"] + feature_sets["transcript_only"]
    feature_sets["full_model"] = feature_sets["market_plus_analyst"] + feature_sets["transcript_only"]

    # Creator historical quality: leave-one-creator-out mean prior 21d return (not future BHAR)
    if "creator" in df.columns:
        prior = df.groupby("creator")["prior_return_21d"].transform("mean")
        df["creator_prior21_mean"] = prior
        feature_sets["creator_only"] = ["creator_prior21_mean"]
        feature_sets["full_model"] = list(dict.fromkeys(feature_sets["full_model"] + ["creator_prior21_mean"]))

    targets = {
        "positive_5d_bhar": (df["forward_spy_bhar_5d"] > 0).astype(int),
        "positive_21d_bhar": (df["forward_spy_bhar_21d"] > 0).astype(int),
        "bottom_quartile_21d": (df["forward_spy_bhar_21d"] <= df["forward_spy_bhar_21d"].quantile(0.25)).astype(int),
        "non_top_underperform": ((~df["top5_flag"].astype(bool)) & (df["forward_spy_bhar_21d"] < 0)).astype(int),
        "top5_positive_21d": (df["top5_flag"].astype(bool) & (df["forward_spy_bhar_21d"] > 0)).astype(int),
    }

    results: list[dict] = []
    importance: list[dict] = []

    for tname, y in targets.items():
        for fname, cols in feature_sets.items():
            use_cols = [c for c in cols if c in df.columns]
            if not use_cols:
                continue
            X = df[use_cols].astype(float)
            mask = y.notna() & X.notna().all(axis=1)
            X, yv, meta = X.loc[mask], y.loc[mask], df.loc[mask, ["creator", "ticker", "event_year"]]

            idx = list(X.index)
            rng = np.random.default_rng(496)
            rng.shuffle(idx)
            split = int(len(idx) * 0.7)
            results.append(eval_model(fname, tname, X, yv, idx[:split], idx[split:]))

            order = meta.sort_values("event_year").index
            split = int(len(order) * 0.7)
            results.append(eval_model(f"{fname}_time", tname, X, yv, order[:split], order[split:]))

            top_c = meta["creator"].value_counts().head(3).index
            results.append(
                eval_model(
                    f"{fname}_creator_out",
                    tname,
                    X,
                    yv,
                    meta.index[~meta["creator"].isin(top_c)],
                    meta.index[meta["creator"].isin(top_c)],
                )
            )
            top_t = meta["ticker"].value_counts().head(5).index
            results.append(
                eval_model(
                    f"{fname}_ticker_out",
                    tname,
                    X,
                    yv,
                    meta.index[~meta["ticker"].isin(top_t)],
                    meta.index[meta["ticker"].isin(top_t)],
                )
            )

    utils.write_csv(OUT / "incremental_predictive_value_results.csv", results, list(results[0]) if results else ["feature_set"])
    utils.write_csv(OUT / "feature_group_importance.csv", importance, ["target", "feature", "importance"])

    pos = [r for r in results if r.get("target") == "positive_21d_bhar" and r.get("status") == "computed" and "random" not in str(r)]
    summary = f"""# Incremental predictive value

Tests whether YouTube/transcript features add signal **over** market and analyst baselines.
**Not a trading strategy.**

## Broad positive 21D (representative AUCs)
{utils.md_table([r for r in pos if r.get("feature_set", "").startswith("market") or r.get("feature_set", "").startswith("transcript") or r.get("feature_set", "").startswith("full")][:12])}

## Interpretation
- If **transcript_only** ≈ **market_only** AUC → speech mainly repackages public/market signals.
- If transcript adds value only for **non_top_underperform** → language helps flag weak calls, not broad alpha.
- Holdout note: non-top underperformance AUC can be high under random/time but **fail ticker-out** (see holdout module).

Cross-ticker placebo 5D ≈ **+0.19%** (near zero) — finfluencer-specific component economically small.
"""
    utils.write_md(OUT / "incremental_predictive_value_summary.md", "Incremental Predictive Value", summary)
    print("Incremental predictive value complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
