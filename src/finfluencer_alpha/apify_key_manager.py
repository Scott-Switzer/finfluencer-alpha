from __future__ import annotations

import csv
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from .config import PROJECT_ROOT

DEFAULT_LEDGER_PATH = PROJECT_ROOT / "data/exports/overnight_collection/apify_key_usage_ledger.csv"


class ApifyBudgetError(RuntimeError):
    """Raised when no Apify key can be used without crossing configured caps."""


def _clean(value: object) -> str:
    return str(value or "").strip()


def _float_or_none(value: object) -> float | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int_or_zero(value: object) -> int:
    text = _clean(value)
    if not text:
        return 0
    try:
        return int(text)
    except ValueError:
        return 0


@dataclass
class ApifyKey:
    label: str
    token: str = field(repr=False)
    max_total_usd: float | None = None
    min_remaining_usd: float | None = None
    spent_usd: float = 0.0
    failure_count: int = 0
    disabled_reason: str | None = None

    def can_spend(self, projected_cost_usd: float = 0.0) -> bool:
        if self.disabled_reason:
            return False
        if self.max_total_usd is None:
            return True
        return self.spent_usd + max(projected_cost_usd, 0.0) <= self.max_total_usd + 1e-9

    def public_summary(self) -> dict[str, object]:
        return {
            "label": self.label,
            "max_total_usd": self.max_total_usd,
            "min_remaining_usd": self.min_remaining_usd,
            "spent_usd": round(self.spent_usd, 6),
            "failure_count": self.failure_count,
            "disabled_reason": self.disabled_reason or "",
        }


@dataclass
class ApifyBudgetConfig:
    global_max_total_usd: float | None = None
    global_min_remaining_usd: float | None = None
    x_total_cost_cap_usd: float | None = None
    youtube_transcript_total_cost_cap_usd: float | None = None

    def cap_for_platform(self, platform: str) -> float | None:
        normalized = platform.strip().lower()
        if normalized == "x":
            return self.x_total_cost_cap_usd or self.global_max_total_usd
        if normalized == "youtube":
            return self.youtube_transcript_total_cost_cap_usd or self.global_max_total_usd
        return self.global_max_total_usd


