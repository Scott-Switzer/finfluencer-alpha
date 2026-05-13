from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .config import EXPORTS_DIR, ensure_data_dirs
from .utils import configure_csv_field_size_limit

VALIDATION_DIR = EXPORTS_DIR / "validation"
DEFAULT_AUTO_LABEL_PATH = VALIDATION_DIR / "event_validation_sample_auto_labeled.csv"
DEFAULT_EVAL_OUTPUT_PATH = VALIDATION_DIR / "event_classifier_evaluation.csv"
DEFAULT_EVAL_MD_PATH = VALIDATION_DIR / "event_classifier_evaluation.md"


@dataclass(frozen=True)
class ClassifierEvaluationResult:
    total_rows: int
    rule_labeled: int
    llm_labeled: int
    hybrid_labeled: int
    yes_count: int
    no_count: int
    unclear_count: int
    review_needed: int
    has_human_labels: bool
    human_agreement_rate: float | None
    precision: float | None
    recall: float | None
    f1: float | None
    output_path: Path
    markdown_path: Path


def _read_csv_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    configure_csv_field_size_limit()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return [], []
        columns = list(reader.fieldnames)
        rows = [dict(row) for row in reader]
    return rows, columns


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def evaluate_event_classifier(
    input_path: Path = DEFAULT_AUTO_LABEL_PATH,
    output_path: Path = DEFAULT_EVAL_OUTPUT_PATH,
    markdown_path: Path = DEFAULT_EVAL_MD_PATH,
) -> ClassifierEvaluationResult:
    if not input_path.exists():
        raise FileNotFoundError(f"Auto-labeled input not found: {input_path}")

    ensure_data_dirs()
    rows, _ = _read_csv_rows(input_path)
    total = len(rows)

    methods = Counter(_clean(row.get("auto_label_method")).lower() for row in rows)
    labels = Counter(_clean(row.get("is_true_recommendation")).lower() for row in rows)
    review_needed = sum(
        1 for row in rows if _clean(row.get("auto_label_needs_review")).lower() == "yes"
    )

    has_human = any(_clean(row.get("labeler_notes")) for row in rows)
    human_agreement = None
    precision = None
    recall = None
    f1 = None

    if has_human:
        tp = fp = tn = fn = 0
        for row in rows:
            human = _clean(row.get("labeler_notes")).lower()
            auto = _clean(row.get("is_true_recommendation")).lower()
            if not human or not auto:
                continue
            if auto == "yes":
                if human == "yes":
                    tp += 1
                else:
                    fp += 1
            else:
                if human == "no":
                    tn += 1
                else:
                    fn += 1
        precision = round(tp / (tp + fp), 3) if (tp + fp) > 0 else None
        recall = round(tp / (tp + fn), 3) if (tp + fn) > 0 else None
        if precision is not None and recall is not None and (precision + recall) > 0:
            f1 = round(2 * precision * recall / (precision + recall), 3)
        total_human = tp + fp + tn + fn
        human_agreement = round((tp + tn) / total_human, 3) if total_human > 0 else None

    summary_rows = [
        {
            "metric": "total_rows",
            "value": total,
        },
        {
            "metric": "rule_labeled",
            "value": methods.get("rules", 0),
        },
        {
            "metric": "llm_labeled",
            "value": methods.get("llm", 0) + methods.get("hybrid_llm", 0),
        },
        {
            "metric": "hybrid_labeled",
            "value": methods.get("hybrid", 0),
        },
        {
            "metric": "yes",
            "value": labels.get("yes", 0),
        },
        {
            "metric": "no",
            "value": labels.get("no", 0),
        },
        {
            "metric": "unclear",
            "value": labels.get("unclear", 0),
        },
        {
            "metric": "review_needed",
            "value": review_needed,
        },
        {
            "metric": "has_human_labels",
            "value": "yes" if has_human else "no",
        },
        {
            "metric": "human_agreement_rate",
            "value": human_agreement if human_agreement is not None else "N/A",
        },
        {
            "metric": "precision",
            "value": precision if precision is not None else "N/A",
        },
        {
            "metric": "recall",
            "value": recall if recall is not None else "N/A",
        },
        {
            "metric": "f1",
            "value": f1 if f1 is not None else "N/A",
        },
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(summary_rows)

    lines = [
        "# Event Classifier Evaluation",
        "",
        f"Source: {input_path.name}",
        "",
        "## Label Distribution",
        "",
        f"- Total rows: {total}",
        f"- Rules-based: {methods.get('rules', 0)}",
        f"- LLM-based: {methods.get('llm', 0) + methods.get('hybrid_llm', 0)}",
        f"- Hybrid: {methods.get('hybrid', 0)}",
        "",
        "## Auto-Label Outcomes",
        "",
        f"- Yes (true recommendation): {labels.get('yes', 0)}",
        f"- No (false positive): {labels.get('no', 0)}",
        f"- Unclear: {labels.get('unclear', 0)}",
        f"- Review needed: {review_needed}",
        "",
        "## Human Label Comparison",
        "",
        f"- Human labels present: {'yes' if has_human else 'no'}",
    ]
    if has_human:
        lines.extend([
            f"- Agreement rate: {human_agreement}",
            f"- Precision: {precision}",
            f"- Recall: {recall}",
            f"- F1: {f1}",
        ])
    else:
        lines.extend([
            "- No human labels found. Current labels are rule-generated pseudo-labels.",
            "- To train/evaluate a classifier, populate labeler_notes with ground-truth labels.",
        ])
    lines.append("")

    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(lines), encoding="utf-8")

    return ClassifierEvaluationResult(
        total_rows=total,
        rule_labeled=methods.get("rules", 0),
        llm_labeled=methods.get("llm", 0) + methods.get("hybrid_llm", 0),
        hybrid_labeled=methods.get("hybrid", 0),
        yes_count=labels.get("yes", 0),
        no_count=labels.get("no", 0),
        unclear_count=labels.get("unclear", 0),
        review_needed=review_needed,
        has_human_labels=has_human,
        human_agreement_rate=human_agreement,
        precision=precision,
        recall=recall,
        f1=f1,
        output_path=output_path,
        markdown_path=markdown_path,
    )
