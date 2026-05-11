from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import EXPORTS_DIR, SEEDS_DIR, ensure_data_dirs
from .utils import configure_csv_field_size_limit

X_EXTENSION_EXPORT_DIR = EXPORTS_DIR / "x_extension"
DEFAULT_X_CREATOR_CANDIDATES_PATH = SEEDS_DIR / "x_creator_candidates.csv"
DEFAULT_CREATOR_TAXONOMY_SEED_PATH = SEEDS_DIR / "creator_taxonomy_seed.csv"
DEFAULT_X_COST_PLAN_CSV_PATH = X_EXTENSION_EXPORT_DIR / "x_extension_cost_plan.csv"
DEFAULT_X_COST_PLAN_MD_PATH = X_EXTENSION_EXPORT_DIR / "x_extension_cost_plan.md"
DEFAULT_X_CANDIDATE_QUERIES_PATH = X_EXTENSION_EXPORT_DIR / "x_candidate_queries.csv"

X_COST_PER_POST_READ = 0.005

X_CREATOR_CANDIDATES_COLUMNS = ["handle", "display_name", "category", "priority", "notes"]
X_COST_PLAN_COLUMNS = [
    "handle",
    "display_name",
    "category",
    "priority",
    "estimated_post_reads",
    "estimated_cost_usd",
    "included_in_10_usd",
    "included_in_25_usd",
    "included_in_50_usd",
]
X_CANDIDATE_QUERIES_COLUMNS = [
    "handle",
    "priority",
    "query_template",
    "estimated_post_reads",
    "estimated_cost_usd",
]


@dataclass(frozen=True)
class XExtensionCostPlanResult:
    cost_plan_csv_path: Path
    cost_plan_md_path: Path
    candidate_queries_csv_path: Path
    candidate_seed_path: Path
    creator_count: int
    total_estimated_reads: int
    total_estimated_cost_usd: float


def _clean(value: object) -> str:
    return str(value or "").strip()


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    configure_csv_field_size_limit()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _priority_rank(priority: str) -> int:
    normalized = _clean(priority).lower()
    if normalized == "high":
        return 0
    if normalized == "medium":
        return 1
    if normalized == "low":
        return 2
    return 3


def _reads_for_priority(priority: str) -> int:
    normalized = _clean(priority).lower()
    if normalized == "high":
        return 2000
    if normalized == "medium":
        return 1000
    if normalized == "low":
        return 500
    return 750


def _seed_rows_from_verified_taxonomy(path: Path) -> list[dict[str, str]]:
    rows = _read_csv(path)
    x_rows = [row for row in rows if _clean(row.get("platform")).lower() == "x" and _clean(row.get("handle"))]
    if not x_rows:
        return []
    seed_rows: list[dict[str, str]] = []
    for index, row in enumerate(x_rows, start=1):
        seed_rows.append(
            {
                "handle": _clean(row.get("handle")),
                "display_name": _clean(row.get("handle")),
                "category": _clean(row.get("initial_category")) or "unknown",
                "priority": "high" if index <= 5 else "medium",
                "notes": "Imported from existing creator taxonomy seed",
            }
        )
    return seed_rows


def ensure_x_creator_candidates_seed(
    *,
    seed_path: Path = DEFAULT_X_CREATOR_CANDIDATES_PATH,
    creator_taxonomy_seed_path: Path = DEFAULT_CREATOR_TAXONOMY_SEED_PATH,
) -> Path:
    if seed_path.exists():
        return seed_path
    ensure_data_dirs()
    seed_rows = _seed_rows_from_verified_taxonomy(creator_taxonomy_seed_path)
    if not seed_rows:
        seed_rows = [
            {
                "handle": "",
                "display_name": "replace_with_verified_handle",
                "category": "unknown",
                "priority": "high",
                "notes": "Placeholder row because no verified X handles were found locally.",
            }
        ]
    _write_csv(seed_path, seed_rows, X_CREATOR_CANDIDATES_COLUMNS)
    return seed_path


def _query_template(handle: str) -> str:
    return (
        f"from:{handle} "
        "($AAPL OR $TSLA OR $NVDA OR $AMD OR $AMZN OR $META OR $MSFT OR $GOOGL) "
        "-is:retweet lang:en"
    )


def _budget_cap_reads(budget_usd: float) -> int:
    return int(budget_usd / X_COST_PER_POST_READ)


