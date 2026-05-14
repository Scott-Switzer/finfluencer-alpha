#!/usr/bin/env python3
"""Tiny capped canaries across X Apify provider actors.

Dry-run (no Apify runs): ``X_PROVIDER_CANARY_DRY_RUN=1``.

Paid calls must be executed on RunPod with a valid Apify token in ``.env``.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)
load_dotenv(ROOT / ".env", override=False)

from finfluencer_alpha.apify_key_manager import ApifyKeyManager  # noqa: E402
from finfluencer_alpha.x_apify_provider_registry import (  # noqa: E402
    CANARY_RESULTS_CSV,
    CANARY_RESULTS_MD,
    build_canary_actor_input,
    default_canary_queries,
    get_provider,
    provider_canary_passes,
    summarize_provider_canary_rows,
    window_bounds_for_canary_entry,
)
from finfluencer_alpha.x_youtube_pipeline import (  # noqa: E402
    _extract_run_cost,
    _fetch_items,
    _start_run,
    _wait_run,
)


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    return [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        w = csv.DictWriter(handle, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def main() -> None:
    dry = _truthy("X_PROVIDER_CANARY_DRY_RUN")
    max_items = int(os.getenv("X_PROVIDER_CANARY_MAX_ITEMS", "5") or 5)
    session_cap = float(os.getenv("X_PROVIDER_CANARY_SESSION_CAP_USD", "0.25") or 0.25)
    stop_on_pass = os.getenv("X_PROVIDER_CANARY_STOP_ON_PASS", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    providers = _env_list(
        "X_PROVIDER_CANARY_PROVIDERS",
        ["xquik", "scrapebadger", "scweet", "apidojo_v2"],
    )
    queries = default_canary_queries()
    session_spent = 0.0
    started = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    md_lines: list[str] = [
        "# X provider canary results",
        "",
        f"Started (UTC): `{started}`",
        f"Dry-run: **{dry}**",
        f"Session cap USD: **{session_cap}**",
        f"Max items per run: **{max_items}**",
        "",
        "## Providers",
        "",
        "```json",
        json.dumps(providers, indent=2),
        "```",
        "",
        "## Canary queries (audited CHANNEL_X handles)",
        "",
        "```json",
        json.dumps([{k: v for k, v in q.items() if k != "query"} for q in queries], indent=2),
        "```",
        "",
    ]

    csv_rows: list[dict[str, Any]] = []
    fieldnames = [
        "started_at_utc",
        "finished_at_utc",
        "provider_key",
        "actor_id",
        "canary_label",
        "dry_run",
        "session_spend_usd_after",
        "run_cost_usd",
        "run_id",
        "run_status",
        "returned_rows",
        "mock_rows",
        "non_mock_rows",
        "normalizable_rows",
        "real_id_rows",
        "created_at_parse_rows",
        "explicit_cashtag_rows",
        "inside_window_rows",
        "importable_rows",
        "same_day_today_collapse",
        "mock_dominance",
        "provider_status",
        "fail_reason",
    ]

    any_pass = False
    manager = None if dry else ApifyKeyManager.from_env()

    for i, pk in enumerate(providers):
        spec = get_provider(pk)
        if not spec.canary_enabled:
            md_lines.append(f"### `{pk}` skipped (canary_enabled=false)")
            md_lines.append("")
            continue
        q_entry = queries[i % len(queries)]
        w0, w1 = window_bounds_for_canary_entry(q_entry)
        payload = build_canary_actor_input(pk, q_entry, max_items)
        md_lines.append(f"## Provider `{pk}` (`{spec.actor_id}`)")
        md_lines.append("")
        md_lines.append(f"- Canary query label: `{q_entry['label']}`")
        md_lines.append("")
        md_lines.append("### Actor input (no secrets)")
        md_lines.append("")
        md_lines.append("```json")
        md_lines.append(json.dumps(payload, indent=2))
        md_lines.append("```")
        md_lines.append("")

        if dry:
            csv_rows.append(
                {
                    "started_at_utc": started,
                    "finished_at_utc": "",
                    "provider_key": pk,
                    "actor_id": spec.actor_id,
                    "canary_label": q_entry["label"],
                    "dry_run": "1",
                    "session_spend_usd_after": f"{session_spent:.6f}",
                    "run_cost_usd": "0",
                    "run_id": "",
                    "run_status": "DRY_RUN",
                    "returned_rows": "",
                    "mock_rows": "",
                    "non_mock_rows": "",
                    "normalizable_rows": "",
                    "real_id_rows": "",
                    "created_at_parse_rows": "",
                    "explicit_cashtag_rows": "",
                    "inside_window_rows": "",
                    "importable_rows": "",
                    "same_day_today_collapse": "",
                    "mock_dominance": "",
                    "provider_status": "SKIPPED_DRY_RUN",
                    "fail_reason": "",
                }
            )
            continue

        remaining = session_cap - session_spent
        if remaining <= 1e-9:
            md_lines.append("_Session cap reached; stopping._")
            break
        per_run = min(float(os.getenv("X_PROVIDER_CANARY_MAX_CHARGE_PER_RUN", "0.08")) or 0.08, remaining)

        assert manager is not None
        key = manager.choose_key(platform="x", projected_cost_usd=per_run)
        finished = ""
        metrics: dict[str, Any] = {}
        run_id = ""
        st = "NOT_STARTED"
        cost = 0.0
        with manager.activate_key(key):
            run = _start_run(spec.actor_id, payload, key.token, per_run)
            run_id = str(run.get("id") or "")
            status = _wait_run(
                run_id,
                key.token,
                max_wait_seconds=int(os.getenv("X_PROVIDER_CANARY_MAX_WAIT_SECONDS", "120")),
            )
            st = str(status.get("status") or "")
            cost = _extract_run_cost(status)
            items = _fetch_items(run_id, key.token) if run_id else []
            metrics = summarize_provider_canary_rows(
                items,
                actor_id=spec.actor_id,
                expected_ticker=q_entry["ticker"],
                window_start_unix=w0,
                window_end_unix=w1,
            )
        session_spent += cost
        finished = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        ok, reason = provider_canary_passes(metrics)
        if ok:
            any_pass = True
        csv_rows.append(
            {
                "started_at_utc": started,
                "finished_at_utc": finished,
                "provider_key": pk,
                "actor_id": spec.actor_id,
                "canary_label": q_entry["label"],
                "dry_run": "0",
                "session_spend_usd_after": f"{session_spent:.6f}",
                "run_cost_usd": f"{cost:.6f}",
                "run_id": run_id,
                "run_status": st,
                "returned_rows": str(metrics.get("returned_rows", "")),
                "mock_rows": str(metrics.get("mock_rows", "")),
                "non_mock_rows": str(metrics.get("non_mock_rows", "")),
                "normalizable_rows": str(metrics.get("normalizable_rows", "")),
                "real_id_rows": str(metrics.get("real_id_rows", "")),
                "created_at_parse_rows": str(metrics.get("created_at_parse_rows", "")),
                "explicit_cashtag_rows": str(metrics.get("explicit_cashtag_rows", "")),
                "inside_window_rows": str(metrics.get("inside_window_rows", "")),
                "importable_rows": str(metrics.get("importable_rows", "")),
                "same_day_today_collapse": str(metrics.get("same_day_today_collapse", "")),
                "mock_dominance": str(metrics.get("mock_dominance", "")),
                "provider_status": "PASS" if ok else "FAIL",
                "fail_reason": "" if ok else reason,
            }
        )
        md_lines.append("### Metrics (aggregated; no raw tweet text)")
        md_lines.append("")
        md_lines.append("```json")
        md_lines.append(json.dumps(metrics, indent=2))
        md_lines.append("```")
        md_lines.append("")
        md_lines.append(f"- **PASS gate:** `{'PASS' if ok else 'FAIL'}` ({reason})")
        md_lines.append("")
        if ok and stop_on_pass:
            md_lines.append("_Stop-on-pass: halting remaining providers._")
            break

    verdict = "PASS" if any_pass else "FAIL"
    md_lines.extend(
        [
            "## Overall verdict",
            "",
            f"**{verdict}** (at least one provider PASS: {any_pass})",
            "",
        ]
    )

    CANARY_RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    CANARY_RESULTS_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    _write_csv(CANARY_RESULTS_CSV, csv_rows, fieldnames=fieldnames)
    try:
        rel_md = CANARY_RESULTS_MD.relative_to(ROOT)
        rel_csv = CANARY_RESULTS_CSV.relative_to(ROOT)
    except ValueError:
        rel_md = CANARY_RESULTS_MD
        rel_csv = CANARY_RESULTS_CSV
    print(f"wrote {rel_md}")
    print(f"wrote {rel_csv}")


if __name__ == "__main__":
    main()
