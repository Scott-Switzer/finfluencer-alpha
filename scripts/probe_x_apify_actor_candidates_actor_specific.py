#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

OUT_DIR = ROOT / "data/exports/overnight_collection"
OUT_CSV = OUT_DIR / "43_x_apify_actor_specific_probe.csv"
OUT_MD = OUT_DIR / "43_x_apify_actor_specific_probe.md"
OUT_PROFILE = OUT_DIR / "44_x_selected_provider_profile.md"
OUT_BLOCKER = OUT_DIR / "44_x_historical_collection_blocker_report.md"

ACTORS = [
    "api-ninja/x-twitter-advanced-search",
    "novi/twitter-x-api",
    "happitap/twitter-tweet-scraper",
]

QUERIES = [
    "$TSLA from:MeetKevin since:2021-01-01 until:2021-01-08 lang:en -filter:retweets",
    "$TSLA from:unusual_whales since:2021-01-01 until:2021-01-15 lang:en -filter:retweets",
    "$AAPL from:unusual_whales since:2021-01-01 until:2021-01-15 lang:en -filter:retweets",
    "$TSLA since:2021-01-01 until:2021-01-03 lang:en -filter:retweets",
]

WINDOW_START = int(datetime(2021, 1, 1, tzinfo=UTC).timestamp())
WINDOW_END = int(datetime(2021, 1, 15, 23, 59, 59, tzinfo=UTC).timestamp())


def _token() -> str:
    t = os.getenv("APIFY_TOKEN_1", "").strip() or os.getenv("APIFY_TOKEN", "").strip()
    if not t:
        raise SystemExit("Missing APIFY token")
    return t


def _actor_path(actor_id: str) -> str:
    return actor_id.replace("/", "~")


def _json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=True)
    except Exception:
        return ""


def _get_actor_meta(actor_id: str, token: str) -> dict[str, Any]:
    r = requests.get(
        f"https://api.apify.com/v2/acts/{_actor_path(actor_id)}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=40,
    )
    if r.status_code >= 400:
        return {"error_http_status": r.status_code, "error_text": r.text[:300]}
    try:
        body = r.json()
    except Exception:
        return {"error_http_status": r.status_code, "error_text": "non_json_meta"}
    data = body.get("data")
    return data if isinstance(data, dict) else {}


def _schema_properties(meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    schema = meta.get("inputSchema")
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties")
    return props if isinstance(props, dict) else {}


def _supports(props: dict[str, dict[str, Any]], *names: str) -> str | None:
    lower = {k.lower(): k for k in props.keys()}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def _parse_error(resp: requests.Response) -> tuple[str, str]:
    try:
        body = resp.json()
    except Exception:
        return "", f"http_{resp.status_code}"
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        return "", f"http_{resp.status_code}"
    return str(err.get("type") or ""), str(err.get("message") or "")[:220]


def _extract(item: dict[str, Any], paths: list[str]) -> Any:
    for path in paths:
        cur: Any = item
        ok = True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None, ""):
            return cur
    return None


def _parse_ts(v: Any) -> tuple[bool, int | None]:
    if v in (None, ""):
        return False, None
    s = str(v).strip()
    if not s:
        return False, None
    try:
        if s.isdigit() and len(s) >= 10:
            n = int(s)
            if len(s) >= 13:
                n //= 1000
            return True, n
        ts = int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
        return True, ts
    except Exception:
        return False, None


def _is_mock(item: dict[str, Any], text: str, pid: str) -> bool:
    if str(item.get("type", "")).lower() == "mock_tweet":
        return True
    if pid.strip() in {"-1", ""}:
        return True
    return "mock_tweet" in text.lower()


def _is_retweet(text: str) -> bool:
    t = text.strip().lower()
    return t.startswith("rt @") or t.startswith("rt ")


