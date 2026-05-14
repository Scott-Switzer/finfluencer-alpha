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
    SAMPLE_KIND_BROAD_PROBE,
    SAMPLE_KIND_EXPLORATORY,
    SAMPLE_KIND_RESEARCH_STRICT,
    SAMPLE_KIND_SANITY,
    SCHEMA_SANITY_CANARY,
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

_DEFAULT_TINY_PROVIDERS = ["apidojo_lite", "scweet"]


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
        w = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def _sample_kind_for_query_variant(query_variant: str, *, canary_unlocks_overnight: bool) -> str:
    if query_variant == "broad":
        return SAMPLE_KIND_BROAD_PROBE
    if not canary_unlocks_overnight:
        return SAMPLE_KIND_EXPLORATORY
    return SAMPLE_KIND_RESEARCH_STRICT


def _csv_row_base(
    *,
    started: str,
    session_spent: float,
    provider_key: str,
    actor_id: str,
    canary_label: str,
    dry: bool,
    query_variant: str,
    sample_kind: str,
) -> dict[str, Any]:
    return {
        "started_at_utc": started,
        "finished_at_utc": "",
        "provider_key": provider_key,
        "actor_id": actor_id,
        "canary_label": canary_label,
        "query_variant": query_variant,
        "sample_kind": sample_kind,
        "dry_run": "1" if dry else "0",
        "session_spend_usd_after": f"{session_spent:.6f}",
        "run_cost_usd": "0",
        "run_id": "",
        "run_status": "DRY_RUN" if dry else "NOT_STARTED",
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
        "provider_status": "SKIPPED_DRY_RUN" if dry else "FAIL",
        "fail_reason": "",
    }


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
    providers = _env_list("X_PROVIDER_CANARY_PROVIDERS", _DEFAULT_TINY_PROVIDERS)
    query_mode = os.getenv("X_PROVIDER_CANARY_QUERY_MODE", "strict").strip().lower()
    if query_mode not in {"strict", "broad", "both"}:
        query_mode = "strict"
    include_sanity = _truthy("X_PROVIDER_CANARY_INCLUDE_SANITY_QUERY")
    sanity_pk = os.getenv("X_PROVIDER_CANARY_SANITY_PROVIDER", "apidojo_lite").strip() or "apidojo_lite"

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
        f"``X_PROVIDER_CANARY_QUERY_MODE``: **{query_mode}**",
        f"Sanity query enabled: **{include_sanity}**",
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
        "query_variant",
        "sample_kind",
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

    research_pass = False
    schema_sanity_metrics_ok = False
    manager = None if dry else ApifyKeyManager.from_env()

    def emit_dry_block(pk: str, q_entry: dict[str, str], qv: str, sk: str) -> None:
        spec = get_provider(pk)
        build_qv = "strict" if qv == "sanity" else qv
        payload = build_canary_actor_input(pk, q_entry, max_items, query_variant=build_qv)  # type: ignore[arg-type]
        md_lines.append(f"## Provider `{pk}` (`{spec.actor_id}`) — `{qv}` / `{sk}`")
        md_lines.append("")
        md_lines.append(f"- Canary query label: `{q_entry['label']}`")
        md_lines.append("")
        md_lines.append("### Actor input (no secrets)")
        md_lines.append("")
        md_lines.append("```json")
        md_lines.append(json.dumps(payload, indent=2))
        md_lines.append("```")
        md_lines.append("")
        row = _csv_row_base(
            started=started,
            session_spent=session_spent,
            provider_key=pk,
            actor_id=spec.actor_id,
            canary_label=q_entry["label"],
            dry=True,
            query_variant=qv,
            sample_kind=sk,
        )
        row["provider_status"] = "SKIPPED_DRY_RUN"
        csv_rows.append(row)

    def run_paid_block(
        pk: str,
        q_entry: dict[str, str],
        qv: str,
        sk: str,
    ) -> tuple[dict[str, Any], float, str, str, str]:
        nonlocal session_spent
        spec = get_provider(pk)
        w0, w1 = window_bounds_for_canary_entry(q_entry)
        payload = build_canary_actor_input(pk, q_entry, max_items, query_variant=qv)  # type: ignore[arg-type]
        md_lines.append(f"## Provider `{pk}` (`{spec.actor_id}`) — `{qv}` / `{sk}`")
        md_lines.append("")
        md_lines.append(f"- Canary query label: `{q_entry['label']}`")
        md_lines.append("")
        md_lines.append("### Actor input (no secrets)")
        md_lines.append("")
        md_lines.append("```json")
        md_lines.append(json.dumps(payload, indent=2))
        md_lines.append("```")
        md_lines.append("")

        remaining = session_cap - session_spent
        if remaining <= 1e-9:
            md_lines.append("_Session cap reached; skipping run._")
            return (
                {
                    "returned_rows": 0,
                    "mock_rows": 0,
                    "non_mock_rows": 0,
                    "normalizable_rows": 0,
                    "real_id_rows": 0,
                    "created_at_parse_rows": 0,
                    "explicit_cashtag_rows": 0,
                    "inside_window_rows": 0,
                    "importable_rows": 0,
                    "same_day_today_collapse": False,
                    "mock_dominance": False,
                },
                0.0,
                "",
                "SKIPPED_CAP",
                "session_cap_reached",
            )

        assert manager is not None
        per_run = min(float(os.getenv("X_PROVIDER_CANARY_MAX_CHARGE_PER_RUN", "0.08")) or 0.08, remaining)
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
        ok, reason = provider_canary_passes(metrics, sample_kind=sk)
        md_lines.append("### Metrics (aggregated; no raw tweet text)")
        md_lines.append("")
        md_lines.append("```json")
        md_lines.append(json.dumps(metrics, indent=2))
        md_lines.append("```")
        md_lines.append("")
        md_lines.append(f"- **PASS gate:** `{'PASS' if ok else 'FAIL'}` ({reason})")
        md_lines.append("")
        csv_rows.append(
            {
                "started_at_utc": started,
                "finished_at_utc": finished,
                "provider_key": pk,
                "actor_id": spec.actor_id,
                "canary_label": q_entry["label"],
                "query_variant": qv,
                "sample_kind": sk,
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
        return metrics, cost, finished, st, "" if ok else reason

    for i, pk in enumerate(providers):
        spec = get_provider(pk)
        if not spec.canary_enabled:
            md_lines.append(f"### `{pk}` skipped (canary_enabled=false)")
            md_lines.append("")
            continue
        q_entry = queries[i % len(queries)]
        sk_strict = _sample_kind_for_query_variant("strict", canary_unlocks_overnight=spec.canary_unlocks_overnight)
        sk_broad = _sample_kind_for_query_variant("broad", canary_unlocks_overnight=spec.canary_unlocks_overnight)

        if dry:
            if query_mode == "strict":
                emit_dry_block(pk, q_entry, "strict", sk_strict)
            elif query_mode == "broad":
                emit_dry_block(pk, q_entry, "broad", sk_broad)
            else:
                emit_dry_block(pk, q_entry, "strict", sk_strict)
                emit_dry_block(pk, q_entry, "broad", sk_broad)
            continue

        remaining = session_cap - session_spent
        if remaining <= 1e-9:
            md_lines.append("_Session cap reached; stopping._")
            break

        if query_mode == "strict":
            metrics, _, _, _, _ = run_paid_block(pk, q_entry, "strict", sk_strict)
            ok, _ = provider_canary_passes(metrics, sample_kind=sk_strict)
            if ok and sk_strict == SAMPLE_KIND_RESEARCH_STRICT:
                research_pass = True
            if ok and stop_on_pass and sk_strict == SAMPLE_KIND_RESEARCH_STRICT:
                md_lines.append("_Stop-on-pass: halting remaining providers._")
                break
        elif query_mode == "broad":
            metrics, _, _, _, _ = run_paid_block(pk, q_entry, "broad", sk_broad)
            ok, _ = provider_canary_passes(metrics, sample_kind=sk_broad)
            if ok and stop_on_pass:
                md_lines.append("_Stop-on-pass: halting remaining providers._")
                break
        else:
            metrics, _, _, _, _ = run_paid_block(pk, q_entry, "strict", sk_strict)
            ok_strict, _ = provider_canary_passes(metrics, sample_kind=sk_strict)
            if ok_strict and sk_strict == SAMPLE_KIND_RESEARCH_STRICT:
                research_pass = True
            if ok_strict and stop_on_pass and sk_strict == SAMPLE_KIND_RESEARCH_STRICT:
                md_lines.append("_Stop-on-pass: halting remaining providers._")
                break
            if int(metrics.get("returned_rows", 0)) <= 0:
                remaining = session_cap - session_spent
                if remaining > 1e-9:
                    run_paid_block(pk, q_entry, "broad", sk_broad)

    if include_sanity:
        try:
            s_spec = get_provider(sanity_pk)
        except KeyError:
            md_lines.append(f"### Sanity skipped (unknown X_PROVIDER_CANARY_SANITY_PROVIDER `{sanity_pk}`)")
        else:
            if dry:
                emit_dry_block(sanity_pk, SCHEMA_SANITY_CANARY, "sanity", SAMPLE_KIND_SANITY)
            elif session_cap - session_spent > 1e-9 and s_spec.canary_enabled:
                w0, w1 = window_bounds_for_canary_entry(SCHEMA_SANITY_CANARY)
                md_lines.append(f"## Sanity control (`{s_spec.actor_id}`)")
                md_lines.append("")
                payload = build_canary_actor_input(sanity_pk, SCHEMA_SANITY_CANARY, max_items, query_variant="strict")
                md_lines.append("### Actor input (no secrets)")
                md_lines.append("")
                md_lines.append("```json")
                md_lines.append(json.dumps(payload, indent=2))
                md_lines.append("```")
                md_lines.append("")
                assert manager is not None
                per_run = min(
                    float(os.getenv("X_PROVIDER_CANARY_MAX_CHARGE_PER_RUN", "0.08")) or 0.08,
                    session_cap - session_spent,
                )
                key = manager.choose_key(platform="x", projected_cost_usd=per_run)
                with manager.activate_key(key):
                    run = _start_run(s_spec.actor_id, payload, key.token, per_run)
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
                        actor_id=s_spec.actor_id,
                        expected_ticker=SCHEMA_SANITY_CANARY["ticker"],
                        window_start_unix=w0,
                        window_end_unix=w1,
                    )
                session_spent += cost
                finished = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                ok, reason = provider_canary_passes(metrics, sample_kind=SAMPLE_KIND_SANITY)
                sane_schema = (
                    int(metrics.get("returned_rows", 0)) > 0
                    and int(metrics.get("non_mock_rows", 0)) > 0
                    and not metrics.get("same_day_today_collapse")
                )
                if sane_schema:
                    schema_sanity_metrics_ok = True
                md_lines.append("### Metrics (schema sanity control; not research-importable)")
                md_lines.append("")
                md_lines.append("```json")
                md_lines.append(json.dumps(metrics, indent=2))
                md_lines.append("```")
                md_lines.append("")
                md_lines.append(f"- **PASS gate:** `{'PASS' if ok else 'FAIL'}` ({reason})")
                md_lines.append("")
                csv_rows.append(
                    {
                        "started_at_utc": started,
                        "finished_at_utc": finished,
                        "provider_key": sanity_pk,
                        "actor_id": s_spec.actor_id,
                        "canary_label": SCHEMA_SANITY_CANARY["label"],
                        "query_variant": "sanity",
                        "sample_kind": SAMPLE_KIND_SANITY,
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

    verdict = "PASS" if research_pass else "FAIL"
    gate = "RESEARCH_PASS" if research_pass else (
        "SCHEMA_PASS_RESEARCH_FAIL" if schema_sanity_metrics_ok and not research_pass else "FAIL"
    )
    md_lines.extend(
        [
            "## Overall verdict",
            "",
            f"**{verdict}** (research_strict overnight-eligible PASS: {research_pass})",
            f"**Classification:** `{gate}`",
            "",
            "Broad probes and `schema_sanity_control` runs never satisfy the overnight canary gate, even if numeric rates look strong.",
        ]
    )

    CANARY_RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    CANARY_RESULTS_MD.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")
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
