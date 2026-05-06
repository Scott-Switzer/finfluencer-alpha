from __future__ import annotations

import math
from dataclasses import dataclass

from .config import Settings, get_settings
from .db import connect, init_db


class BudgetExceededError(RuntimeError):
    """Raised when a paid X command would exceed the configured hard budget."""


@dataclass(frozen=True)
class BudgetSnapshot:
    estimated_reads: int
    estimated_cost: float
    used_reads: int
    used_cost: float
    remaining_reads: int
    remaining_budget: float
    max_reads: int
    max_budget: float


def estimate_cost(post_reads: int, cost_per_post_read: float | None = None) -> float:
    settings = get_settings()
    cost = settings.x_cost_per_post_read if cost_per_post_read is None else cost_per_post_read
    return round(max(post_reads, 0) * cost, 4)


class BudgetGuard:
    def __init__(self, settings: Settings | None = None, database_url: str | None = None) -> None:
        self.settings = settings or get_settings()
        self.database_url = database_url

    @property
    def max_reads(self) -> int:
        cost_limited_reads = math.floor(
            self.settings.x_max_budget_usd / self.settings.x_cost_per_post_read
        )
        return min(self.settings.x_max_total_post_reads, cost_limited_reads)

    def estimate_cost(self, post_reads: int) -> float:
        return estimate_cost(post_reads, self.settings.x_cost_per_post_read)

    def used_reads(self) -> int:
        init_db(self.database_url)
        with connect(self.database_url) as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(
                  CASE
                    WHEN status = 'reserved' THEN estimated_reads
                    ELSE COALESCE(actual_reads, 0)
                  END
                ), 0) AS reads
                FROM x_budget_usage
                """
            ).fetchone()
        return int(row["reads"] or 0)

    def remaining_reads(self) -> int:
        return max(self.max_reads - self.used_reads(), 0)

    def remaining_budget(self) -> float:
        return round(self.remaining_reads() * self.settings.x_cost_per_post_read, 4)

    def snapshot(self, estimated_reads: int = 0) -> BudgetSnapshot:
        used_reads = self.used_reads()
        remaining_reads = max(self.max_reads - used_reads, 0)
        return BudgetSnapshot(
            estimated_reads=max(estimated_reads, 0),
            estimated_cost=self.estimate_cost(estimated_reads),
            used_reads=used_reads,
            used_cost=self.estimate_cost(used_reads),
            remaining_reads=remaining_reads,
            remaining_budget=self.estimate_cost(remaining_reads),
            max_reads=self.max_reads,
            max_budget=self.settings.x_max_budget_usd,
        )

    def assert_budget_available(self, estimated_reads: int, override_budget: bool = False) -> None:
        snapshot = self.snapshot(estimated_reads)
        if override_budget:
            return
        if estimated_reads > snapshot.remaining_reads:
            raise BudgetExceededError(
                "X budget guard blocked paid run: "
                f"estimated_reads={estimated_reads}, "
                f"estimated_cost=${snapshot.estimated_cost:.2f}, "
                f"remaining_reads={snapshot.remaining_reads}, "
                f"remaining_budget=${snapshot.remaining_budget:.2f}, "
                f"max_budget=${snapshot.max_budget:.2f}."
            )

    def reserve_budget(
        self,
        job_name: str,
        estimated_reads: int,
        details: str | None = None,
        override_budget: bool = False,
    ) -> int:
        self.assert_budget_available(estimated_reads, override_budget=override_budget)
        init_db(self.database_url)
        with connect(self.database_url) as conn:
            cursor = conn.execute(
                """
                INSERT INTO x_budget_usage (
                  job_name, estimated_reads, estimated_cost, actual_reads,
                  actual_cost, status, details
                )
                VALUES (?, ?, ?, 0, 0, 'reserved', ?)
                """,
                (job_name, estimated_reads, self.estimate_cost(estimated_reads), details),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def record_actual_usage(self, job_name: str, actual_reads: int) -> None:
        init_db(self.database_url)
        with connect(self.database_url) as conn:
            row = conn.execute(
                """
                SELECT usage_id
                FROM x_budget_usage
                WHERE job_name = ? AND status = 'reserved'
                ORDER BY created_at DESC, usage_id DESC
                LIMIT 1
                """,
                (job_name,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE x_budget_usage
                    SET actual_reads = ?, actual_cost = ?, status = 'recorded',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE usage_id = ?
                    """,
                    (actual_reads, self.estimate_cost(actual_reads), row["usage_id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO x_budget_usage (
                      job_name, estimated_reads, estimated_cost, actual_reads,
                      actual_cost, status
                    )
                    VALUES (?, ?, ?, ?, ?, 'recorded')
                    """,
                    (
                        job_name,
                        actual_reads,
                        self.estimate_cost(actual_reads),
                        actual_reads,
                        self.estimate_cost(actual_reads),
                    ),
                )
            conn.commit()

    def format_snapshot(self, estimated_reads: int, command_details: str) -> str:
        snapshot = self.snapshot(estimated_reads)
        return (
            f"Command: {command_details}\n"
            f"Estimated X post reads: {snapshot.estimated_reads:,}\n"
            f"Estimated cost: ${snapshot.estimated_cost:.2f}\n"
            f"Used budget: {snapshot.used_reads:,} reads (${snapshot.used_cost:.2f})\n"
            f"Remaining budget: {snapshot.remaining_reads:,} reads "
            f"(${snapshot.remaining_budget:.2f})\n"
            f"Hard maximum: {snapshot.max_reads:,} reads (${snapshot.max_budget:.2f})"
        )


def remaining_budget() -> float:
    return BudgetGuard().remaining_budget()


def assert_budget_available(estimated_reads: int, override_budget: bool = False) -> None:
    BudgetGuard().assert_budget_available(estimated_reads, override_budget=override_budget)


def reserve_budget(job_name: str, estimated_reads: int) -> int:
    return BudgetGuard().reserve_budget(job_name, estimated_reads)


def record_actual_usage(job_name: str, actual_reads: int) -> None:
    BudgetGuard().record_actual_usage(job_name, actual_reads)
