"""Deterministic policy gate — authoritative constraint enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import sqlite3

from recovery.config import load_policy
from recovery.ingestion.customer_loader import CustomerContext, count_recent_contacts
from recovery.models.case import RecoveryCaseRuntime
from recovery.models.enums import Lane
from recovery.models.recovery_types import PolicyResult, RecoveryAction

# Simulated limited incentive offer size — must stay under merchant ceiling.
_LIMITED_INCENTIVE_PCT = 10


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    max_retries: int
    min_contact_cooldown_hours: int
    max_contacts_per_7_days: int
    opt_out_protection: bool
    discount_ceiling_pct: int
    human_only_threshold_amount: float


def load_policy_config() -> PolicyConfig:
    raw = load_policy()
    return PolicyConfig(
        max_retries=int(raw["max_retries"]),
        min_contact_cooldown_hours=int(raw["min_contact_cooldown_hours"]),
        max_contacts_per_7_days=int(raw["max_contacts_per_7_days"]),
        opt_out_protection=bool(raw["opt_out_protection"]),
        discount_ceiling_pct=int(raw.get("discount_ceiling_pct", 0)),
        human_only_threshold_amount=float(raw.get("human_only_threshold_amount", 0)),
    )


def check_policy(
    case: RecoveryCaseRuntime,
    action: RecoveryAction,
    customer: CustomerContext,
    conn: sqlite3.Connection | None = None,
    last_retry_at: datetime | None = None,
    now: datetime | None = None,
) -> PolicyResult:
    """Evaluate whether a proposed action is allowed under merchant policy."""
    policy = load_policy_config()
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if policy.opt_out_protection and customer.opt_out and action.is_contact:
        return PolicyResult(
            allowed=False,
            action=action.action_id,
            reason="Customer has opted out of contact channels.",
        )

    if action.is_retry and case.attempt_count >= policy.max_retries:
        return PolicyResult(
            allowed=False,
            action=action.action_id,
            reason="Maximum retry count exceeded.",
        )

    checkout_attempt = case.lane == Lane.CHECKOUT_ABANDONMENT.value and (
        action.is_contact or action.action_id in {"limited_incentive", "offer_discount"}
    )
    if checkout_attempt and case.attempt_count >= policy.max_retries:
        return PolicyResult(
            allowed=False,
            action=action.action_id,
            reason="Maximum checkout recovery attempts exceeded.",
        )

    if action.is_contact:
        total_contacts = customer.prior_contacts_7d
        if conn is not None:
            since = now - timedelta(days=7)
            total_contacts += count_recent_contacts(conn, customer.customer_id, since)

        if total_contacts >= policy.max_contacts_per_7_days:
            return PolicyResult(
                allowed=False,
                action=action.action_id,
                reason="Maximum contacts in 7 days exceeded.",
            )

    if action.action_id in {"limited_incentive", "offer_discount"}:
        if policy.discount_ceiling_pct <= 0 or _LIMITED_INCENTIVE_PCT > policy.discount_ceiling_pct:
            return PolicyResult(
                allowed=False,
                action=action.action_id,
                reason=(
                    f"Incentive {_LIMITED_INCENTIVE_PCT}% exceeds discount ceiling "
                    f"({policy.discount_ceiling_pct}%)."
                ),
            )

    if action.is_retry and last_retry_at is not None:
        last = last_retry_at if last_retry_at.tzinfo else last_retry_at.replace(tzinfo=timezone.utc)
        elapsed = now - last
        cooldown = timedelta(hours=policy.min_contact_cooldown_hours)
        if elapsed < cooldown:
            return PolicyResult(
                allowed=False,
                action=action.action_id,
                reason=f"Retry cooldown not met ({policy.min_contact_cooldown_hours}h required).",
            )

    return PolicyResult(
        allowed=True,
        action=action.action_id,
        reason="Action permitted under current policy.",
    )


def select_first_allowed_action(
    case: RecoveryCaseRuntime,
    actions: list[RecoveryAction],
    customer: CustomerContext,
    conn: sqlite3.Connection | None = None,
    last_retry_at: datetime | None = None,
    now: datetime | None = None,
) -> tuple[RecoveryAction | None, PolicyResult | None, list[PolicyResult]]:
    """Return first feasible action and all policy checks performed."""
    checks: list[PolicyResult] = []
    for action in actions:
        result = check_policy(case, action, customer, conn, last_retry_at, now)
        checks.append(result)
        if result.allowed:
            return action, result, checks
    return None, checks[-1] if checks else None, checks
