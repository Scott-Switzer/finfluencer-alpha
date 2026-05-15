from pathlib import Path

import pytest

from finfluencer_alpha.apify_key_manager import (
    ApifyBudgetError,
    ApifyKeyManager,
    classify_apify_key_failure,
)


def test_reads_indexed_keys_and_labels(tmp_path: Path) -> None:
    manager = ApifyKeyManager.from_env(
        {
            "APIFY_TOKEN_COUNT": "2",
            "APIFY_TOKEN_1": "secret-one",
            "APIFY_TOKEN_1_LABEL": "main",
            "APIFY_TOKEN_2": "secret-two",
            "APIFY_TOKEN_2_LABEL": "backup",
            "APIFY_GLOBAL_MAX_TOTAL_USD": "10",
        },
        ledger_path=tmp_path / "ledger.csv",
    )

    assert manager.labels == ["main", "backup"]
    assert manager.safe_summary()["token_count"] == 2


def test_does_not_print_token_values(tmp_path: Path) -> None:
    manager = ApifyKeyManager.from_env(
        {
            "APIFY_TOKEN_COUNT": "1",
            "APIFY_TOKEN_1": "very-secret-token",
            "APIFY_TOKEN_1_LABEL": "safe_label",
        },
        ledger_path=tmp_path / "ledger.csv",
    )

    rendered = repr(manager.keys[0]) + str(manager.safe_summary())
    assert "very-secret-token" not in rendered
    assert manager.redact_text("token=very-secret-token") == "token=[REDACTED_APIFY_TOKEN]"


def test_respects_per_key_cap(tmp_path: Path) -> None:
    manager = ApifyKeyManager.from_env(
        {
            "APIFY_TOKEN_COUNT": "1",
            "APIFY_TOKEN_1": "secret-one",
            "APIFY_TOKEN_1_LABEL": "main",
            "APIFY_TOKEN_1_MAX_TOTAL_USD": "1.00",
            "APIFY_GLOBAL_MAX_TOTAL_USD": "5.00",
        },
        ledger_path=tmp_path / "ledger.csv",
    )
    manager.record_run(key_label="main", platform="x", cost_usd=0.75)

    with pytest.raises(ApifyBudgetError):
        manager.choose_key(platform="x", projected_cost_usd=0.30)


def test_respects_global_cap(tmp_path: Path) -> None:
    manager = ApifyKeyManager.from_env(
        {
            "APIFY_TOKEN_COUNT": "2",
            "APIFY_TOKEN_1": "secret-one",
            "APIFY_TOKEN_1_LABEL": "main",
            "APIFY_TOKEN_2": "secret-two",
            "APIFY_TOKEN_2_LABEL": "backup",
            "X_TOTAL_COST_CAP_USD": "1.00",
        },
        ledger_path=tmp_path / "ledger.csv",
    )
    manager.record_run(key_label="main", platform="x", cost_usd=0.90)

    with pytest.raises(ApifyBudgetError):
        manager.choose_key(platform="x", projected_cost_usd=0.20)


def test_rotates_exhausted_key(tmp_path: Path) -> None:
    manager = ApifyKeyManager.from_env(
        {
            "APIFY_TOKEN_COUNT": "2",
            "APIFY_TOKEN_1": "secret-one",
            "APIFY_TOKEN_1_LABEL": "main",
            "APIFY_TOKEN_1_MAX_TOTAL_USD": "0.50",
            "APIFY_TOKEN_2": "secret-two",
            "APIFY_TOKEN_2_LABEL": "backup",
            "APIFY_TOKEN_2_MAX_TOTAL_USD": "5.00",
            "X_TOTAL_COST_CAP_USD": "5.00",
        },
        ledger_path=tmp_path / "ledger.csv",
    )
    manager.record_run(key_label="main", platform="x", cost_usd=0.50)

    assert manager.choose_key(platform="x", projected_cost_usd=0.10).label == "backup"


def test_falls_back_to_single_apify_token(tmp_path: Path) -> None:
    manager = ApifyKeyManager.from_env(
        {"APIFY_TOKEN": "fallback-secret", "APIFY_TOKEN_LABEL": "fallback"},
        ledger_path=tmp_path / "ledger.csv",
    )

    assert manager.labels == ["fallback"]


def test_loads_eleven_keys_in_order(tmp_path: Path) -> None:
    env: dict[str, str] = {"APIFY_TOKEN_COUNT": "11", "APIFY_GLOBAL_MAX_TOTAL_USD": "100"}
    for i in range(1, 12):
        env[f"APIFY_TOKEN_{i}"] = f"tok-{i}"
        env[f"APIFY_TOKEN_{i}_LABEL"] = f"k{i}"
    manager = ApifyKeyManager.from_env(env, ledger_path=tmp_path / "ledger.csv")
    assert manager.labels == [f"k{i}" for i in range(1, 12)]