def build_x_extension_cost_plan(
    *,
    candidate_seed_path: Path = DEFAULT_X_CREATOR_CANDIDATES_PATH,
    creator_taxonomy_seed_path: Path = DEFAULT_CREATOR_TAXONOMY_SEED_PATH,
    output_cost_plan_csv_path: Path = DEFAULT_X_COST_PLAN_CSV_PATH,
    output_cost_plan_md_path: Path = DEFAULT_X_COST_PLAN_MD_PATH,
    output_candidate_queries_csv_path: Path = DEFAULT_X_CANDIDATE_QUERIES_PATH,
) -> XExtensionCostPlanResult:
    ensure_data_dirs()
    seed_path = ensure_x_creator_candidates_seed(
        seed_path=candidate_seed_path,
        creator_taxonomy_seed_path=creator_taxonomy_seed_path,
    )
    seed_rows = _read_csv(seed_path)
    valid_rows = [row for row in seed_rows if _clean(row.get("handle"))]
    sorted_rows = sorted(
        valid_rows,
        key=lambda row: (_priority_rank(_clean(row.get("priority"))), _clean(row.get("handle")).lower()),
    )

    remaining_10 = _budget_cap_reads(10.0)
    remaining_25 = _budget_cap_reads(25.0)
    remaining_50 = _budget_cap_reads(50.0)

    cost_rows: list[dict[str, Any]] = []
    query_rows: list[dict[str, Any]] = []
    total_reads = 0
    total_cost = 0.0
    for row in sorted_rows:
        handle = _clean(row.get("handle"))
        priority = _clean(row.get("priority")) or "medium"
        estimated_reads = _reads_for_priority(priority)
        estimated_cost = estimated_reads * X_COST_PER_POST_READ
        include_10 = estimated_reads <= remaining_10
        include_25 = estimated_reads <= remaining_25
        include_50 = estimated_reads <= remaining_50
        if include_10:
            remaining_10 -= estimated_reads
        if include_25:
            remaining_25 -= estimated_reads
        if include_50:
            remaining_50 -= estimated_reads

        cost_rows.append(
            {
                "handle": handle,
                "display_name": _clean(row.get("display_name")) or handle,
                "category": _clean(row.get("category")) or "unknown",
                "priority": priority,
                "estimated_post_reads": estimated_reads,
                "estimated_cost_usd": f"{estimated_cost:.2f}",
                "included_in_10_usd": include_10,
                "included_in_25_usd": include_25,
                "included_in_50_usd": include_50,
            }
        )
        query_rows.append(
            {
                "handle": handle,
                "priority": priority,
                "query_template": _query_template(handle),
                "estimated_post_reads": estimated_reads,
                "estimated_cost_usd": f"{estimated_cost:.2f}",
            }
        )
        total_reads += estimated_reads
        total_cost += estimated_cost

    _write_csv(output_cost_plan_csv_path, cost_rows, X_COST_PLAN_COLUMNS)
    _write_csv(output_candidate_queries_csv_path, query_rows, X_CANDIDATE_QUERIES_COLUMNS)

    included_10_count = sum(1 for row in cost_rows if row["included_in_10_usd"])
    included_10_reads = sum(int(row["estimated_post_reads"]) for row in cost_rows if row["included_in_10_usd"])
    included_10_cost = included_10_reads * X_COST_PER_POST_READ

    included_25_count = sum(1 for row in cost_rows if row["included_in_25_usd"])
    included_25_reads = sum(int(row["estimated_post_reads"]) for row in cost_rows if row["included_in_25_usd"])
    included_25_cost = included_25_reads * X_COST_PER_POST_READ

    included_50_count = sum(1 for row in cost_rows if row["included_in_50_usd"])
    included_50_reads = sum(int(row["estimated_post_reads"]) for row in cost_rows if row["included_in_50_usd"])
    included_50_cost = included_50_reads * X_COST_PER_POST_READ

    lines = [
        "# X Extension Cost Plan (No API Calls)",
        "",
        f"- Candidate seed: `{seed_path}`",
        f"- Candidate handles with estimates: {len(cost_rows)}",
        "",
        "## Pilot Budget Scenarios",
        "",
        f"- **$10 pilot**: up to {_budget_cap_reads(10.0)} reads max, fits {included_10_count} creators ({included_10_reads} reads, ${included_10_cost:.2f})",
        f"- **$25 pilot**: up to {_budget_cap_reads(25.0)} reads max, fits {included_25_count} creators ({included_25_reads} reads, ${included_25_cost:.2f})",
        f"- **$50 pilot**: up to {_budget_cap_reads(50.0)} reads max, fits {included_50_count} creators ({included_50_reads} reads, ${included_50_cost:.2f})",
        "",
        "## Full Sample Estimate (all candidates)",
        "",
        f"- Total estimated post reads: {total_reads}",
        f"- Total estimated cost (@ $0.005/read): ${total_cost:.2f}",
        "",
        "Recommended approach: run X as a small extension pilot and keep YouTube as the core analysis platform.",
    ]
    output_cost_plan_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_cost_plan_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return XExtensionCostPlanResult(
        cost_plan_csv_path=output_cost_plan_csv_path,
        cost_plan_md_path=output_cost_plan_md_path,
        candidate_queries_csv_path=output_candidate_queries_csv_path,
        candidate_seed_path=seed_path,
        creator_count=len(cost_rows),
        total_estimated_reads=total_reads,
        total_estimated_cost_usd=total_cost,
    )
