from __future__ import annotations

import importlib


def test_limits_parser_reads_nested_fields() -> None:
    mod = importlib.import_module("scripts.audit_apify_token_accounts")
    parsed = mod._extract_limits_fields(
        {
            "monthlyUsageCycle": {
                "startAt": "2026-05-01T00:00:00.000Z",
                "endAt": "2026-05-31T23:59:59.999Z",
            },
            "limits": {
                "maxMonthlyUsageUsd": 25.0,
            },
            "current": {
                "monthlyUsageUsd": 8.5,
                "activeActorJobCount": 2,
            },
        }
    )
    assert parsed["cycle_start"] == "2026-05-01T00:00:00.000Z"
    assert parsed["cycle_end"] == "2026-05-31T23:59:59.999Z"
    assert parsed["max_monthly"] == 25.0
    assert parsed["monthly_usage"] == 8.5
    assert parsed["active_jobs"] == 2.0


def test_shape_diagnostics_written_when_fields_missing() -> None:
    mod = importlib.import_module("scripts.audit_apify_token_accounts")
    parsed_limits = mod._extract_limits_fields({"foo": {"bar": 1}})
    assert parsed_limits["limits_top_level_keys"] == "foo"
    assert parsed_limits["limits_limits_keys"] == ""
    assert parsed_limits["limits_current_keys"] == ""
    parsed_usage = mod._extract_usage_fields({"data": {"totalUsageCreditsUsdAfterVolumeDiscount": 1.0}})
    assert "data" in parsed_usage["usage_monthly_top_level_keys"]
    assert "totalUsageCreditsUsdAfterVolumeDiscount" in parsed_usage["usage_monthly_data_keys"]
