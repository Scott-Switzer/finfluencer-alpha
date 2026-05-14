"""Registry of X/Twitter Apify actors for canary tests and overnight collection.

Handle + query strings for canaries are audited in ``scripts/x_native_creator_checkpoint_1.py``
(``CHANNEL_X``). Do not invent handles here.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from finfluencer_alpha.config import PROJECT_ROOT


def _clean_str(value: object) -> str:
    return str(value or "").strip()

# ---------------------------------------------------------------------------
# Audited canary queries (advanced search). Handles match CHANNEL_X needles.
# ---------------------------------------------------------------------------

CANARY_SEARCH_QUERIES: list[dict[str, str]] = [
    {
        "label": "realMeetKevin_TSLA_2021w1",
        "query": "from:realMeetKevin $TSLA since:2021-01-01 until:2021-01-08 lang:en",
        "ticker": "TSLA",
        "since": "2021-01-01",
        "until": "2021-01-08",
        "handle_audit": "CHANNEL_X: meet kevin -> realMeetKevin",
    },
    {
        "label": "GrahamStephan_AAPL_2020w1",
        "query": "from:GrahamStephan $AAPL since:2020-08-01 until:2020-08-08 lang:en",
        "ticker": "AAPL",
        "since": "2020-08-01",
        "until": "2020-08-08",
        "handle_audit": "CHANNEL_X: graham -> GrahamStephan",
    },
    {
        "label": "StockMoe_NIO_2021w1",
        "query": "from:StockMoe $NIO since:2021-02-01 until:2021-02-08 lang:en",
        "ticker": "NIO",
        "since": "2021-02-01",
        "until": "2021-02-08",
        "handle_audit": "CHANNEL_X: stock moe -> StockMoe",
    },
    {
        "label": "ThePlainBagel_PYPL_2022w1",
        "query": "from:ThePlainBagel $PYPL since:2022-02-01 until:2022-02-08 lang:en",
        "ticker": "PYPL",
        "since": "2022-02-01",
        "until": "2022-02-08",
        "handle_audit": "CHANNEL_X: plain bagel -> ThePlainBagel",
    },
]


def default_canary_queries() -> list[dict[str, str]]:
    import os

    raw = os.getenv("X_PROVIDER_CANARY_QUERY_LABELS", "").strip()
    if not raw:
        return list(CANARY_SEARCH_QUERIES)
    wanted = {x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()}
    picked = [q for q in CANARY_SEARCH_QUERIES if q["label"] in wanted]
    return picked or list(CANARY_SEARCH_QUERIES)


def _date_window_unix_bounds(start_date: str, end_date: str) -> tuple[int, int]:
    start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(end_date, "%Y-%m-%d").replace(
        hour=23,
        minute=59,
        second=59,
        tzinfo=UTC,
    )
    if end < start:
        raise ValueError(f"end_date must be on or after start_date: {start_date} > {end_date}")
    return int(start.timestamp()), int(end.timestamp())


def window_bounds_for_canary_entry(entry: dict[str, str]) -> tuple[int, int]:
    return _date_window_unix_bounds(entry["since"], entry["until"])


@dataclass(frozen=True)
class XApifyProviderSpec:
    key: str
    actor_id: str
    default_max_items: int
    supports_advanced_search: bool
    supports_date_bounds: bool | str
    canary_enabled: bool
    status: str
    notes: str
    adapter_name: str = "default"


def _providers() -> dict[str, XApifyProviderSpec]:
    import os

    kaito_on = os.getenv("X_PROVIDER_CANARY_INCLUDE_KAITO", "").strip().lower() in {"1", "true", "yes", "on"}
    return {
        "kaito_cheapest": XApifyProviderSpec(
            key="kaito_cheapest",
            actor_id="kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest",
            default_max_items=5,
            supports_advanced_search=True,
            supports_date_bounds=True,
            canary_enabled=kaito_on,
            status="blocked_if_mock_only",
            notes="Smoke replay returned type:mock_tweet placeholder rows only.",
        ),
        "xquik": XApifyProviderSpec(
            key="xquik",
            actor_id="xquik/x-tweet-scraper",
            default_max_items=5,
            supports_advanced_search=True,
            supports_date_bounds="unknown",
            canary_enabled=True,
            status="candidate",
            notes="Lower cost; advanced search support per marketplace listing (verify via canary).",
        ),
        "scrapebadger": XApifyProviderSpec(
            key="scrapebadger",
            actor_id="scrape.badger/twitter-tweets-scraper",
            default_max_items=5,
            supports_advanced_search=True,
            supports_date_bounds="unknown",
            canary_enabled=True,
            status="candidate",
            notes="Low cost actor; schema must be verified before overnight.",
        ),
        "scweet": XApifyProviderSpec(
            key="scweet",
            actor_id="altimis/scweet",
            default_max_items=5,
            supports_advanced_search=True,
            supports_date_bounds="unknown",
            canary_enabled=True,
            status="candidate",
            notes="Search/profile/date filtering per listing; verify billing model.",
        ),
        "apidojo_v2": XApifyProviderSpec(
            key="apidojo_v2",
            actor_id="apidojo/tweet-scraper",
            default_max_items=5,
            supports_advanced_search=True,
            supports_date_bounds=True,
            canary_enabled=True,
            status="candidate",
            notes="Established apidojo tweet-scraper input shape already supported in pipeline.",
        ),
        "apidojo_lite": XApifyProviderSpec(
            key="apidojo_lite",
            actor_id="apidojo/twitter-scraper-lite",
            default_max_items=5,
            supports_advanced_search=True,
            supports_date_bounds=True,
            canary_enabled=True,
            status="candidate",
            notes="Advanced searchTerms; event pricing — keep maxItems tiny for canary.",
        ),
    }


def all_provider_keys() -> list[str]:
    return sorted(_providers().keys())


def get_provider(key: str) -> XApifyProviderSpec:
    k = key.strip().lower()
    prov = _providers().get(k)
    if prov is None:
        raise KeyError(f"Unknown X Apify provider: {key!r}")
    return prov


def build_canary_actor_input(provider_key: str, canary_entry: dict[str, str], max_items: int) -> dict[str, Any]:
    from finfluencer_alpha.x_youtube_pipeline import build_x_actor_input

    spec = get_provider(provider_key)
    return build_x_actor_input(
        spec.actor_id,
        "advanced_search",
        canary_entry["query"],
        max_items,
        date_start=canary_entry["since"],
        date_end=canary_entry["until"],
    )


def is_placeholder_apify_row(item: Any) -> bool:
    if not isinstance(item, dict):
        return True
    if str(item.get("type", "")).lower() == "mock_tweet":
        return True
    rid = item.get("id")
    if rid == -1:
        return True
    if str(rid).strip() == "-1":
        return True
    return False


def historical_window_suspect_same_utc_today(
    items: list[dict[str, Any]],
    *,
    window_end_unix: int,
) -> bool:
    from finfluencer_alpha.x_youtube_pipeline import _CREATED_PATHS, _nested, _normalize_created_at

    window_end_d = datetime.fromtimestamp(window_end_unix, UTC).date()
    today = datetime.now(UTC).date()
    if window_end_d >= today:
        return False
    day_strings: list[str] = []
    for item in items:
        if not isinstance(item, dict) or is_placeholder_apify_row(item):
            continue
        raw = _nested(item, *_CREATED_PATHS)
        norm = _normalize_created_at(raw)
        if norm:
            day_strings.append(norm[:10])
    if not day_strings:
        return False
    today_s = today.isoformat()
    return all(d == today_s for d in day_strings)


def summarize_provider_canary_rows(
    items: list[dict[str, Any]],
    *,
    actor_id: str,
    expected_ticker: str,
    window_start_unix: int,
    window_end_unix: int,
) -> dict[str, Any]:
    from finfluencer_alpha.x_youtube_pipeline import (
        _ID_PATHS,
        _is_usable_finance_post,
        _nested,
        diagnose_apify_x_item_quality,
        normalize_apify_x_post,
    )

    returned_rows = len([x for x in items if isinstance(x, dict)])
    mock_rows = 0
    non_mock_rows = 0
    normalizable_rows = 0
    real_id_rows = 0
    created_at_parse_rows = 0
    explicit_cashtag_rows = 0
    inside_window_rows = 0
    importable_rows = 0

    for item in items:
        if not isinstance(item, dict):
            continue
        if is_placeholder_apify_row(item):
            mock_rows += 1
            continue
        non_mock_rows += 1

        rid = _clean_str(_nested(item, *_ID_PATHS))
        if rid.isdigit() and int(rid) > 0:
            real_id_rows += 1

        d = diagnose_apify_x_item_quality(
            item,
            expected_ticker=expected_ticker,
            window_start_unix=window_start_unix,
            window_end_unix=window_end_unix,
        )
        if d.get("date_parse_succeeded"):
            created_at_parse_rows += 1
        if d.get("strict_cashtag_for_expected_ticker"):
            explicit_cashtag_rows += 1
        if d.get("date_parse_succeeded") and d.get("reject_reason") != "outside_window":
            inside_window_rows += 1

        base = normalize_apify_x_post(
            item,
            actor_id=actor_id,
            key_label="canary",
            source_type="search",
            source_value="canary",
        )
        if base is not None:
            normalizable_rows += 1

        strict = normalize_apify_x_post(
            item,
            actor_id=actor_id,
            key_label="canary",
            source_type="search",
            source_value="canary",
            expected_ticker=expected_ticker,
            window_start_unix=window_start_unix,
            window_end_unix=window_end_unix,
        )
        if strict is not None and _is_usable_finance_post(strict.get("text", "")):
            importable_rows += 1

    collapse = historical_window_suspect_same_utc_today(
        items,
        window_end_unix=window_end_unix,
    )
    mock_dominance = bool(returned_rows and mock_rows / returned_rows > 0.5)

    return {
        "returned_rows": returned_rows,
        "mock_rows": mock_rows,
        "non_mock_rows": non_mock_rows,
        "normalizable_rows": normalizable_rows,
        "real_id_rows": real_id_rows,
        "created_at_parse_rows": created_at_parse_rows,
        "explicit_cashtag_rows": explicit_cashtag_rows,
        "inside_window_rows": inside_window_rows,
        "importable_rows": importable_rows,
        "same_day_today_collapse": collapse,
        "mock_dominance": mock_dominance,
    }


def provider_canary_passes(metrics: dict[str, Any]) -> tuple[bool, str]:
    if metrics["returned_rows"] <= 0:
        return False, "no_returned_rows"
    if metrics["non_mock_rows"] <= 0:
        return False, "mock_only_dataset"
    if metrics.get("same_day_today_collapse"):
        return False, "suspect_same_utc_today_collapse"
    if metrics.get("mock_dominance"):
        return False, "mock_row_dominance"
    if int(metrics.get("mock_rows", 0)) > 0:
        return False, "nonzero_mock_rows"
    nm = int(metrics["non_mock_rows"])
    if nm <= 0:
        return False, "non_mock_zero"
    need = 0.8

    def rate(num: int) -> float:
        return num / nm

    if rate(int(metrics["real_id_rows"])) < need:
        return False, "real_id_rate_below_threshold"
    if rate(int(metrics["created_at_parse_rows"])) < need:
        return False, "created_at_parse_rate_below_threshold"
    if rate(int(metrics["explicit_cashtag_rows"])) < need:
        return False, "explicit_cashtag_rate_below_threshold"
    if rate(int(metrics["inside_window_rows"])) < need:
        return False, "inside_window_rate_below_threshold"
    if int(metrics.get("normalizable_rows", 0)) <= 0:
        return False, "no_normalizable_rows"
    return True, "pass"


CANARY_RESULTS_MD = PROJECT_ROOT / "data/exports/overnight_collection/39_x_provider_canary_results.md"
CANARY_RESULTS_CSV = PROJECT_ROOT / "data/exports/overnight_collection/39_x_provider_canary_results.csv"


def _parse_iso_ts(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def latest_canary_pass_from_csv(
    csv_path: Path | None = None,
    *,
    max_age_hours: int = 24,
) -> tuple[bool, str]:
    """Return (ok, reason) if CSV shows a PASS provider within max_age_hours."""
    path = csv_path or CANARY_RESULTS_CSV
    if not path.exists():
        return False, f"missing_canary_csv:{path}"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"read_error:{exc}"
    reader = csv.DictReader(text.splitlines())
    rows = list(reader)
    if not rows:
        return False, "empty_canary_csv"
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    best: datetime | None = None
    for row in rows:
        if (row.get("provider_status") or "").strip().upper() != "PASS":
            continue
        ts = _parse_iso_ts(row.get("finished_at_utc") or row.get("started_at_utc") or "")
        if ts is None:
            continue
        if ts >= cutoff:
            return True, f"pass_within_window:{row.get('provider_key')}"
        if best is None or ts > best:
            best = ts
    return False, "no_pass_in_window"


def canary_markdown_reports_pass(md_path: Path | None = None) -> bool:
    """Lightweight check for overnight gate when CSV row missing but MD updated."""
    import re

    path = md_path or CANARY_RESULTS_MD
    if not path.exists():
        return False
    try:
        body = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(r"overall verdict.*\*\*PASS\*\*", body, flags=re.IGNORECASE | re.DOTALL) is not None


def overnight_x_collection_canary_gate_ok() -> tuple[bool, str]:
    """Combined gate: fresh CSV PASS or explicit bypass env."""
    import os

    if os.getenv("X_REQUIRE_PROVIDER_CANARY_PASS", "1").strip().lower() in {"0", "false", "no", "off"}:
        return True, "bypass:X_REQUIRE_PROVIDER_CANARY_PASS=0"
    ok, reason = latest_canary_pass_from_csv(max_age_hours=24)
    if ok:
        return True, reason
    if canary_markdown_reports_pass():
        return True, "markdown_pass_flag"
    return False, reason
