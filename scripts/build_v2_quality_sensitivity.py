from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
QUALITY_DIR = OUT_DIR / "quality_sensitivity"
QUALITY_DIR.mkdir(parents=True, exist_ok=True)


def stats_row(name: str, events: list[base.EventRecord], notes: str = "") -> dict[str, str]:
    return base.spec_row(name, events, notes)


def main() -> int:
    events = base.fetch_events(base.load_market_data())
    actionability_thresholds = [2.0, 2.5, 3.0, 3.5, 4.0]
    threshold_rows = []
    for threshold in actionability_thresholds:
        selected = [
            event
            for event in events
            if event.actionability_score is not None and event.actionability_score >= threshold
        ]
        threshold_rows.append(stats_row(f"actionability_score>={threshold}", selected))
    base.write_csv(QUALITY_DIR / "01_quality_threshold_sensitivity.csv", threshold_rows, list(threshold_rows[0]))
    base.write_md(
        QUALITY_DIR / "01_quality_threshold_sensitivity.md",
        "# V2 Quality Threshold Sensitivity\n\n"
        + base.markdown_table(threshold_rows, list(threshold_rows[0])),
    )
    type_rows = [
        stats_row("buy", [event for event in events if event.recommendation_type == "buy"]),
        stats_row("sell", [event for event in events if event.recommendation_type == "sell"]),
        stats_row(
            "high_confidence_label",
            [event for event in events if "high" in (event.confidence_label or "").lower()],
            "confidence_label contains high",
        ),
        stats_row(
            "confidence_score>=0.75",
            [event for event in events if event.confidence_score is not None and event.confidence_score >= 0.75],
        ),
    ]
    base.write_csv(QUALITY_DIR / "02_recommendation_type_sensitivity.csv", type_rows, list(type_rows[0]))
    base.write_md(
        QUALITY_DIR / "02_recommendation_type_sensitivity.md",
        "# V2 Recommendation Type Sensitivity\n\n" + base.markdown_table(type_rows, list(type_rows[0])),
    )
    first_ids = {event.event_id for event in base.first_per_cluster(events)}
    interaction_rows = []
    for threshold in [2.5, 3.0, 3.5]:
        high = [
            event
            for event in events
            if event.actionability_score is not None and event.actionability_score >= threshold
        ]
        interaction_rows.append(stats_row(f"quality>={threshold}_all", high))
        interaction_rows.append(
            stats_row(
                f"quality>={threshold}_duplicate_collapsed",
                [event for event in high if event.event_id in first_ids],
            )
        )
        interaction_rows.append(
            stats_row(
                f"quality>={threshold}_top5",
                [event for event in high if event.ticker in base.TOP5_TICKERS],
            )
        )
        interaction_rows.append(
            stats_row(
                f"quality>={threshold}_non_top",
                [event for event in high if event.ticker not in base.TOP5_TICKERS],
            )
        )
    base.write_csv(
        QUALITY_DIR / "03_duplicate_and_quality_interaction.csv",
        interaction_rows,
        list(interaction_rows[0]),
    )
    base.write_md(
        QUALITY_DIR / "03_duplicate_and_quality_interaction.md",
        "# V2 Duplicate and Quality Interaction\n\n"
        + base.markdown_table(interaction_rows, list(interaction_rows[0])),
    )
    scores = pd.Series([event.actionability_score for event in events if event.actionability_score is not None])
    memo = f"""# V2 Quality Sensitivity Memo

The live DB has actionability and confidence proxy fields, but no human-audited
quality score for every v2 event. Actionability score is stored on a low
integer-like proxy scale in the live DB, so this audit uses proxy thresholds
from 2.0 through 4.0 rather than 0-100 score cutoffs.

- Events with non-null actionability score: `{len(scores)}`
- Mean actionability score: `{scores.mean():.2f}`
- Median actionability score: `{scores.median():.2f}`

Quality splits should be interpreted as extraction-sensitivity checks, not proof
that high-quality recommendations cause returns.
"""
    base.write_md(QUALITY_DIR / "04_quality_sensitivity_memo.md", memo)
    print("V2 quality sensitivity complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