def _build_payload(actor_id: str, props: dict[str, dict[str, Any]], query: str) -> tuple[dict[str, Any], str]:
    payload: dict[str, Any] = {}
    used: list[str] = []

    def setf(field: str | None, value: Any) -> None:
        if not field:
            return
        payload[field] = value
        used.append(field)

    # shared terms
    setf(_supports(props, "query", "searchQuery", "search", "q"), query)
    setf(_supports(props, "searchTerms"), [query])

    # optional filters
    setf(_supports(props, "lang", "language", "tweetLanguage"), "en")
    setf(_supports(props, "since", "startDate", "timeSince"), "2021-01-01")
    setf(_supports(props, "until", "endDate", "timeUntil"), "2021-01-15")
    setf(_supports(props, "timeSinceUnix", "since_time"), 1609459200)
    setf(_supports(props, "timeUntilUnix", "until_time"), 1610755200)

    # max items / tweet count
    max_field = _supports(props, "maxItems", "max_items", "limit", "maxTweets")
    if max_field:
        setf(max_field, 20)
    num_field = _supports(props, "numberOfTweets")
    if num_field:
        setf(num_field, 20)

    sort_field = _supports(props, "sort", "searchType", "search_type")
    if sort_field:
        setf(sort_field, "Latest")

    # fallback minimum payload when schema missing: actor-specific
    if not payload:
        if "api-ninja/x-twitter-advanced-search" in actor_id:
            payload = {"query": query, "numberOfTweets": 20}
            used = ["query", "numberOfTweets"]
        elif "novi/twitter-x-api" in actor_id:
            payload = {"searchTerms": [query], "maxItems": 20, "tweetLanguage": "en", "sort": "Latest"}
            used = ["searchTerms", "maxItems", "tweetLanguage", "sort"]
        else:
            payload = {"searchTerms": [query], "maxItems": 20}
            used = ["searchTerms", "maxItems"]

    return payload, ",".join(used)


