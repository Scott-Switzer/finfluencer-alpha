#!/usr/bin/env python3
"""Replay Apify dataset rows for prior Actor runs (no new Actor starts).

Fetches a small sample using the Apify REST API and ``APIFY_TOKEN`` or
``APIFY_TOKEN_1`` from ``.env``. Never prints token values.

Usage:
  cd /workspace/FIN496CAPSTONE
  PYTHONPATH=src .venv/bin/python scripts/debug_kaito_dataset_schema.py \\
    --run-id RUN_ID [--run-id RUN2] [--sample 8]

  PYTHONPATH=src .venv/bin/python scripts/debug_kaito_dataset_schema.py \\
    --dataset-id DATASET_ID

  PYTHONPATH=src .venv/bin/python scripts/debug_kaito_dataset_schema.py \\
    --fixture path/to/items.json

Or pass comma-separated run IDs:
  KAITO_DEBUG_RUN_IDS=id1,id2 PYTHONPATH=src .venv/bin/python scripts/debug_kaito_dataset_schema.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)
load_dotenv(ROOT / ".env", override=False)

from finfluencer_alpha.x_youtube_pipeline import (  # noqa: E402
    APIFY_BASE_URL,
    _apify_headers,
    diagnose_apify_x_item_quality,
    normalize_apify_x_post,
)

OUT = ROOT / "data/exports/overnight_collection/36_kaito_payload_schema_debug.md"

_TOKEN_LIKE = re.compile(
    r"(?i)\b(bearer\s+[a-z0-9._-]{20,}|apify_api[a-z0-9._-]{10,}|token\s*=\s*['\"]?[a-z0-9._-]{16,})\b"
)


def _first_apify_token() -> str:
    count_raw = os.getenv("APIFY_TOKEN_COUNT", "0").strip() or "0"
    try:
        n = int(count_raw)
    except ValueError:
        n = 0
    for i in range(1, max(n, 0) + 1):
        tok = os.getenv(f"APIFY_TOKEN_{i}", "").strip()
        if tok:
            return tok
    tok = os.getenv("APIFY_TOKEN", "").strip()
    if tok:
        return tok
    raise RuntimeError("No APIFY_TOKEN or APIFY_TOKEN_N in environment")


def _unwrap_apify_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        inner = payload.get("data")
        if isinstance(inner, dict):
            return inner
        return payload
    return {}


def _fetch_actor_run(run_id: str, token: str) -> dict[str, Any]:
    url = f"{APIFY_BASE_URL}/actor-runs/{run_id}"
    response = requests.get(url, headers=_apify_headers(token), timeout=120)
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code} loading actor run {run_id}")
    return _unwrap_apify_dict(response.json())


def _fetch_sample(run_id: str, token: str, limit: int) -> list[dict[str, Any]]:
    url = f"{APIFY_BASE_URL}/actor-runs/{run_id}/dataset/items"
    response = requests.get(
        url,
        headers=_apify_headers(token),
        params={"format": "json", "clean": "1", "limit": str(limit)},
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code} for run {run_id} dataset/items")
    payload = response.json()
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("data") or []
        return [x for x in items if isinstance(x, dict)]
    return []


def _fetch_dataset_sample(dataset_id: str, token: str, limit: int) -> list[dict[str, Any]]:
    url = f"{APIFY_BASE_URL}/datasets/{dataset_id}/items"
    response = requests.get(
        url,
        headers=_apify_headers(token),
        params={"format": "json", "clean": "1", "limit": str(limit)},
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code} for dataset {dataset_id}")
    payload = response.json()
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("data") or []
        return [x for x in items if isinstance(x, dict)]
    return []


def _load_fixture_items(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        inner = data.get("items") or data.get("data")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    raise ValueError(f"Fixture {path} must be a JSON list of objects or {{\"items\": [...]}}")


def _nested_keys(obj: Any, prefix: str = "", depth: int = 0, out: list[str] | None = None) -> list[str]:
    if out is None:
        out = []
    if depth > 3 or not isinstance(obj, dict):
        return out
    for k, v in sorted(obj.items()):
        path = f"{prefix}.{k}" if prefix else k
        out.append(path)
        if isinstance(v, dict):
            _nested_keys(v, path, depth + 1, out)
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            _nested_keys(v[0], f"{path}[0]", depth + 1, out)
    return out


def _safe_prefix(text: str, n: int = 12) -> str:
    t = (text or "").replace("\n", " ").strip()
    return t[:n]


def assert_markdown_has_no_secrets(text: str) -> None:
    if _TOKEN_LIKE.search(text):
        raise RuntimeError("Generated markdown matched a token-like pattern (refusing to write).")


def build_report(
    sections_sources: list[tuple[str, list[dict[str, Any]]]],
    *,
    sample: int,
    expected_ticker: str,
) -> str:
    sections: list[str] = [
        "# Kaito / Apify dataset payload schema debug",
        "",
        "Generated by `scripts/debug_kaito_dataset_schema.py` (no new Actor runs, no tokens logged).",
        "",
        "## Sources inspected",
        "",
        "```json",
        json.dumps([label for label, _ in sections_sources], indent=2),
        "```",
        "",
    ]

    total_items = 0
    type_counts: Counter[str] = Counter()
    diag_counts: Counter[str] = Counter()
    normalize_ok = 0

    for label, items in sections_sources:
        items = items[:sample]
        total_items += len(items)
        sections.append(f"## {label}")
        sections.append("")
        sections.append(f"- Sample size: **{len(items)}**")
        if not items:
            sections.append("- **No items returned** (dataset empty or inaccessible).")
            sections.append("")
            continue
        top_keys = Counter()
        nested_paths: Counter[str] = Counter()
        for it in items:
            for k in it.keys():
                top_keys[k] += 1
            for p in _nested_keys(it):
                nested_paths[p] += 1
            t = str(it.get("type", "") or "?")
            type_counts[t] += 1
            d = diagnose_apify_x_item_quality(it, expected_ticker=expected_ticker)
            diag_counts[d["reject_reason"]] += 1
            if normalize_apify_x_post(
                it,
                actor_id="kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest",
                key_label="debug",
                source_type="search",
                source_value="debug",
            ):
                normalize_ok += 1
        sections.append("")
        sections.append("### Top-level key presence (sample)")
        sections.append("")
        sections.append("```json")
        sections.append(json.dumps(top_keys.most_common(), indent=2))
        sections.append("```")
        sections.append("")
        sections.append("### Nested paths (depth ≤ 3, first list element only)")
        sections.append("")
        sections.append("```json")
        sections.append(json.dumps(nested_paths.most_common(40), indent=2))
        sections.append("```")
        sections.append("")
        sections.append("### Per-item quick scan (redacted)")
        sections.append("")
        sections.append("| idx | type | id_type | text_len | text_prefix | reject_reason |")
        sections.append("|---:|---|---|---:|---|---|")
        for i, it in enumerate(items):
            d = diagnose_apify_x_item_quality(it, expected_ticker=expected_ticker)
            tid = it.get("id")
            tid_t = type(tid).__name__
            tx = _safe_prefix(str(it.get("text") or ""), 12)
            tl = len(str(it.get("text") or ""))
            sections.append(
                f"| {i} | {it.get('type', '')!s} | {tid_t} | {tl} | `{tx}` | {d.get('reject_reason')} |"
            )
        sections.append("")

    sections.extend(
        [
            "## Aggregate findings",
            "",
            f"- **Total sample rows:** {total_items}",
            f"- **`type` distribution:** ```json\n{json.dumps(dict(type_counts), indent=2)}\n```",
            f"- **`diagnose_apify_x_item_quality` reject_reason counts:** ```json\n{json.dumps(dict(diag_counts), indent=2)}\n```",
            f"- **`normalize_apify_x_post` successes in sample:** {normalize_ok}",
            "",
            "## Interpretation",
            "",
            "- If every row has **`type: mock_tweet`** and **`id: -1`**, the Actor returned **KaitoEasyAPI placeholder rows** (pricing / quota messaging), not real tweets. **Imports stay at zero** because there is no parseable `created_at` and no real tweet id.",
            "- **Fixing field aliases alone cannot import mocks.** Resolve Actor billing / quota / search coverage so the dataset contains real tweet payloads, then re-run a capped checkpoint.",
            "",
        ]
    )
    text = "\n".join(sections) + "\n"
    assert_markdown_has_no_secrets(text)
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", action="append", dest="run_ids", default=[])
    parser.add_argument("--dataset-id", action="append", dest="dataset_ids", default=[])
    parser.add_argument("--fixture", action="append", dest="fixtures", default=[], type=Path)
    parser.add_argument("--sample", type=int, default=8)
    parser.add_argument("--expected-ticker", default="TSLA")
    parser.add_argument(
        "--resolve-dataset",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="For each --run-id, call GET /actor-runs/{id} and record defaultDatasetId (safe metadata only).",
    )
    args = parser.parse_args()
    run_ids = list(args.run_ids)
    env_ids = os.getenv("KAITO_DEBUG_RUN_IDS", "").strip()
    if env_ids:
        run_ids.extend([x.strip() for x in env_ids.split(",") if x.strip()])
    if not run_ids and not args.dataset_ids and not args.fixtures:
        run_ids = ["5Xu4Ewz3PUUXHLoWe"]

    token = _first_apify_token()
    sections_sources: list[tuple[str, list[dict[str, Any]]]] = []

    for rid in run_ids:
        meta_lines: list[str] = []
        if args.resolve_dataset:
            meta = _fetch_actor_run(rid, token)
            ds_id = str(meta.get("defaultDatasetId") or "")
            st = str(meta.get("status") or "")
            act = str(meta.get("actId") or meta.get("actorId") or "")
            meta_lines.append(f"run `{rid}` status={st!r} actId={act!r} defaultDatasetId={ds_id!r}")
        items = _fetch_sample(rid, token, args.sample)
        label = "run:" + rid
        if meta_lines:
            label = label + " (" + "; ".join(meta_lines) + ")"
        sections_sources.append((label, items))

    for did in args.dataset_ids:
        items = _fetch_dataset_sample(did, token, args.sample)
        sections_sources.append((f"dataset:{did}", items))

    for fp in args.fixtures:
        items = _load_fixture_items(fp.resolve())
        sections_sources.append((f"fixture:{fp}", items))

    text = build_report(
        sections_sources,
        sample=args.sample,
        expected_ticker=args.expected_ticker,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    try:
        rel = OUT.relative_to(ROOT)
    except ValueError:
        print(f"wrote {OUT}")
    else:
        print(f"wrote {rel}")


if __name__ == "__main__":
    main()
