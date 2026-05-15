#!/usr/bin/env python3
"""Plan YouTube Apify transcript provider drain (no paid calls)."""
from __future__ import annotations

import csv
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

DB_PATH = ROOT / "data" / "finfluencer_alpha.db"
OUT_DIR = ROOT / "data" / "exports" / "overnight_collection"
OUT_CSV = OUT_DIR / "51_youtube_apify_provider_plan.csv"
OUT_MD = OUT_DIR / "51_youtube_apify_provider_plan.md"

PREFERRED = [
    "supreme_coder/youtube-transcript-scraper",
    "curious_coder/youtube-transcript-scraper",
    "insight_api_labs/youtube-transcript",
]

FALLBACKS = [
    "seemuapps/youtube-transcript-scraper",
    "powerai/youtube-transcript-scraper",
    "pintostudio/youtube-transcript-scraper",
    "muhammad_noman_riaz/youtube-video-transcript-super-scraper",
]


@dataclass
class ProviderPlanRow:
    actor_id: str
    expected_input_schema: str
    pricing_summary: str
    historical_success_count: int
    historical_failure_count: int
    estimated_cost_per_successful_transcript_usd: str
    supports_batch_urls: str
    supports_json_timestamps: str
    selected: str
    reason: str


def _normalize(actor_id: str) -> str:
    return actor_id.replace("/", "~", 1) if "/" in actor_id and "~" not in actor_id else actor_id


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _token() -> str:
    return os.getenv("APIFY_TOKEN_1", "").strip() or os.getenv("APIFY_TOKEN", "").strip()


def _actor_meta(actor_id: str, token: str) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(f"https://api.apify.com/v2/acts/{_normalize(actor_id)}", headers=headers, timeout=40)
    if r.status_code >= 400:
        return {"error_http_status": r.status_code}
    try:
        body = r.json()
    except Exception:
        return {"error_http_status": r.status_code}
    data = body.get("data")
    return data if isinstance(data, dict) else {}


def _schema_summary(meta: dict[str, Any]) -> tuple[str, str, str]:
    schema = meta.get("inputSchema")
    if not isinstance(schema, dict):
        return "", "unknown", "unknown"
    props = schema.get("properties")
    if not isinstance(props, dict):
        return "", "unknown", "unknown"
    keys = sorted(props.keys())
    summary = ",".join(keys[:20])
    lower = {k.lower() for k in keys}
    batch = "yes" if any(k in lower for k in {"videourls", "urls", "starturls"}) else "no"
    timestamps = "yes" if any(k in lower for k in {"timestamps", "outputformat", "format"}) else "unknown"
    return summary, batch, timestamps


def _pricing(meta: dict[str, Any]) -> str:
    for k in ("pricing", "pricingModel", "pricingInfo"):
        v = meta.get(k)
        if isinstance(v, str) and v.strip():
            return v[:180]
        if isinstance(v, dict):
            model = str(v.get("model") or v.get("pricingModel") or "").strip()
            desc = str(v.get("description") or "").strip()
            out = " ".join(x for x in [model, desc] if x)
            if out:
                return out[:180]
    text = " ".join(str(meta.get(k) or "") for k in ("title", "description", "name")).lower()
    if "pay per result" in text or "pay-per-result" in text:
        return "pay-per-result (from actor description text)"
    if "consumption" in text:
        return "consumption pricing (from actor description text)"
    return ""


def _history_counts(conn: sqlite3.Connection) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    # youtube_transcripts.provider_actor_id stores canonical slash actor id for apify
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='youtube_transcripts'").fetchone():
        rows = conn.execute(
            """
            SELECT provider_actor_id, status, COUNT(*) AS n
            FROM youtube_transcripts
            WHERE COALESCE(provider_actor_id,'') != ''
            GROUP BY provider_actor_id, status
            """
        ).fetchall()
        tmp: dict[str, dict[str, int]] = {}
        for r in rows:
            aid = str(r["provider_actor_id"])
            tmp.setdefault(aid, {})
            tmp[aid][str(r["status"] or "")] = int(r["n"] or 0)
        for aid, m in tmp.items():
            succ = m.get("available", 0)
            fail = sum(v for k, v in m.items() if k != "available")
            out[aid] = (succ, fail)
    return out


def main() -> None:
    token = _token()
    token_count = int(os.getenv("APIFY_TOKEN_COUNT", "0") or 0)
    all_actors = list(dict.fromkeys(PREFERRED + FALLBACKS))
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    history: dict[str, tuple[int, int]] = {}
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            history = _history_counts(conn)
        finally:
            conn.close()

    rows: list[ProviderPlanRow] = []
    selected_actor = ""
    for actor_id in all_actors:
        meta = _actor_meta(actor_id, token)
        schema, batch, ts = _schema_summary(meta)
        pricing = _pricing(meta)
        succ, fail = history.get(actor_id, (0, 0))
        est = ""
        if succ > 0 and pricing:
            est = "historical_available+metadata_pricing"
        elif succ > 0:
            est = "historical_available_no_pricing"
        elif pricing:
            est = "metadata_only"

        # selection logic: preferred order + not deprecated + schema available
        deprecated = str(meta.get("isDeprecated") or "").lower() in {"true", "1", "yes"}
        selected = "0"
        reason = "not selected"
        if not selected_actor:
            if deprecated:
                reason = "deprecated actor"
            elif actor_id in PREFERRED:
                selected = "1"
                selected_actor = actor_id
                reason = "first preferred provider in configured order"
            elif succ > 0:
                selected = "1"
                selected_actor = actor_id
                reason = "fallback with prior success history"
            else:
                reason = "fallback kept as reserve"

        rows.append(
            ProviderPlanRow(
                actor_id=actor_id,
                expected_input_schema=schema,
                pricing_summary=pricing,
                historical_success_count=succ,
                historical_failure_count=fail,
                estimated_cost_per_successful_transcript_usd=est,
                supports_batch_urls=batch,
                supports_json_timestamps=ts,
                selected=selected,
                reason=reason,
            )
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "actor_id",
        "expected_input_schema",
        "pricing_summary",
        "historical_success_count",
        "historical_failure_count",
        "estimated_cost_per_successful_transcript_usd",
        "supports_batch_urls",
        "supports_json_timestamps",
        "selected",
        "reason",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r.__dict__)

    lines = [
        "# YouTube Apify provider plan",
        "",
        f"Generated (UTC): `{now}`",
        f"APIFY_TOKEN_COUNT: `{token_count}`",
        f"Selected provider: `{selected_actor or 'none'}`",
        "",
        "## Provider rows",
        "",
    ]
    for r in rows:
        lines.append(
            f"- `{r.actor_id}` selected={r.selected} batch={r.supports_batch_urls} "
            f"timestamps={r.supports_json_timestamps} history_success={r.historical_success_count} "
            f"history_fail={r.historical_failure_count} reason=`{r.reason}`"
        )
    OUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"WROTE_CSV={_display_path(OUT_CSV)}")
    print(f"WROTE_MD={_display_path(OUT_MD)}")
    print(f"SELECTED_PROVIDER={selected_actor or 'none'}")


if __name__ == "__main__":
    main()