def main() -> None:
    token = _token()
    cap = float(os.getenv("X_ACTOR_PROBE_SESSION_CAP_USD", "0.25") or 0.25)
    rows: list[dict[str, Any]] = []
    spend_used = 0.0
    selected: dict[str, Any] | None = None
    started_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    for idx, actor_id in enumerate(ACTORS, start=1):
        if selected is not None:
            break
        meta = _get_actor_meta(actor_id, token)
        perm = str(meta.get("actorPermissionLevel") or "")
        if perm.upper() == "FULL_PERMISSIONS":
            rows.append(
                {
                    "provider_key": f"actor_{idx}",
                    "actor_id": actor_id,
                    "actorPermissionLevel": perm,
                    "attempted_input_shape": "",
                    "started": "0",
                    "run_status": "",
                    "http_status": "",
                    "error_type": "",
                    "returned_rows": "0",
                    "has_text_field": "false",
                    "has_created_at_field": "false",
                    "has_id_field": "false",
                    "created_at_parseable": "false",
                    "explicit_cashtag_detected": "false",
                    "inside_window_detected": "false",
                    "same_day_collapse_suspected": "false",
                    "mock_like_row_detected": "false",
                    "selected_for_strict_canary": "0",
                    "decision": "FULL_PERMISSION_SKIP",
                    "reason": "requires manual approval",
                }
            )
            continue

        props = _schema_properties(meta)
        actor_selected = False
        for query in QUERIES:
            if selected is not None or actor_selected or spend_used >= cap:
                break

            payload, shape = _build_payload(actor_id, props, query)
            row = {
                "provider_key": f"actor_{idx}",
                "actor_id": actor_id,
                "actorPermissionLevel": perm,
                "attempted_input_shape": shape or "actor_specific_fallback",
                "started": "0",
                "run_status": "",
                "http_status": "",
                "error_type": "",
                "returned_rows": "0",
                "has_text_field": "false",
                "has_created_at_field": "false",
                "has_id_field": "false",
                "created_at_parseable": "false",
                "explicit_cashtag_detected": "false",
                "inside_window_detected": "false",
                "same_day_collapse_suspected": "false",
                "mock_like_row_detected": "false",
                "selected_for_strict_canary": "0",
                "decision": "",
                "reason": "",
                "_query": query,
                "_payload": payload,
            }

            resp = requests.post(
                f"https://api.apify.com/v2/acts/{_actor_path(actor_id)}/runs",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=45,
            )
            row["http_status"] = str(resp.status_code)
            if resp.status_code >= 400:
                et, em = _parse_error(resp)
                row["error_type"] = et
                if et == "full-permission-actor-not-approved":
                    row["decision"] = "AUTH_BLOCKED_APPROVAL_REQUIRED"
                elif et == "actor-is-not-rented":
                    row["decision"] = "RENTAL_REQUIRED_SKIP"
                else:
                    row["decision"] = "START_FAILED"
                row["reason"] = em
                rows.append(row)
                continue

            row["started"] = "1"
            run = resp.json().get("data", {})
            run_id = str(run.get("id") or "")
            final = run

            for _ in range(10):
                if not run_id:
                    break
                st = requests.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30,
                )
                if st.status_code >= 400:
                    break
                data = st.json().get("data", {})
                if isinstance(data, dict):
                    final = data
                status = str(final.get("status") or "")
                if status in {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}:
                    break

            row["run_status"] = str(final.get("status") or "")
            usage = final.get("usage")
            if isinstance(usage, dict):
                try:
                    spend_used += float(usage.get("totalUsd") or 0.0)
                except Exception:
                    pass

            ds = str(final.get("defaultDatasetId") or "")
            items: list[dict[str, Any]] = []
            if ds:
                dresp = requests.get(
                    f"https://api.apify.com/v2/datasets/{ds}/items",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"limit": 1, "offset": 0, "clean": "1"},
                    timeout=30,
                )
                if dresp.status_code < 400:
                    try:
                        data = dresp.json()
                        if isinstance(data, list):
                            items = [x for x in data if isinstance(x, dict)]
                    except Exception:
                        pass
            row["returned_rows"] = str(len(items))
            if items:
                item = items[0]
                text = str(_extract(item, ["text", "full_text", "content", "tweetText", "tweet.text"]) or "")
                created_raw = _extract(item, ["created_at", "createdAt", "timestamp", "date", "time", "tweet.created_at"])
                pid = str(_extract(item, ["id", "tweet_id", "tweetId", "rest_id", "tweet.id"]) or "")
                author = str(_extract(item, ["author.username", "user.username", "username", "screen_name", "handle"]) or "")

                row["has_text_field"] = str(bool(text)).lower()
                row["has_created_at_field"] = str(created_raw not in (None, "")).lower()
                row["has_id_field"] = str(bool(pid)).lower()
                parse_ok, ts = _parse_ts(created_raw)
                row["created_at_parseable"] = str(parse_ok).lower()
                ticker_ok = ("$TSLA" in text) or ("$AAPL" in text)
                row["explicit_cashtag_detected"] = str(ticker_ok).lower()
                if parse_ok and ts is not None:
                    row["inside_window_detected"] = str(WINDOW_START <= ts <= WINDOW_END).lower()
                    row["same_day_collapse_suspected"] = str(
                        datetime.fromtimestamp(ts, UTC).date() == datetime.now(UTC).date()
                    ).lower()
                row["mock_like_row_detected"] = str(_is_mock(item, text, pid)).lower()

                intended_creator_ok = True
                if "from:MeetKevin" in query:
                    intended_creator_ok = "meetkevin" in author.lower()
                elif "from:unusual_whales" in query:
                    intended_creator_ok = "unusual_whales" in author.lower() or "unusualwhales" in author.lower()

                importable = (
                    bool(pid)
                    and bool(text.strip())
                    and parse_ok
                    and ticker_ok
                    and row["inside_window_detected"] == "true"
                    and row["same_day_collapse_suspected"] == "false"
                    and row["mock_like_row_detected"] == "false"
                    and not _is_retweet(text)
                    and intended_creator_ok
                )
                if importable:
                    row["selected_for_strict_canary"] = "1"
                    row["decision"] = "SELECT_FOR_STRICT_CANARY"
                    row["reason"] = "importable historical row detected"
                    actor_selected = True
                    selected = {
                        "actor_id": actor_id,
                        "payload": payload,
                        "query": query,
                        "returned_rows": row["returned_rows"],
                        "importable_rows": "1",
                        "detected_fields": {
                            "timestamp_field": "created_at/createdAt/timestamp/date",
                            "text_field": "text/full_text/content/tweetText",
                            "id_field": "id/tweet_id/tweetId/rest_id",
                            "author_field": "author.username/user.username/username",
                        },
                        "cost_estimate_usd": str(usage.get("totalUsd") if isinstance(usage, dict) else ""),
                    }
                else:
                    row["decision"] = "STARTED_QUALITY_NOT_PROVEN"
                    row["reason"] = "started but row not importable under strict research gates"
            else:
                row["decision"] = "STARTED_NO_ROWS"
                row["reason"] = "started but returned 0 rows"

            rows.append(row)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "provider_key",
        "actor_id",
        "actorPermissionLevel",
        "attempted_input_shape",
        "started",
        "run_status",
        "http_status",
        "error_type",
        "returned_rows",
        "has_text_field",
        "has_created_at_field",
        "has_id_field",
        "created_at_parseable",
        "explicit_cashtag_detected",
        "inside_window_detected",
        "same_day_collapse_suspected",
        "mock_like_row_detected",
        "selected_for_strict_canary",
        "decision",
        "reason",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    md = [
        "# Actor-specific X probe",
        "",
        f"Generated (UTC): `{started_at}`",
        "Session cap USD: `0.25`",
        f"Actors tested: `{', '.join(ACTORS)}`",
        "",
        "## Probe rows",
        "",
    ]
    for r in rows:
        md.append(
            f"- `{r['actor_id']}` started={r['started']} http={r['http_status'] or 'n/a'} "
            f"returned={r['returned_rows']} decision=`{r['decision']}` reason=`{r['reason']}`"
        )
    OUT_MD.write_text("\n".join(md).rstrip() + "\n", encoding="utf-8")

    if selected:
        profile = [
            "# Selected X provider profile",
            "",
            f"Selected actor id: `{selected['actor_id']}`",
            f"Exact query: `{selected['query']}`",
            "",
            "## Input payload used",
            "",
            "```json",
            _json(selected["payload"]),
            "```",
            "",
            f"Returned rows: `{selected['returned_rows']}`",
            f"Importable rows: `{selected['importable_rows']}`",
            f"Detected output schema fields: `{_json(selected['detected_fields'])}`",
            f"Cost/spend (if available): `{selected['cost_estimate_usd']}`",
            "",
            "## Limitations and methodology",
            "",
            "- This tiny probe validates schema viability and strict-row importability only.",
            "- Full research canary still required before any broad X collection.",
        ]
        OUT_PROFILE.write_text("\n".join(profile).rstrip() + "\n", encoding="utf-8")
        if OUT_BLOCKER.exists():
            OUT_BLOCKER.unlink()
    else:
        blocker = [
            "# Historical X collection blocker report",
            "",
            "No actor produced an importable strict historical row in this actor-specific probe.",
            "",
            "## Recommended path",
            "",
            "- Preferred: official X API full-archive access for defensible historical retrieval.",
            "- Fallback: forward-looking X collection while keeping YouTube event study as primary historical sample.",
            "- Under current actor/account constraints, historical X remains limitation/future work.",
        ]
        OUT_BLOCKER.write_text("\n".join(blocker).rstrip() + "\n", encoding="utf-8")
        if OUT_PROFILE.exists():
            OUT_PROFILE.unlink()

    print(f"WROTE_CSV={OUT_CSV.relative_to(ROOT)}")
    print(f"WROTE_MD={OUT_MD.relative_to(ROOT)}")
    print(f"SELECTED_ACTOR={selected['actor_id'] if selected else 'none'}")


if __name__ == "__main__":
    main()
