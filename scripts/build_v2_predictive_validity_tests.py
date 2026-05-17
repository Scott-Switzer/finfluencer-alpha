"""Out-of-sample predictive validity (mechanism/falsification; not tradability)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = rf.frontier_dir("predictive_validity")


def main() -> int:
    events = rf.build_event_feature_table()
    text = rf.load_evidence_text()
    if events.empty:
        return 0
    events = events.merge(text, on="event_id", how="left")
    score_df = pd.DataFrame(events["evidence_window"].fillna("").map(rf.language_scores).tolist())
    df = pd.concat([events, score_df], axis=1)
    df["event_year"] = pd.to_numeric(df["event_year"], errors="coerce")
    df = df.sort_values("event_year")

    feature_cols = [
        "top5_flag",
        "prior_return_21d",
        "prior_return_63d",
        "prior_abnormal_volume",
        "prior_volatility_21d",
        "high_confidence",
        "hype_score",
        "risk_warning_score",
        "disclosure_score",
    ]
    targets = {
        "positive_5d": (df["forward_spy_bhar_5d"] > 0).astype(int),
        "positive_21d": (df["forward_spy_bhar_21d"] > 0).astype(int),
        "bottom_quartile_21d": (df["forward_spy_bhar_21d"] <= df["forward_spy_bhar_21d"].quantile(0.25)).astype(int),
        "non_top_underperform": ((~df["top5_flag"]) & (df["forward_spy_bhar_21d"] < 0)).astype(int),
    }

    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, roc_auc_score
        from sklearn.preprocessing import StandardScaler

        sklearn_ok = True
    except ImportError:
        sklearn_ok = False

    results: list[dict] = []
    importance_rows: list[dict] = []

    for target_name, y in targets.items():
        X = df[feature_cols].copy()
        X["top5_flag"] = X["top5_flag"].astype(float)
        X["high_confidence"] = X["high_confidence"].astype(float)
        mask = y.notna() & X.notna().all(axis=1)
        X, y = X.loc[mask], y.loc[mask]
        if len(X) < 120:
            results.append({"target": target_name, "model": "all", "status": "insufficient_n", "n": len(X)})
            continue
        split = int(len(X) * 0.7)
        X_train, X_test = X.iloc[:split], X.iloc[split:]
        y_train, y_test = y.iloc[:split], y.iloc[split:]
        majority = float(max(y_train.mean(), 1 - y_train.mean()))
        results.append(
            {
                "target": target_name,
                "model": "majority_baseline",
                "status": "computed",
                "n_train": len(X_train),
                "n_test": len(X_test),
                "accuracy": accuracy_score(y_test, [int(y_train.mean() >= 0.5)] * len(y_test)) if sklearn_ok else majority,
                "auc": None,
            }
        )
        if not sklearn_ok:
            continue
        scaler = StandardScaler()
        Xt = scaler.fit_transform(X_train)
        Xv = scaler.transform(X_test)
        logit = LogisticRegression(max_iter=500, C=1.0)
        logit.fit(Xt, y_train)
        prob = logit.predict_proba(Xv)[:, 1]
        results.append(
            {
                "target": target_name,
                "model": "logistic_time_split",
                "status": "computed",
                "n_train": len(X_train),
                "n_test": len(X_test),
                "accuracy": accuracy_score(y_test, (prob >= 0.5).astype(int)),
                "auc": roc_auc_score(y_test, prob) if y_test.nunique() > 1 else None,
            }
        )
        rf_clf = RandomForestClassifier(n_estimators=200, max_depth=4, random_state=496)
        rf_clf.fit(X_train, y_train)
        prob_rf = rf_clf.predict_proba(X_test)[:, 1]
        results.append(
            {
                "target": target_name,
                "model": "random_forest_time_split",
                "status": "computed",
                "n_train": len(X_train),
                "n_test": len(X_test),
                "accuracy": accuracy_score(y_test, (prob_rf >= 0.5).astype(int)),
                "auc": roc_auc_score(y_test, prob_rf) if y_test.nunique() > 1 else None,
            }
        )
        for feat, imp in zip(feature_cols, rf_clf.feature_importances_, strict=True):
            importance_rows.append({"target": target_name, "feature": feat, "importance": float(imp)})

    utils.write_csv(OUT / "predictive_validity_results.csv", results, list(results[0]) if results else ["target"])
    utils.write_csv(
        OUT / "predictive_validity_feature_importance.csv",
        importance_rows,
        ["target", "feature", "importance"] if importance_rows else ["target"],
    )

    summary = """# Predictive validity (out-of-sample)

Time-ordered 70/30 split. **Not** a trading strategy backtest.

## Interpretation
- If broad positive-return targets are unpredictable, outcomes are **not** easily exploitable.
- If **non_top_underperform** is more predictable than broad alpha, that supports the paper's stronger heterogeneity claim.
- Creator-out and ticker-out holdouts remain a gap (future work).

Models: majority baseline, logistic regression, random forest (when sklearn available).
"""
    utils.write_md(OUT / "predictive_validity_summary.md", "Predictive Validity", summary)
    print("Predictive validity tests complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
