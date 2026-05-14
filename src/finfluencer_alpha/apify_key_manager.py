from __future__ import annotations

import csv
import os
import re
from collections import defaultdict
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


def _env_truthy(value: object, *, default: bool = True) -> bool:
    text = _clean(value).lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def classify_apify_key_failure(reason: str) -> str | None:
    """Classify whether an Apify error string indicates a key/account health issue.

    Returns ``\"auth\"``, ``\"credit\"``, ``\"transient\"``, or ``None`` when the failure
    should not cause key rotation (for example empty datasets or timestamp parsing).
    """
    lower = reason.lower()
    if re.search(r"\b401\b", lower) or "unauthorized" in lower or "invalid token" in lower:
        return "auth"
    if re.search(r"\b402\b", lower) or "payment required" in lower or "insufficient" in lower:
        return "credit"
    if (
        re.search(r"\b403\b", lower)
        and ("forbidden" in lower or "token" in lower or "credential" in lower)
    ):
        return "auth"
    if re.search(r"\b429\b", lower) or "rate limit" in lower:
        return "transient"
    if any(
        token in lower
        for token in (
            "timeout",
            "timed out",
            "connection reset",
            "econnrefused",
            "temporarily unavailable",
            "bad gateway",
            "service unavailable",
            "502",
            "503",
            "504",
        )
    ):
        return "transient"
    if "quota" in lower and "exceed" in lower:
        return "credit"
    return None


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
        projected = max(projected_cost_usd, 0.0)
        if self.max_total_usd is not None:
            if self.spent_usd + projected > self.max_total_usd + 1e-9:
                return False
            if self.min_remaining_usd is not None:
                headroom = self.max_total_usd - self.spent_usd - projected
                if headroom + 1e-9 < self.min_remaining_usd:
                    return False
        return True

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
    session_max_total_usd: float | None = None

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
        *,
        disable_on_auth_error: bool = True,
        disable_on_credit_error: bool = False,
        max_transient_retries_per_key: int = 2,
        skip_exhausted_keys: bool = True,
    ) -> None:
        if not keys:
            raise ApifyBudgetError("No Apify tokens are configured.")
        self.keys = keys
        self.budget = budget or ApifyBudgetConfig()
        self.ledger_path = ledger_path or DEFAULT_LEDGER_PATH
        self.max_failures_per_key = max_failures_per_key
        self.disable_on_auth_error = disable_on_auth_error
        self.disable_on_credit_error = disable_on_credit_error
        self.max_transient_retries_per_key = max(1, max_transient_retries_per_key)
        self.skip_exhausted_keys = skip_exhausted_keys
        self._session_spent_usd = 0.0
        self._session_excluded: set[str] = set()
        self._transient_hits: dict[str, int] = {}
        self._session_spend_by_label: defaultdict[str, float] = defaultdict(float)
        self._session_calls_by_label: defaultdict[str, int] = defaultdict(int)
        self._session_used_labels: set[str] = set()
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
        if configured_count > 0:
            scan_range = range(1, configured_count + 1)
        else:
            scan_range = range(1, 21)

        indexed_keys: list[ApifyKey] = []
        for index in scan_range:
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

        multi = _env_truthy(environ.get("APIFY_MULTI_KEY_MODE"), default=True)
        if not multi and len(keys) > 1:
            keys = [keys[0]]

        budget = ApifyBudgetConfig(
            global_max_total_usd=_float_or_none(environ.get("APIFY_GLOBAL_MAX_TOTAL_USD")),
            global_min_remaining_usd=_float_or_none(environ.get("APIFY_GLOBAL_MIN_REMAINING_USD")),
            x_total_cost_cap_usd=_float_or_none(environ.get("X_TOTAL_COST_CAP_USD")),
            youtube_transcript_total_cost_cap_usd=_float_or_none(
                environ.get("YOUTUBE_TRANSCRIPT_TOTAL_COST_CAP_USD")
            ),
            session_max_total_usd=_float_or_none(environ.get("APIFY_SESSION_MAX_TOTAL_USD")),
        )
        max_failures = _int_or_zero(environ.get("APIFY_MAX_KEY_FAILURES_PER_RUN"))
        if max_failures <= 0:
            max_failures = 3
        transient_retries = _int_or_zero(environ.get("APIFY_MAX_TRANSIENT_RETRIES_PER_KEY"))
        if transient_retries <= 0:
            transient_retries = max_failures
        return cls(
            keys=keys,
            budget=budget,
            ledger_path=ledger_path,
            max_failures_per_key=max_failures,
            disable_on_auth_error=_env_truthy(
                environ.get("APIFY_DISABLE_KEY_ON_AUTH_ERROR"), default=True
            ),
            disable_on_credit_error=_env_truthy(
                environ.get("APIFY_DISABLE_KEY_ON_CREDIT_ERROR"), default=False
            ),
            max_transient_retries_per_key=transient_retries,
            skip_exhausted_keys=_env_truthy(environ.get("APIFY_SKIP_EXHAUSTED_KEYS"), default=True),
        )

    @property
    def labels(self) -> list[str]:
        return [key.label for key in self.keys]

    @property
    def global_spend_usd(self) -> float:
        return sum(self.platform_spend.values())

    @property
    def session_spend_usd(self) -> float:
        return self._session_spent_usd

    def begin_session(self) -> None:
        """Reset per-checkpoint session counters and soft exclusions."""
        self._session_spent_usd = 0.0
        self._session_excluded.clear()
        self._transient_hits.clear()
        self._session_spend_by_label.clear()
        self._session_calls_by_label.clear()
        self._session_used_labels.clear()

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
        self._ensure_session_budget(projected_cost_usd)
        for key in self.keys:
            if not self._key_pickable(key, platform, projected_cost_usd):
                continue
            self._session_calls_by_label[key.label] += 1
            self._session_used_labels.add(key.label)
            return key
        raise ApifyBudgetError("All configured Apify keys are exhausted or disabled.")

    def note_key_failure_for_rotation(
        self,
        key_label: str,
        reason: str,
        *,
        platform: str = "x",
        projected_retry_usd: float = 0.02,
    ) -> bool:
        """Apply failure policy and return whether another key may still be attempted."""
        category = classify_apify_key_failure(reason)
        if category is None:
            return False
        key = self._key_by_label(key_label)
        if category == "auth":
            if self.disable_on_auth_error:
                key.disabled_reason = key.disabled_reason or "authentication_error"
            else:
                self._session_excluded.add(key_label)
        elif category == "credit":
            if self.disable_on_credit_error:
                key.disabled_reason = key.disabled_reason or "credit_error"
            else:
                self._session_excluded.add(key_label)
        elif category == "transient":
            hits = self._transient_hits.get(key_label, 0) + 1
            self._transient_hits[key_label] = hits
            if hits >= self.max_transient_retries_per_key:
                self._session_excluded.add(key_label)
        return self._has_pickable_key(platform, projected_retry_usd)

    def _has_pickable_key(self, platform: str, projected: float) -> bool:
        try:
            self._ensure_platform_budget(platform.strip().lower() or "x", projected)
            self._ensure_session_budget(projected)
        except ApifyBudgetError:
            return False
        for key in self.keys:
            if self._key_pickable(key, platform, projected):
                return True
        return False

    def _key_pickable(self, key: ApifyKey, platform: str, projected_cost_usd: float) -> bool:
        if self.skip_exhausted_keys and not key.can_spend(projected_cost_usd):
            return False
        if key.label in self._session_excluded:
            return False
        if key.disabled_reason:
            return False
        return key.can_spend(projected_cost_usd)

    def session_key_status_summary(self) -> list[dict[str, object]]:
        """Per-key checkpoint-safe status (no token values)."""
        rows: list[dict[str, object]] = []
        for key in self.keys:
            rows.append(
                {
                    "label": key.label,
                    "used_this_session": key.label in self._session_used_labels,
                    "permanently_disabled": bool(key.disabled_reason),
                    "session_excluded": key.label in self._session_excluded,
                    "disable_reason_category": _clean(key.disabled_reason),
                    "transient_hits_this_session": int(self._transient_hits.get(key.label, 0)),
                    "estimated_spend_this_session_usd": round(
                        float(self._session_spend_by_label.get(key.label, 0.0)), 6
                    ),
                    "calls_attempted_this_session": int(self._session_calls_by_label.get(key.label, 0)),
                }
            )
        return rows

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
        key_health_failure: bool | None = None,
    ) -> None:
        key = self._key_by_label(key_label)
        cost = max(float(cost_usd or 0.0), 0.0)
        key.spent_usd += cost
        self._session_spent_usd += cost
        self._session_spend_by_label[key_label] += cost
        platform_key = platform.strip().lower() or "unknown"
        self.platform_spend[platform_key] = self.platform_spend.get(platform_key, 0.0) + cost
        inferred_health: bool | None = key_health_failure
        if inferred_health is None and status.lower() in {"failed", "error", "auth_error", "credit_error"}:
            inferred_health = classify_apify_key_failure(reason or "") in {"auth", "credit"}
        if inferred_health:
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
            self.record_run(
                key_label=key_label,
                platform="unknown",
                status="failed",
                reason=reason,
                key_health_failure=False,
            )

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
                "session_max_total_usd": self.budget.session_max_total_usd,
            },
            "keys": [key.public_summary() for key in self.keys],
            "global_spend_usd": round(self.global_spend_usd, 6),
            "session_spend_usd": round(self._session_spent_usd, 6),
        }

    def redact_text(self, text: str) -> str:
        redacted = text
        for key in self.keys:
            if key.token:
                redacted = redacted.replace(key.token, "[REDACTED_APIFY_TOKEN]")
        return redacted

    def _ensure_session_budget(self, projected_cost_usd: float) -> None:
        cap = self.budget.session_max_total_usd
        if cap is None:
            return
        if self._session_spent_usd + max(projected_cost_usd, 0.0) > cap + 1e-9:
            raise ApifyBudgetError(
                f"Configured Apify session budget would be exceeded: "
                f"session_spend={self._session_spent_usd:.4f}, "
                f"projected={projected_cost_usd:.4f}, cap={cap:.4f}"
            )

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
        if self.budget.global_min_remaining_usd is not None:
            headroom = cap - current - max(projected_cost_usd, 0.0)
            if headroom + 1e-9 < self.budget.global_min_remaining_usd:
                raise ApifyBudgetError(
                    "Configured global minimum remaining headroom for this platform would be violated."
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
