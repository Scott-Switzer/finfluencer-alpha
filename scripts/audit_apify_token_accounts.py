#!/usr/bin/env python3
"""No-paid-call Apify token identity/limit audit.

This script performs only GET requests:
- /v2/users/me
- /v2/users/me/limits
- /v2/users/me/usage/monthly
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

OUT_DIR = ROOT / "data" / "exports" / "overnight_collection"
OUT79_CSV = OUT_DIR / "79_apify_token_account_audit.csv"
OUT79_MD = OUT_DIR / "79_apify_token_account_audit.md"
OUT80_CSV = OUT_DIR / "80_apify_token_rotation_audit.csv"
OUT80_MD = OUT_DIR / "80_apify_token_rotation_audit.md"
PROBE75_CSV = OUT_DIR / "75_youtube_provider_probe.csv"
REPORT77_MD = OUT_DIR / "77_youtube_multi_provider_recovery_final_report.md"
DIAG66_CSV = OUT_DIR / "66_apify_key_status_diagnostic.csv"
LEDGER_CSV = OUT_DIR / "apify_key_usage_ledger.csv"

APIFY_BASE = "https://api.apify.com/v2"
TOKEN_LIKE_RE = re.compile(r"(?i)(bearer\s+[a-z0-9._-]{10,}|[a-z0-9]{20,})")


@dataclass
class TokenSlot:
    slot_number: str
    source_name: str
    token: str
    token_fingerprint: str
    token_length: int


def _clean(value: object) -> str:
    return str(value or "").strip()


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _sanitize_error(message: str, tokens: list[str]) -> str:
    out = message
    for tok in tokens:
        if tok:
            out = out.replace(tok, "[REDACTED_APIFY_TOKEN]")
    out = TOKEN_LIKE_RE.sub("[REDACTED_TOKENISH]", out)
    return out[:400]


def _extract_data(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload
    return {}


def _extract_first(data: dict[str, Any], candidates: list[str]) -> str:
    for key in candidates:
        if key in data and data.get(key) is not None:
            return _clean(data.get(key))
    return ""


def _extract_float(data: dict[str, Any], candidates: list[str]) -> float | None:
    for key in candidates:
        if key not in data:
            continue
        raw = data.get(key)
        if raw is None or _clean(raw) == "":
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_keys_csv(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return ",".join(sorted(str(k) for k in value.keys()))


def _extract_limits_fields(limits_data: dict[str, Any]) -> dict[str, object]:
    monthly_cycle = _as_dict(limits_data.get("monthlyUsageCycle"))
    limits_block = _as_dict(limits_data.get("limits"))
    current_block = _as_dict(limits_data.get("current"))

    cycle_start = _extract_first(
        monthly_cycle,
        ["startAt", "start", "from", "cycleStart", "cycleStartAt"],
    )
    cycle_end = _extract_first(
        monthly_cycle,
        ["endAt", "end", "to", "cycleEnd", "cycleEndAt"],
    )
    max_monthly = _extract_float(
        limits_block,
        ["maxMonthlyUsageUsd", "monthlyUsageLimitUsd", "maxMonthlyUsageCreditsUsd", "hardMonthlyUsdLimit"],
    )
    monthly_usage = _extract_float(
        current_block,
        ["monthlyUsageUsd", "usageUsd", "totalUsageUsd", "totalUsageCreditsUsdAfterVolumeDiscount"],
    )
    active_jobs = _extract_float(
        current_block,
        ["activeActorJobCount", "activeActorRuns", "activeJobs", "runningJobs"],
    )
    return {
        "cycle_start": cycle_start,
        "cycle_end": cycle_end,
        "max_monthly": max_monthly,
        "monthly_usage": monthly_usage,
        "active_jobs": active_jobs,
        "limits_top_level_keys": _dict_keys_csv(limits_data),
        "limits_data_keys": _dict_keys_csv(limits_data),
        "limits_limits_keys": _dict_keys_csv(limits_block),
        "limits_current_keys": _dict_keys_csv(current_block),
    }


def _extract_usage_fields(usage_data: dict[str, Any]) -> dict[str, object]:
    usage_inner = _as_dict(usage_data.get("data")) if "data" in usage_data else {}
    effective = usage_inner or usage_data
    total_after_discount = _extract_float(
        effective,
        ["totalUsageCreditsUsdAfterVolumeDiscount", "usageAfterVolumeDiscountUsd"],
    )
    cycle_start = _extract_first(
        effective,
        ["cycleStart", "cycleStartAt", "periodStart", "periodStartAt", "from"],
    )
    cycle_end = _extract_first(
        effective,
        ["cycleEnd", "cycleEndAt", "periodEnd", "periodEndAt", "to"],
    )
    return {
        "total_after_discount": total_after_discount,
        "cycle_start": cycle_start,
        "cycle_end": cycle_end,
        "usage_monthly_top_level_keys": _dict_keys_csv(usage_data),
        "usage_monthly_data_keys": _dict_keys_csv(effective),
    }


def _get_json(url: str, token: str) -> tuple[int, dict[str, Any], str, str]:
    try:
        response = requests.get(url, headers=_headers(token), timeout=45)
    except requests.RequestException as exc:
        return 0, {}, "request_exception", _clean(exc)
    status = int(response.status_code)
    try:
        payload = response.json()
    except ValueError:
        return status, {}, "non_json", _clean(response.text)[:300]
    if status >= 400:
        error = payload.get("error") if isinstance(payload, dict) else {}
        if isinstance(error, dict):
            return (
                status,
                {},
                _clean(error.get("type")) or f"http_{status}",
                _clean(error.get("message")) or f"http_{status}",
            )
        return status, {}, f"http_{status}", _clean(payload)[:300]
    return status, _extract_data(payload), "", ""


def _collect_slots() -> tuple[list[TokenSlot], dict[str, str]]:
    raw_count = _clean(os.getenv("APIFY_TOKEN_COUNT")) or "0"
    try:
        configured_count = int(raw_count)
    except ValueError:
        configured_count = 0

    slots: list[TokenSlot] = []
    missing_map: dict[str, str] = {}
    if configured_count > 0:
        for i in range(1, configured_count + 1):
            name = f"APIFY_TOKEN_{i}"
            token = _clean(os.getenv(name))
            if not token:
                missing_map[str(i)] = "missing_in_environment"
                continue
            slots.append(
                TokenSlot(
                    slot_number=str(i),
                    source_name=name,
                    token=token,
                    token_fingerprint=_token_fingerprint(token),
                    token_length=len(token),
                )
            )
    fallback = _clean(os.getenv("APIFY_TOKEN"))
    if fallback:
        slots.append(
            TokenSlot(
                slot_number="fallback",
                source_name="APIFY_TOKEN",
                token=fallback,
                token_fingerprint=_token_fingerprint(fallback),
                token_length=len(fallback),
            )
        )
    return slots, {"configured_count": str(configured_count), **missing_map}


def _run_account_audit(slots: list[TokenSlot]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    all_tokens = [s.token for s in slots]
    for slot in slots:
        me_status, me_data, me_err_type, me_err_msg = _get_json(f"{APIFY_BASE}/users/me", slot.token)
        limits_status, limits_data, limits_err_type, limits_err_msg = _get_json(
            f"{APIFY_BASE}/users/me/limits", slot.token
        )
        usage_status, usage_data, usage_err_type, usage_err_msg = _get_json(
            f"{APIFY_BASE}/users/me/usage/monthly", slot.token
        )

        auth_valid = int(200 <= me_status < 300)
        user_id = _extract_first(me_data, ["id", "userId", "accountId"])
        username = _extract_first(me_data, ["username", "userName", "name"])
        account_owner = _extract_first(
            me_data,
            [
                "accountId",
                "billingUserId",
                "billingOwnerId",
                "organizationId",
                "orgId",
                "teamId",
                "currentTeamId",
            ],
        )
        limits_fields = _extract_limits_fields(limits_data)
        usage_fields = _extract_usage_fields(usage_data)
        cycle_start = _clean(limits_fields["cycle_start"]) or _clean(usage_fields["cycle_start"])
        cycle_end = _clean(limits_fields["cycle_end"]) or _clean(usage_fields["cycle_end"])
        max_monthly = limits_fields["max_monthly"]
        monthly_usage = limits_fields["monthly_usage"]
        if monthly_usage in (None, ""):
            monthly_usage = _extract_float(
                _as_dict(usage_data),
                [
                    "monthlyUsageUsd",
                    "usageUsd",
                    "totalUsageUsd",
                    "totalUsageCreditsUsdAfterVolumeDiscount",
                ],
            )
        total_after_discount = usage_fields["total_after_discount"]
        active_jobs = limits_fields["active_jobs"]
        remaining = (max_monthly - monthly_usage) if (max_monthly is not None and monthly_usage is not None) else None

        error_type = me_err_type or limits_err_type or usage_err_type
        error_msg = me_err_msg or limits_err_msg or usage_err_msg
        row = {
            "slot_number": slot.slot_number,
            "token_source": slot.source_name,
            "token_fingerprint": slot.token_fingerprint,
            "token_length": slot.token_length,
            "auth_valid": auth_valid,
            "user_id": user_id,
            "username": username,
            "account_owner_id": account_owner,
            "monthly_usage_cycle_start": cycle_start,
            "monthly_usage_cycle_end": cycle_end,
            "maxMonthlyUsageUsd": max_monthly if max_monthly is not None else "",
            "monthlyUsageUsd": monthly_usage if monthly_usage is not None else "",
            "totalUsageCreditsUsdAfterVolumeDiscount": total_after_discount if total_after_discount is not None else "",
            "remainingMonthlyUsageUsd": remaining if remaining is not None else "",
            "activeActorJobCount": int(active_jobs) if active_jobs is not None else "",
            "users_me_http_status": me_status,
            "limits_http_status": limits_status,
            "users_me_limits_http_status": limits_status,
            "users_me_usage_monthly_http_status": usage_status,
            "limits_top_level_keys": limits_fields["limits_top_level_keys"],
            "limits_data_keys": limits_fields["limits_data_keys"],
            "limits_limits_keys": limits_fields["limits_limits_keys"],
            "limits_current_keys": limits_fields["limits_current_keys"],
            "usage_monthly_top_level_keys": usage_fields["usage_monthly_top_level_keys"],
            "usage_monthly_data_keys": usage_fields["usage_monthly_data_keys"],
            "error_type": error_type,
            "error_message_sanitized": _sanitize_error(error_msg, all_tokens),
        }
        rows.append(row)
    return rows


def _summarize_rows(rows: list[dict[str, object]], meta: dict[str, str]) -> dict[str, object]:
    fingerprints = {_clean(r["token_fingerprint"]) for r in rows if _clean(r["token_fingerprint"])}
    user_keys = {
        f"{_clean(r['user_id'])}|{_clean(r['username'])}|{_clean(r['account_owner_id'])}"
        for r in rows
        if _clean(r["user_id"]) or _clean(r["username"]) or _clean(r["account_owner_id"])
    }
    cycle_keys = {
        f"{_clean(r['monthly_usage_cycle_start'])}|{_clean(r['monthly_usage_cycle_end'])}"
        for r in rows
        if _clean(r["monthly_usage_cycle_start"]) or _clean(r["monthly_usage_cycle_end"])
    }
    distinct_limits_usage = {
        f"{_clean(r['maxMonthlyUsageUsd'])}|{_clean(r['monthlyUsageUsd'])}" for r in rows
    }
    duplicates = len(fingerprints) < len(rows)
    fallback = [r for r in rows if _clean(r["slot_number"]) == "fallback"]
    fallback_same_indexed = False
    if fallback:
        fpr = _clean(fallback[0]["token_fingerprint"])
        fallback_same_indexed = any(
            _clean(r["slot_number"]) != "fallback" and _clean(r["token_fingerprint"]) == fpr
            for r in rows
        )

    remaining_values = [
        float(r["remainingMonthlyUsageUsd"])
        for r in rows
        if _clean(r["remainingMonthlyUsageUsd"]) not in {"", "None"}
    ]
    capped = any(val <= 0.0 for val in remaining_values) if remaining_values else False
    return {
        "visible_slots": len(rows),
        "configured_slot_count": int(meta.get("configured_count", "0") or "0"),
        "missing_slots": sorted([k for k in meta.keys() if k != "configured_count"]),
        "unique_token_fingerprints": len(fingerprints),
        "unique_user_accounts": len(user_keys),
        "unique_monthly_cycles": len(cycle_keys),
        "distinct_limit_usage_pairs": len(distinct_limits_usage),
        "duplicate_tokens_present": duplicates,
        "fallback_matches_indexed": fallback_same_indexed,
        "auth_valid_slots": sum(1 for r in rows if int(r.get("auth_valid") or 0) == 1),
        "capped_or_zero_remaining_detected": capped,
    }


def _write_79(rows: list[dict[str, object]], summary: dict[str, object], meta: dict[str, str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "slot_number",
        "token_source",
        "token_fingerprint",
        "token_length",
        "auth_valid",
        "user_id",
        "username",
        "account_owner_id",
        "monthly_usage_cycle_start",
        "monthly_usage_cycle_end",
        "maxMonthlyUsageUsd",
        "monthlyUsageUsd",
        "totalUsageCreditsUsdAfterVolumeDiscount",
        "remainingMonthlyUsageUsd",
        "activeActorJobCount",
        "users_me_http_status",
        "limits_http_status",
        "users_me_limits_http_status",
        "users_me_usage_monthly_http_status",
        "limits_top_level_keys",
        "limits_data_keys",
        "limits_limits_keys",
        "limits_current_keys",
        "usage_monthly_top_level_keys",
        "usage_monthly_data_keys",
        "error_type",
        "error_message_sanitized",
    ]
    with OUT79_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    lines = [
        "# Apify token account audit",
        "",
        f"Generated UTC: `{_iso_now()}`",
        f"Configured APIFY_TOKEN_COUNT: `{summary['configured_slot_count']}`",
        f"Visible token slots: `{summary['visible_slots']}`",
        f"Auth-valid slots: `{summary['auth_valid_slots']}`",
        f"Unique token fingerprints: `{summary['unique_token_fingerprints']}`",
        f"Unique Apify users/accounts: `{summary['unique_user_accounts']}`",
        f"Unique monthly usage cycles: `{summary['unique_monthly_cycles']}`",
        f"Duplicate token strings present: `{summary['duplicate_tokens_present']}`",
        f"Fallback APIFY_TOKEN matches indexed token: `{summary['fallback_matches_indexed']}`",
        f"Missing configured slots: `{json.dumps(summary['missing_slots'])}`",
        "",
        "## Direct answers",
        "",
    ]
    if summary["unique_user_accounts"] <= 1 and summary["visible_slots"] > 1:
        lines.append("- Conclusion: multiple token slots likely map to the same account/usage pool.")
    elif summary["unique_user_accounts"] > 1:
        lines.append("- Conclusion: tokens span multiple distinct users/accounts.")
    else:
        lines.append("- Conclusion: insufficient identity data to prove account separation.")

    if summary["capped_or_zero_remaining_detected"]:
        lines.append("- Monthly usage appears capped or at zero remaining for at least one account.")
    else:
        lines.append("- No explicit zero remaining usage found from limits/usage endpoints.")
    lines.append("- Prior `Monthly usage hard limit exceeded` responses are consistent with account-level caps when remaining is zero/negative.")
    lines.append("- This report does not run actors and does not spend credits.")
    lines.append("")
    lines.append("## Slot rows")
    lines.append("")
    for row in rows:
        lines.append(
            f"- slot `{row['slot_number']}` fp=`{row['token_fingerprint']}` auth={row['auth_valid']} "
            f"user=`{row['user_id'] or row['username'] or 'unknown'}` "
            f"remaining=`{row['remainingMonthlyUsageUsd'] if _clean(row['remainingMonthlyUsageUsd']) else 'n/a'}` "
            f"err=`{row['error_type'] or 'none'}`"
        )
    lines.append("")
    OUT79_MD.write_text("\n".join(lines), encoding="utf-8")


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_80(rows79: list[dict[str, object]], summary79: dict[str, object]) -> None:
    probe_rows = _read_csv(PROBE75_CSV)
    diag_rows = _read_csv(DIAG66_CSV)
    ledger_rows = _read_csv(LEDGER_CSV)
    report77 = _read_text(REPORT77_MD)

    probe_slot_counts: dict[str, int] = {}
    probe_decisions: dict[str, int] = {}
    for row in probe_rows:
        slot = _clean(row.get("token_slot_number")) or "unknown"
        probe_slot_counts[slot] = probe_slot_counts.get(slot, 0) + 1
        dec = _clean(row.get("decision")) or "unknown"
        probe_decisions[dec] = probe_decisions.get(dec, 0) + 1

    diag_slots_visible = sorted({_clean(r.get("slot_number")) for r in diag_rows if _clean(r.get("slot_number"))})
    diag_available = sorted(
        _clean(r.get("slot_number"))
        for r in diag_rows
        if _clean(r.get("available_for_actor_runs")) == "1"
    )

    youtube_ledger = [r for r in ledger_rows if _clean(r.get("platform")).lower() == "youtube"]
    youtube_labels = sorted({_clean(r.get("key_label")) for r in youtube_ledger if _clean(r.get("key_label"))})
    start_403 = [
        r for r in youtube_ledger
        if "HTTP 403" in _clean(r.get("reason")) or "hard limit exceeded" in _clean(r.get("reason")).lower()
    ]

    stop_reason = ""
    for line in report77.splitlines():
        if "final_stop_reason:" in line:
            stop_reason = line.split(":", 1)[1].strip().strip("`")
            break

    rotation_bug_likely = False
    rotation_bug_reason = ""
    if probe_slot_counts.get("unknown", 0) == len(probe_rows) and probe_rows:
        rotation_bug_likely = True
        rotation_bug_reason = "probe_reporting_unknown_slot_for_all_rows"
    if len(youtube_labels) <= 1 and int(summary79.get("visible_slots") or 0) > 1:
        rotation_bug_likely = True
        rotation_bug_reason = (rotation_bug_reason + ";single_label_in_youtube_ledger").strip(";")

    fields = [
        "metric",
        "value",
        "notes",
    ]
    out_rows = [
        {"metric": "probe_rows_total", "value": str(len(probe_rows)), "notes": ""},
        {"metric": "probe_slot_counts", "value": json.dumps(probe_slot_counts, sort_keys=True), "notes": ""},
        {"metric": "probe_decisions", "value": json.dumps(probe_decisions, sort_keys=True), "notes": ""},
        {"metric": "diag66_slots_visible", "value": json.dumps(diag_slots_visible), "notes": ""},
        {"metric": "diag66_slots_available_for_actor_runs", "value": json.dumps(diag_available), "notes": ""},
        {"metric": "youtube_ledger_key_labels", "value": json.dumps(youtube_labels), "notes": ""},
        {"metric": "youtube_ledger_403_or_limit_rows", "value": str(len(start_403)), "notes": ""},
        {"metric": "report77_stop_reason", "value": stop_reason, "notes": ""},
        {"metric": "rotation_bug_likely", "value": str(rotation_bug_likely), "notes": rotation_bug_reason},
    ]
    with OUT80_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(out_rows)

    lines = [
        "# Apify token rotation audit",
        "",
        f"Generated UTC: `{_iso_now()}`",
        "",
        f"- Probe rows in `75`: `{len(probe_rows)}`",
        f"- Provider probe slot distribution: `{json.dumps(probe_slot_counts, sort_keys=True)}`",
        f"- Provider probe decisions: `{json.dumps(probe_decisions, sort_keys=True)}`",
        f"- `66` visible slots: `{json.dumps(diag_slots_visible)}`",
        f"- `66` available_for_actor_runs slots: `{json.dumps(diag_available)}`",
        f"- YouTube ledger key labels observed: `{json.dumps(youtube_labels)}`",
        f"- YouTube ledger 403/limit rows: `{len(start_403)}`",
        f"- `77` final stop reason: `{stop_reason or 'unknown'}`",
        "",
        "## Interpretation",
        "",
    ]
    all_slots_tested = (
        "yes" if probe_slot_counts and set(probe_slot_counts.keys()) != {"unknown"} and len(probe_slot_counts) >= int(summary79.get("visible_slots") or 0) else "no_or_not_provable"
    )
    lines.append(f"- Were all slots tested in provider probe? `{all_slots_tested}`")
    lines.append("- Probe currently cannot prove slot coverage when `token_slot_number` is `unknown` for all rows.")
    if rotation_bug_likely:
        lines.append("- Runner/probe bug likely: token slot reporting/rotation evidence is insufficient; code patch recommended.")
    else:
        lines.append("- Runner/probe bug likely: not indicated by available evidence.")
    lines.append("- `STOP_NO_PROVIDER_PASSED_CANARY` was emitted, but slot-level attribution in `75` is incomplete.")
    lines.append("")
    OUT80_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    slots, meta = _collect_slots()
    rows79 = _run_account_audit(slots)
    summary79 = _summarize_rows(rows79, meta)
    _write_79(rows79, summary79, meta)
    _write_80(rows79, summary79)
    print(f"WROTE_79_CSV={OUT79_CSV.relative_to(ROOT)}")
    print(f"WROTE_79_MD={OUT79_MD.relative_to(ROOT)}")
    print(f"WROTE_80_CSV={OUT80_CSV.relative_to(ROOT)}")
    print(f"WROTE_80_MD={OUT80_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
