#!/usr/bin/env python3
"""Universal X provider dataset schema diagnostics (no new Actor runs by default).

With ``--run-id`` / ``--dataset-id``, fetches a small sample via Apify REST API.
Use ``--fixture`` for offline replay. Never logs tokens or full tweet text.
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

from finfluencer_alpha.x_apify_provider_registry import (  # noqa: E402
    get_provider,
    summarize_provider_canary_rows,
    window_bounds_for_canary_entry,
)
from finfluencer_alpha.x_youtube_pipeline import (  # noqa: E402
    APIFY_BASE_URL,
    _apify_headers,
    diagnose_apify_x_item_quality,
    normalize_apify_x_post,
)

OUT = ROOT / "data/exports/overnight_collection/38_x_provider_schema_debug.md"

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
        raise RuntimeError(f"HTTP {response.status_code} for run {run_id}")
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
    raise ValueError(f"Fixture {path} must be a JSON list or {{\"items\": [...]}}")


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
        raise RuntimeError("Markdown matched a token-like pattern.")


def build_report(
    sections: list[tuple[str, list[dict[str, Any]], str, str, int, int]],
    *,
    sample: int,
) -> str:
    lines: list[str] = [
        "# X provider dataset schema debug",
        "",
        "Generated by `scripts/debug_x_provider_dataset_schema.py` (no secrets, no full tweet bodies).",
        "",
    ]
    for label, items, actor_id, ticker, w0, w1 in sections:
        items = items[:sample]
        lines.append(f"## {label}")
        lines.append("")
        lines.append(f"- Sample size: **{len(items)}**")
        if not items:
            lines.append("- _No items._")
            lines.append("")
            continue
        top_keys: Counter[str] = Counter()
        nested_paths: Counter[str] = Counter()
        for it in items:
            for k in it.keys():
                top_keys[k] += 1
            for p in _nested_keys(it):
                nested_paths[p] += 1
        agg = summarize_provider_canary_rows(
            items,
            actor_id=actor_id,
            expected_ticker=ticker,
            window_start_unix=w0,
            window_end_unix=w1,
        )
        lines.append("")
        lines.append("### Aggregate metrics")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(agg, indent=2, default=str))
        lines.append("```")
        lines.append("")
        lines.append("### Top-level keys (sample)")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(top_keys.most_common(), indent=2))
        lines.append("```")
        lines.append("")
        lines.append("### Nested paths (depth ≤ 3)")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(nested_paths.most_common(40), indent=2))
        lines.append("```")
        lines.append("")
        lines.append("| idx | type | id | text_len | prefix | mock? | norm_ok | reject | strict_$ |")
        lines.append("|---:|---|---:|---:|---|:---:|---|---|---|")
        for i, it in enumerate(items):
            d = diagnose_apify_x_item_quality(it, expected_ticker=ticker, window_start_unix=w0, window_end_unix=w1)
            tid = it.get("id")
            tl = len(str(it.get("text") or ""))
            pr = _safe_prefix(str(it.get("text") or ""), 12)
            mt = str(it.get("type", ""))
            mock = str(mt).lower() == "mock_tweet" or tid == -1 or str(tid) == "-1"
            n_ok = bool(
                normalize_apify_x_post(
                    it,
                    actor_id=actor_id,
                    key_label="debug",
                    source_type="search",
                    source_value="debug",
                    expected_ticker=ticker,
                    window_start_unix=w0,
                    window_end_unix=w1,
                )
            )
            lines.append(
                f"| {i} | {mt!s} | `{tid!s}` | {tl} | `{pr}` | {mock} | {n_ok} | "
                f"{d.get('reject_reason')} | {d.get('strict_cashtag_for_expected_ticker')} |"
            )
        lines.append("")
    text = "\n".join(lines) + "\n"
    assert_markdown_has_no_secrets(text)
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="apidojo_v2")
    parser.add_argument("--run-id", action="append", default=[])
    parser.add_argument("--dataset-id", action="append", default=[])
    parser.add_argument("--fixture", type=Path, action="append", default=[])
    parser.add_argument("--expected-ticker", default="TSLA")
    parser.add_argument("--window-start", default="2020-02-18")
    parser.add_argument("--window-end", default="2020-02-24")
    parser.add_argument("--sample", type=int, default=8)
    args = parser.parse_args()

    spec = get_provider(args.provider)
    w0, w1 = window_bounds_for_canary_entry(
        {
            "since": args.window_start,
            "until": args.window_end,
            "query": "",
            "label": "",
            "ticker": "",
        }
    )
    sections: list[tuple[str, list[dict[str, Any]], str, str, int, int]] = []

    if args.fixture:
        for fp in args.fixture:
            items = _load_fixture_items(fp.resolve())
            sections.append((f"fixture:{fp}", items, spec.actor_id, args.expected_ticker, w0, w1))
    elif args.run_id or args.dataset_id:
        token = _first_apify_token()
        for rid in args.run_id:
            label = f"run:{rid}"
            if os.getenv("X_DEBUG_RESOLVE_DATASET", "").strip() == "1":
                meta = _fetch_actor_run(rid, token)
                ds = meta.get("defaultDatasetId")
                label += f" (defaultDatasetId={ds!r})"
            items = _fetch_sample(rid, token, args.sample)
            sections.append((label, items, spec.actor_id, args.expected_ticker, w0, w1))
        for did in args.dataset_id:
            items = _fetch_dataset_sample(did, token, args.sample)
            sections.append((f"dataset:{did}", items, spec.actor_id, args.expected_ticker, w0, w1))
    else:
        sections.append(("offline_stub", [], spec.actor_id, args.expected_ticker, w0, w1))

    text = build_report(sections, sample=args.sample)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    try:
        rel = OUT.relative_to(ROOT)
    except ValueError:
        rel = OUT
    print(f"wrote {rel}")


if __name__ == "__main__":
    main()
