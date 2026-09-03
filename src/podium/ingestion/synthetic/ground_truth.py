"""Correlated p_pay_anyway computation from case features."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PayAnywayFeatures:
    lane: str
    failure_reason: str | None
    recoverability_hint: str | None
    days_overdue: int | None
    attempt_count: int
    opt_out: bool
    prior_contacts_7d: int
    intent_score: float | None = None
    segment: str = "b2c"
    promise_missed: bool = False


FAILURE_BASE: dict[str, float] = {
    "transient_technical": 0.62,
    "network_timeout": 0.58,
    "issuer_timeout": 0.55,
    "authentication_failure": 0.35,
    "insufficient_funds": 0.22,
    "expired_card": 0.14,
    "invalid_card": 0.12,
    "mandate_revoked": 0.08,
    "repeated_failure": 0.06,
    "checkout_payment_page_drop": 0.28,
    "checkout_cart_abandon": 0.18,
    "checkout_high_intent_drop": 0.42,
    "invoice_mild_overdue": 0.20,
    "invoice_aged_overdue": 0.10,
    "invoice_severely_overdue": 0.05,
    "promise_missed": 0.07,
}


def compute_p_pay_anyway(features: PayAnywayFeatures, rng: random.Random) -> float:
    reason = features.failure_reason or "unknown"
    base = FAILURE_BASE.get(reason, 0.25)

    if features.lane == "checkout_abandonment" and features.intent_score is not None:
        base += (features.intent_score - 0.5) * 0.25

    if features.days_overdue is not None:
        if features.days_overdue > 60:
            base -= 0.12
        elif features.days_overdue > 30:
            base -= 0.06
        elif features.days_overdue <= 7:
            base += 0.04

    if features.segment == "b2b_enterprise":
        base -= 0.05
    elif features.segment == "b2b_smb":
        base -= 0.02

    base -= min(features.attempt_count, 5) * 0.03
    base -= min(features.prior_contacts_7d, 5) * 0.02

    if features.opt_out:
        base = min(base, 0.04)

    if features.promise_missed:
        base = min(base, 0.10)

    if features.recoverability_hint == "high":
        base += 0.08
    elif features.recoverability_hint == "low":
        base -= 0.10

    noise = rng.uniform(-0.04, 0.04)
    value = base + noise
    return max(0.01, min(0.95, round(value, 4)))


def features_to_snapshot(features: PayAnywayFeatures) -> dict:
    return {
        "lane": features.lane,
        "failure_reason": features.failure_reason,
        "recoverability_hint": features.recoverability_hint,
        "days_overdue": features.days_overdue,
        "attempt_count": features.attempt_count,
        "opt_out": features.opt_out,
        "prior_contacts_7d": features.prior_contacts_7d,
        "intent_score": features.intent_score,
        "segment": features.segment,
        "promise_missed": features.promise_missed,
    }
