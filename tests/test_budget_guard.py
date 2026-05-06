from pathlib import Path

import pytest

from finfluencer_alpha.budget_guard import BudgetExceededError, BudgetGuard, estimate_cost
from finfluencer_alpha.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'budget.db'}",
        x_cost_per_post_read=0.005,
        x_max_budget_usd=50,
        x_max_total_post_reads=10_000,
    )


def test_50_dollar_budget_converts_to_10000_reads(tmp_path: Path) -> None:
    guard = BudgetGuard(settings=_settings(tmp_path), database_url=f"sqlite:///{tmp_path / 'budget.db'}")
    assert guard.max_reads == 10_000
    assert estimate_cost(10_000, 0.005) == 50.0


def test_budget_hard_stop_blocks_reads_over_remaining_budget(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'budget.db'}"
    guard = BudgetGuard(settings=_settings(tmp_path), database_url=database_url)
    guard.reserve_budget("existing", 10_000)
    with pytest.raises(BudgetExceededError):
        guard.assert_budget_available(1)
