"""Validate future manual Bloomberg CSV exports.

This script never calls Bloomberg APIs. It only checks manually saved CSV files
under data/imports/bloomberg/manual_csv/ and writes paper-package status docs.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BLOOMBERG_DIR = REPO_ROOT / "data" / "imports" / "bloomberg" / "manual_csv"
OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package"


@dataclass(frozen=True)
class BloombergSpec:
    filename: str
    label: str
    required_fields: tuple[str, ...]


SPECS = [
    BloombergSpec(
        "bloomberg_price_template.csv",
        "Price / total return panel",
        (
            "event_id",
            "ticker",
            "bloomberg_ticker",
            "date",
            "adjusted_close_or_total_return_index",
            "px_last",
            "volume",
            "market_cap",
            "beta",
            "gics_sector",
            "gics_industry",
            "benchmark_spy_return",
            "benchmark_qqq_return",
            "sector_etf_return",
        ),
    ),
    BloombergSpec(
        "bloomberg_news_template.csv",
        "Company news headlines",
        (
            "event_id",
            "ticker",
            "bloomberg_ticker",
            "event_date",
            "headline_timestamp",
            "headline",
            "source",
            "news_category",
            "relevance_score_if_available",
        ),
    ),
    BloombergSpec(
        "bloomberg_corporate_actions_template.csv",
        "Corporate actions",
        (
            "ticker",
            "bloomberg_ticker",
            "action_date",
            "action_type",
            "description",
        ),
    ),
    BloombergSpec(
        "bloomberg_earnings_template.csv",
        "Earnings",
        (
            "ticker",
            "bloomberg_ticker",
            "earnings_announcement_datetime",
            "fiscal_period",
            "eps_actual",
            "eps_estimate",
            "revenue_actual",
            "revenue_estimate",
        ),
    ),
    BloombergSpec(
        "bloomberg_analyst_actions_template.csv",
        "Analyst actions",
        (
            "ticker",
            "bloomberg_ticker",
            "action_datetime",
            "broker",
            "action_type",
            "old_rating",
            "new_rating",
            "old_target",
            "new_target",
        ),
    ),
]


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ensure_templates() -> None:
    BLOOMBERG_DIR.mkdir(parents=True, exist_ok=True)
    readme = """# Manual Bloomberg CSV Drop Zone

Save manually pulled Bloomberg Terminal / Excel / BQuant exports here using the
template filenames below. These files are input templates and validation
scaffolding only; do not commit raw Bloomberg exports containing licensed data.

The current empirical package does not depend on Bloomberg. Bloomberg is a
future validation layer that can replace yfinance-derived results after manual
CSV files are available and validated.
"""
    write_md(BLOOMBERG_DIR / "README.md", readme)
    for spec in SPECS:
        path = BLOOMBERG_DIR / spec.filename
        if not path.exists():
            write_csv(path, [], list(spec.required_fields))


def validate_file(spec: BloombergSpec) -> dict[str, Any]:
    path = BLOOMBERG_DIR / spec.filename
    if not path.exists():
        return {
            "file": spec.filename,
            "label": spec.label,
            "exists": False,
            "row_count": 0,
            "schema_valid": False,
            "missing_fields": ";".join(spec.required_fields),
            "extra_fields": "",
            "status": "missing_template",
        }
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
    missing = [field for field in spec.required_fields if field not in fields]
    extra = [field for field in fields if field not in spec.required_fields]
    data_rows = [
        row
        for row in rows
        if any((value or "").strip() for value in row.values())
    ]
    schema_valid = not missing
    if not schema_valid:
        status = "schema_invalid"
    elif data_rows:
        status = "manual_data_present_not_applied"
    else:
        status = "template_only"
    return {
        "file": spec.filename,
        "label": spec.label,
        "exists": True,
        "row_count": len(data_rows),
        "schema_valid": schema_valid,
        "missing_fields": ";".join(missing),
        "extra_fields": ";".join(extra),
        "status": status,
    }


def write_status_outputs(rows: list[dict[str, Any]]) -> None:
    columns = [
        "file",
        "label",
        "exists",
        "row_count",
        "schema_valid",
        "missing_fields",
        "extra_fields",
        "status",
    ]
    write_csv(OUT_DIR / "07_bloomberg_csv_ingestion_status.csv", rows, columns)

    table = [
        "# Bloomberg CSV Ingestion Status",
        "",
        "No Bloomberg API was used. This validation checks only manual CSV templates/exports.",
        "",
        "| File | Exists | Rows | Schema valid | Status |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        table.append(
            f"| `{row['file']}` | {row['exists']} | {row['row_count']} | "
            f"{row['schema_valid']} | {row['status']} |"
        )
    table += [
        "",
        "Current yfinance/free-data results are not overwritten by these files.",
        "If manual Bloomberg CSVs are later populated, rerun this validator first,",
        "then explicitly rerun the empirical package with a Bloomberg-source option.",
        "",
    ]
    write_md(OUT_DIR / "07_bloomberg_csv_ingestion_status.md", "\n".join(table))

    instructions = """# Bloomberg Manual Pull Instructions

Bloomberg is a future validation layer, not a dependency for the current build.
At school, manually export CSVs for the locked event IDs and save them under:

`data/imports/bloomberg/manual_csv/`

Use the template filenames exactly. Do not commit raw Bloomberg data. After
pulling files, run:

```bash
python3 scripts/validate_bloomberg_csv_imports.py
```

Then review `07_bloomberg_csv_ingestion_status.md`. Only after schema and
coverage are acceptable should the analysis be rerun with Bloomberg as an
explicit source.
"""
    write_md(OUT_DIR / "07_bloomberg_manual_pull_instructions.md", instructions)

    checklist = [
        "# Bloomberg Required Fields Checklist",
        "",
        "| File | Required fields |",
        "| --- | --- |",
    ]
    for spec in SPECS:
        checklist.append(f"| `{spec.filename}` | `{', '.join(spec.required_fields)}` |")
    checklist += [
        "",
        "These fields support later replacement of yfinance prices, SEC-only news",
        "flags, free metadata checks, and provisional calendar-time portfolio results.",
        "",
    ]
    write_md(OUT_DIR / "07_bloomberg_required_fields_checklist.md", "\n".join(checklist))


def main() -> int:
    ensure_templates()
    rows = [validate_file(spec) for spec in SPECS]
    write_status_outputs(rows)
    invalid = [row for row in rows if not row["schema_valid"]]
    print(f"Validated Bloomberg CSV templates/exports: {len(rows)} files")
    print(f"Manual Bloomberg data rows present: {sum(int(row['row_count']) for row in rows)}")
    if invalid:
        print(f"Schema issues: {len(invalid)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