class ApifyKeyManager:
    def __init__(
        self,
        keys: list[ApifyKey],
        budget: ApifyBudgetConfig | None = None,
        ledger_path: Path | None = None,
        max_failures_per_key: int = 3,
    ) -> None:
        if not keys:
            raise ApifyBudgetError("No Apify tokens are configured.")
        self.keys = keys
        self.budget = budget or ApifyBudgetConfig()
        self.ledger_path = ledger_path or DEFAULT_LEDGER_PATH
        self.max_failures_per_key = max_failures_per_key
        self._cursor = 0
        self.platform_spend: dict[str, float] = {}
        self._load_existing_ledger()
        self._sync_key_spend_from_ledger()
        self.ensure_ledger()

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        ledger_path: Path | None = None,
    ) -> ApifyKeyManager:
        if environ is None:
            load_dotenv(PROJECT_ROOT / ".env", override=False)
            environ = os.environ

        configured_count = _int_or_zero(environ.get("APIFY_TOKEN_COUNT"))
        scan_limit = max(configured_count, 20)
        indexed_keys: list[ApifyKey] = []
        for index in range(1, scan_limit + 1):
            token = _clean(environ.get(f"APIFY_TOKEN_{index}"))
            if not token:
                continue
            indexed_keys.append(
                ApifyKey(
                    label=_clean(environ.get(f"APIFY_TOKEN_{index}_LABEL"))
                    or f"APIFY_TOKEN_{index}",
                    token=token,
                    max_total_usd=_float_or_none(environ.get(f"APIFY_TOKEN_{index}_MAX_TOTAL_USD")),
                    min_remaining_usd=_float_or_none(
                        environ.get(f"APIFY_TOKEN_{index}_MIN_REMAINING_USD")
                    ),
                )
            )

        keys = indexed_keys
        fallback = _clean(environ.get("APIFY_TOKEN"))
        if not keys and fallback:
            keys = [
                ApifyKey(
                    label=_clean(environ.get("APIFY_TOKEN_LABEL")) or "APIFY_TOKEN",
                    token=fallback,
                    max_total_usd=_float_or_none(environ.get("APIFY_TOKEN_MAX_TOTAL_USD")),
                    min_remaining_usd=_float_or_none(environ.get("APIFY_TOKEN_MIN_REMAINING_USD")),
                )
            ]

        budget = ApifyBudgetConfig(
            global_max_total_usd=_float_or_none(environ.get("APIFY_GLOBAL_MAX_TOTAL_USD")),
            global_min_remaining_usd=_float_or_none(environ.get("APIFY_GLOBAL_MIN_REMAINING_USD")),
            x_total_cost_cap_usd=_float_or_none(environ.get("X_TOTAL_COST_CAP_USD")),
            youtube_transcript_total_cost_cap_usd=_float_or_none(
                environ.get("YOUTUBE_TRANSCRIPT_TOTAL_COST_CAP_USD")
            ),
        )
        return cls(keys=keys, budget=budget, ledger_path=ledger_path)

    @property
    def labels(self) -> list[str]:
        return [key.label for key in self.keys]

    @property
    def global_spend_usd(self) -> float:
        return sum(self.platform_spend.values())

    def ensure_ledger(self) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if self.ledger_path.exists() and self.ledger_path.stat().st_size > 0:
            return
        with self.ledger_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.ledger_fields())
            writer.writeheader()

    @staticmethod
    def ledger_fields() -> list[str]:
        return [
            "timestamp_utc",
            "key_label",
            "platform",
            "actor_id",
            "run_id",
            "source_type",
            "source_value",
            "requested_items",
            "imported_items",
            "duplicates",
            "cost_usd",
            "status",
            "reason",
            "cumulative_key_spend_usd",
            "cumulative_global_spend_usd",
        ]

    def choose_key(self, platform: str = "x", projected_cost_usd: float = 0.0) -> ApifyKey:
        platform = platform.strip().lower() or "x"
        self._ensure_platform_budget(platform, projected_cost_usd)
        for offset in range(len(self.keys)):
            index = (self._cursor + offset) % len(self.keys)
            key = self.keys[index]
            if key.can_spend(projected_cost_usd):
                self._cursor = (index + 1) % len(self.keys)
                return key
        raise ApifyBudgetError("All configured Apify keys are exhausted or disabled.")

    @contextmanager
    def activate_key(self, key: ApifyKey) -> Iterator[str]:
        previous = os.environ.get("APIFY_TOKEN")
        os.environ["APIFY_TOKEN"] = key.token
        try:
            yield key.label
        finally:
            if previous is None:
                os.environ.pop("APIFY_TOKEN", None)
            else:
                os.environ["APIFY_TOKEN"] = previous

    def record_run(
        self,
        *,
        key_label: str,
        platform: str,
        actor_id: str = "",
        run_id: str = "",
        source_type: str = "",
        source_value: str = "",
        requested_items: int = 0,
        imported_items: int = 0,
        duplicates: int = 0,
        cost_usd: float = 0.0,
        status: str = "completed",
        reason: str = "",
    ) -> None:
        key = self._key_by_label(key_label)
        cost = max(float(cost_usd or 0.0), 0.0)
        key.spent_usd += cost
        platform_key = platform.strip().lower() or "unknown"
        self.platform_spend[platform_key] = self.platform_spend.get(platform_key, 0.0) + cost
        if status.lower() in {"failed", "error", "auth_error", "credit_error"}:
            self.mark_failure(key_label, reason=reason or status, write_ledger=False)
        self.ensure_ledger()
        with self.ledger_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.ledger_fields())
            writer.writerow(
                {
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                    "key_label": key.label,
                    "platform": platform_key,
                    "actor_id": actor_id,
                    "run_id": run_id,
                    "source_type": source_type,
                    "source_value": source_value,
                    "requested_items": requested_items,
                    "imported_items": imported_items,
                    "duplicates": duplicates,
                    "cost_usd": f"{cost:.6f}",
                    "status": status,
                    "reason": reason,
                    "cumulative_key_spend_usd": f"{key.spent_usd:.6f}",
                    "cumulative_global_spend_usd": f"{self.global_spend_usd:.6f}",
                }
            )

    def mark_failure(self, key_label: str, reason: str = "", write_ledger: bool = True) -> None:
        key = self._key_by_label(key_label)
        key.failure_count += 1
        lower = reason.lower()
        if key.failure_count >= self.max_failures_per_key:
            key.disabled_reason = reason or "repeated_failures"
        if "auth" in lower or "401" in lower or "unauthorized" in lower:
            key.disabled_reason = reason or "authentication_error"
        if "credit" in lower or "payment" in lower or "insufficient" in lower:
            key.disabled_reason = reason or "credit_error"
        if write_ledger:
            self.record_run(key_label=key_label, platform="unknown", status="failed", reason=reason)

    def mark_low_yield(self, key_label: str, reason: str = "low_yield_costly_result") -> None:
        self._key_by_label(key_label).disabled_reason = reason

    def safe_summary(self) -> dict[str, object]:
        return {
            "token_count": len(self.keys),
            "labels": self.labels,
            "budget": {
                "global_max_total_usd": self.budget.global_max_total_usd,
                "global_min_remaining_usd": self.budget.global_min_remaining_usd,
                "x_total_cost_cap_usd": self.budget.x_total_cost_cap_usd,
                "youtube_transcript_total_cost_cap_usd": self.budget.youtube_transcript_total_cost_cap_usd,
            },
            "keys": [key.public_summary() for key in self.keys],
            "global_spend_usd": round(self.global_spend_usd, 6),
        }

    def redact_text(self, text: str) -> str:
        redacted = text
        for key in self.keys:
            if key.token:
                redacted = redacted.replace(key.token, "[REDACTED_APIFY_TOKEN]")
        return redacted

    def _ensure_platform_budget(self, platform: str, projected_cost_usd: float) -> None:
        cap = self.budget.cap_for_platform(platform)
        if cap is None:
            return
        current = self.platform_spend.get(platform, 0.0)
        if current + max(projected_cost_usd, 0.0) > cap + 1e-9:
            raise ApifyBudgetError(
                f"Configured Apify {platform} budget would be exceeded: "
                f"current={current:.2f}, projected={projected_cost_usd:.2f}, cap={cap:.2f}"
            )

    def _key_by_label(self, key_label: str) -> ApifyKey:
        for key in self.keys:
            if key.label == key_label:
                return key
        raise KeyError(f"Unknown Apify key label: {key_label}")

    def _load_existing_ledger(self) -> None:
        if not self.ledger_path.exists() or self.ledger_path.stat().st_size == 0:
            return
        try:
            with self.ledger_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    platform = _clean(row.get("platform")).lower() or "unknown"
                    cost = _float_or_none(row.get("cost_usd")) or 0.0
                    self.platform_spend[platform] = self.platform_spend.get(platform, 0.0) + cost
        except csv.Error:
            return

    def _sync_key_spend_from_ledger(self) -> None:
        if not self.ledger_path.exists() or self.ledger_path.stat().st_size == 0:
            return
        spend_by_label = {key.label: 0.0 for key in self.keys}
        try:
            with self.ledger_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    label = _clean(row.get("key_label"))
                    if label in spend_by_label:
                        spend_by_label[label] += _float_or_none(row.get("cost_usd")) or 0.0
        except csv.Error:
            return
        for key in self.keys:
            key.spent_usd = spend_by_label.get(key.label, 0.0)
