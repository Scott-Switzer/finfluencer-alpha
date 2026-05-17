"""Creator-out, ticker-out, year-out predictive holdouts."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = rf.frontier_dir("predictive_validity_holdouts")


def eval_split(name: str, target: str, X: pd.DataFrame, y: pd.Series, train_idx, test_idx) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, roc_auc_score
    from sklearn.preprocessing import StandardScaler

    X_train, X_test = X.loc[train_idx], X.loc[test_idx]
    y_train, y_test = y.loc[train_idx], y.loc[test_idx]
    if len(X_test) < 30 or y_test.nunique() < 2:
        return {"split": name, "target": target, "model": "logistic", "status": "insufficient_test", "n_test": len(X_test)}
    scaler = StandardScaler()
    Xt = scaler.fit_transform(X_train)
    Xv = scaler.transform(X_test)
    clf = LogisticRegression(max_iter=500)
    clf.fit(Xt, y_train)
    prob = clf.predict_proba(Xv)[:, 1]
    return {
        "split": name,
        "target": target,
        "model": "logistic",
        "status": "computed",
        "n_train": len(X_train),
        "n_test": len(X_test),
        "accuracy": float(accuracy_score(y_test, (prob >= 0.5).astype(int))),
        "auc": float(roc_auc_score(y_test, prob)),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    events = rf.build_event_feature_table()
    text = rf.load_evidence_text()
    if events.empty:
        return 0
    events = events.merge(text, on="event_id", how="left")
    score_df = pd.DataFrame(events["evidence_window"].fillna("").map(rf.language_scores).tolist())
    df = pd.concat([events, score_df], axis=1)
    df["event_year"] = pd.to_numeric(df["event_year"], errors="coerce")

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
        "non_top_underperform": ((~df["top5_flag"].astype(bool)) & (df["forward_spy_bhar_21d"] < 0)).astype(int),
    }

    results: list[dict] = []
    importance: list[dict] = []

    for tname, y in targets.items():
        X = df[feature_cols].copy()
        X["top5_flag"] = X["top5_flag"].astype(float)
        X["high_confidence"] = X["high_confidence"].astype(float)
        mask = y.notna() & X.notna().all(axis=1)
        X, y, meta = X.loc[mask], y.loc[mask], df.loc[mask, ["creator", "ticker", "event_year"]]

        # random 70/30
        idx = list(X.index)
        rng = np.random.default_rng(496)
        rng.shuffle(idx)
        split = int(len(idx) * 0.7)
        results.append(eval_split("random_70_30", tname, X, y, idx[:split], idx[split:]))

        # time
        order = meta.sort_values("event_year").index
        split = int(len(order) * 0.7)
        results.append(eval_split("time_ordered", tname, X, y, order[:split], order[split:]))

        # creator-out: hold out creators with most events
        top_creators = meta["creator"].value_counts().head(3).index.tolist()
        test_idx = meta.index[meta["creator"].isin(top_creators)]
        train_idx = meta.index[~meta["creator"].isin(top_creators)]
        results.append(eval_split("creator_out_top3", tname, X, y, train_idx, test_idx))

        # ticker-out: hold out most common tickers
        top_tickers = meta["ticker"].value_counts().head(5).index.tolist()
        test_idx = meta.index[meta["ticker"].isin(top_tickers)]
        train_idx = meta.index[~meta["ticker"].isin(top_tickers)]
        results.append(eval_split("ticker_out_top5", tname, X, y, train_idx, test_idx))

        # year-out: hold out latest year
        latest = meta["event_year"].max()
        test_idx = meta.index[meta["event_year"] == latest]
        train_idx = meta.index[meta["event_year"] != latest]
        results.append(eval_split("year_out_latest", tname, X, y, train_idx, test_idx))

        from sklearn.ensemble import RandomForestClassifier

        rf_fit = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=496)
        rf_fit.fit(X, y)
        for feat, imp in zip(feature_cols, rf_fit.feature_importances_, strict=True):
            importance.append({"target": tname, "feature": feat, "importance": float(imp), "split": "full_sample_rf"})

    utils.write_csv(OUT / "holdout_predictive_validity_results.csv", results, list(results[0]) if results else ["split"])
    utils.write_csv(OUT / "feature_importance_holdouts.csv", importance, ["target", "feature", "importance", "split"])

    nt = [r for r in results if r.get("target") == "non_top_underperform" and r.get("status") == "computed"]
    summary = "# Holdout predictive validity\n\n" + utils.md_table(nt) + """

## Interpretation
- If **non_top_underperform** AUC collapses under **ticker_out**, the pattern is **ticker/salience-driven**, not a portable cross-sectional rule.
- High AUC under random/time split but failure under ticker-out → do **not** claim tradable non-top shorts.
"""
    utils.write_md(OUT / "holdout_predictive_validity_summary.md", "Holdout Predictive Validity", summary)
    print("Holdout predictive validity complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
