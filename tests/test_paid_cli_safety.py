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
