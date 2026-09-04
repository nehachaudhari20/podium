"""Deterministic policy gate — authoritative constraint enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import sqlite3

from podium.config import load_policy
from podium.ingestion.customer_loader import CustomerContext, count_recent_contacts
from podium.models.case import RecoveryCaseRuntime
from podium.models.recovery_types import PolicyResult, RecoveryAction


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    max_retries: int
    min_contact_cooldown_hours: int
    max_contacts_per_7_days: int
    opt_out_protection: bool


def load_policy_config() -> PolicyConfig:
    raw = load_policy()
    return PolicyConfig(
        max_retries=int(raw["max_retries"]),
        min_contact_cooldown_hours=int(raw["min_contact_cooldown_hours"]),
        max_contacts_per_7_days=int(raw["max_contacts_per_7_days"]),
        opt_out_protection=bool(raw["opt_out_protection"]),
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
    now = now or datetime.now()

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

    if action.is_retry and last_retry_at is not None:
        elapsed = now - last_retry_at
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
