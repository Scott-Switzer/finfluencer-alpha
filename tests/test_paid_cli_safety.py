from pathlib import Path

from typer.testing import CliRunner

from finfluencer_alpha.cli import app
from finfluencer_alpha.config import get_settings


def test_collect_x_budgeted_requires_confirmation_before_count_or_collection(tmp_path: Path) -> None:
    get_settings.cache_clear()
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "collect-x-budgeted",
            "--start-date",
            "2020-01-01",
            "--end-date",
            "2026-05-06",
            "--budget",
            "50",
        ],
        env={
            "X_BEARER_TOKEN": "fake-token",
            "DATABASE_URL": f"sqlite:///{tmp_path / 'confirm_guard.db'}",
        },
    )
    assert result.exit_code == 1
    assert "Refusing paid X post retrieval" in result.output


def test_collect_x_budgeted_over_budget_exits_before_api_calls(tmp_path: Path) -> None:
    get_settings.cache_clear()
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "collect-x-budgeted",
            "--start-date",
            "2020-01-01",
            "--end-date",
            "2026-05-06",
            "--budget",
            "500",
            "--confirm-paid-run",
        ],
        env={
            "X_BEARER_TOKEN": "fake-token",
            "DATABASE_URL": f"sqlite:///{tmp_path / 'over_budget_guard.db'}",
        },
    )
    assert result.exit_code == 1
    assert "requested budget $500.00 exceeds" in result.output
    assert "X_MAX_BUDGET_USD=$50.00" in result.output


def test_enrich_x_budgeted_requires_confirmation_before_collection(tmp_path: Path) -> None:
    get_settings.cache_clear()
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "enrich-x-budgeted",
            "--budget",
            "10",
        ],
        env={
            "X_BEARER_TOKEN": "fake-token",
            "DATABASE_URL": f"sqlite:///{tmp_path / 'enrich_confirm_guard.db'}",
        },
    )
    assert result.exit_code == 1
    assert "Refusing paid X post retrieval" in result.output


def test_show_config_masks_api_keys(tmp_path: Path) -> None:
    get_settings.cache_clear()
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["show-config"],
        env={
            "X_BEARER_TOKEN": "x-secret-value",
            "YOUTUBE_API_KEY": "youtube-secret-value",
            "YOUTUBETRANSCRIPT_DEV_API_KEY": "yttdev-secret-value",
            "TRANSCRIPTAPI_KEY": "transcriptapi-secret-value",
            "DATABASE_URL": f"sqlite:///{tmp_path / 'config.db'}",
            "X_SEARCH_MODE": "all",
        },
    )
    assert result.exit_code == 0
    assert '"x_bearer_token": true' in result.output
    assert '"youtube_api_key": true' in result.output
    assert '"youtubetranscript_dev_api_key": true' in result.output
    assert '"transcriptapi_key": true' in result.output
    assert "x-secret-value" not in result.output
    assert "youtube-secret-value" not in result.output
    assert "yttdev-secret-value" not in result.output
    assert "transcriptapi-secret-value" not in result.output