def test_session_cap_blocks_additional_spend(tmp_path: Path) -> None:
    manager = ApifyKeyManager.from_env(
        {
            "APIFY_TOKEN_COUNT": "2",
            "APIFY_TOKEN_1": "a",
            "APIFY_TOKEN_1_LABEL": "k1",
            "APIFY_TOKEN_2": "b",
            "APIFY_TOKEN_2_LABEL": "k2",
            "APIFY_GLOBAL_MAX_TOTAL_USD": "50",
            "APIFY_SESSION_MAX_TOTAL_USD": "0.40",
        },
        ledger_path=tmp_path / "ledger.csv",
    )
    manager.begin_session()
    manager.record_run(key_label="k1", platform="x", cost_usd=0.25, status="SUCCEEDED")
    manager.record_run(key_label="k2", platform="x", cost_usd=0.10, status="SUCCEEDED")
    with pytest.raises(ApifyBudgetError, match="session budget"):
        manager.choose_key(platform="x", projected_cost_usd=0.10)


def test_credit_failure_rotates_to_next_key(tmp_path: Path) -> None:
    manager = ApifyKeyManager.from_env(
        {
            "APIFY_TOKEN_COUNT": "2",
            "APIFY_TOKEN_1": "a",
            "APIFY_TOKEN_1_LABEL": "old",
            "APIFY_TOKEN_2": "b",
            "APIFY_TOKEN_2_LABEL": "new",
            "APIFY_GLOBAL_MAX_TOTAL_USD": "50",
            "APIFY_DISABLE_KEY_ON_CREDIT_ERROR": "false",
        },
        ledger_path=tmp_path / "ledger.csv",
    )
    manager.begin_session()
    assert manager.choose_key(platform="x", projected_cost_usd=0.01).label == "old"
    assert manager.note_key_failure_for_rotation("old", "HTTP 402: payment required", platform="x")
    assert manager.choose_key(platform="x", projected_cost_usd=0.01).label == "new"


def test_auth_failure_disables_when_configured(tmp_path: Path) -> None:
    manager = ApifyKeyManager.from_env(
        {
            "APIFY_TOKEN_COUNT": "2",
            "APIFY_TOKEN_1": "a",
            "APIFY_TOKEN_1_LABEL": "bad",
            "APIFY_TOKEN_2": "b",
            "APIFY_TOKEN_2_LABEL": "good",
            "APIFY_GLOBAL_MAX_TOTAL_USD": "50",
            "APIFY_DISABLE_KEY_ON_AUTH_ERROR": "true",
        },
        ledger_path=tmp_path / "ledger.csv",
    )
    manager.begin_session()
    assert manager.choose_key(platform="x", projected_cost_usd=0.01).label == "bad"
    assert manager.note_key_failure_for_rotation("bad", "HTTP 401: unauthorized", platform="x")
    assert manager.keys[0].disabled_reason
    assert manager.choose_key(platform="x", projected_cost_usd=0.01).label == "good"


def test_failed_run_without_key_health_does_not_disable_key(tmp_path: Path) -> None:
    manager = ApifyKeyManager.from_env(
        {
            "APIFY_TOKEN_COUNT": "1",
            "APIFY_TOKEN_1": "a",
            "APIFY_TOKEN_1_LABEL": "solo",
            "APIFY_GLOBAL_MAX_TOTAL_USD": "50",
        },
        ledger_path=tmp_path / "ledger.csv",
    )
    manager.begin_session()
    manager.record_run(
        key_label="solo",
        platform="x",
        status="failed",
        reason="dataset empty after normalization",
        cost_usd=0.0,
        key_health_failure=False,
    )
    assert manager.keys[0].disabled_reason is None
    assert manager.keys[0].failure_count == 0


def test_classify_ignores_quality_failures() -> None:
    assert classify_apify_key_failure("timestamp mismatch on posts") is None
    assert classify_apify_key_failure("HTTP 402 payment required") == "credit"


def test_non_health_failure_keeps_rotation_possible(tmp_path: Path) -> None:
    manager = ApifyKeyManager.from_env(
        {
            "APIFY_TOKEN_COUNT": "2",
            "APIFY_TOKEN_1": "a",
            "APIFY_TOKEN_1_LABEL": "k1",
            "APIFY_TOKEN_2": "b",
            "APIFY_TOKEN_2_LABEL": "k2",
            "APIFY_GLOBAL_MAX_TOTAL_USD": "50",
        },
        ledger_path=tmp_path / "ledger.csv",
    )
    manager.begin_session()
    assert manager.choose_key(platform="youtube", projected_cost_usd=0.01).label == "k1"
    # Transcript-level/content failures should not classify key health as exhausted.
    assert manager.note_key_failure_for_rotation(
        "k1",
        "TranscriptNotFound: subtitles are disabled for this video",
        platform="youtube",
    )
    assert manager.choose_key(platform="youtube", projected_cost_usd=0.01).label in {"k1", "k2"}


def test_activate_key_sets_process_environment_without_leaking(monkeypatch, tmp_path: Path) -> None:
    manager = ApifyKeyManager.from_env(
        {"APIFY_TOKEN": "fallback-secret", "APIFY_TOKEN_LABEL": "fallback"},
        ledger_path=tmp_path / "ledger.csv",
    )
    monkeypatch.delenv("APIFY_TOKEN", raising=False)

    with manager.activate_key(manager.keys[0]) as label:
        assert label == "fallback"
        assert manager.redact_text("fallback-secret") == "[REDACTED_APIFY_TOKEN]"

    assert "APIFY_TOKEN" not in __import__("os").environ
