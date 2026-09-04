"""Deterministic predictive signals from structured context."""

from __future__ import annotations

from recovery.intelligence.contracts import PredictiveIntelligence, PredictiveSignals
from recovery.models.recovery_context import RecoveryContext


class DeterministicPredictiveIntelligence:
    """Rule-based recovery likelihood scores — not ML, not LLM."""

    def score(self, context: RecoveryContext) -> PredictiveSignals:
        signals = context.derived_signals
        case = context.case

        recovery_prob = 0.45
        retry_likelihood = 0.40
        responsiveness = 0.50

        if signals.transient_failure and signals.first_failure:
            recovery_prob = 0.72
            retry_likelihood = 0.68
        elif signals.expired_payment_method:
            recovery_prob = 0.55 if case.payment_method_updated else 0.38
            retry_likelihood = 0.62 if case.payment_method_updated else 0.25
        elif case.failure_reason == "insufficient_funds":
            recovery_prob = 0.48 if case.attempt_count >= 1 else 0.35
            retry_likelihood = 0.50 if case.attempt_count >= 1 else 0.30
        elif signals.repeated_failure:
            recovery_prob = 0.18
            retry_likelihood = 0.12

        if signals.prior_successful_payment:
            recovery_prob = min(0.95, recovery_prob + 0.08)
            responsiveness += 0.10

        if signals.customer_non_response:
            responsiveness = max(0.05, responsiveness - 0.20)

        if signals.customer_opt_out:
            responsiveness = 0.0
            recovery_prob = max(0.05, recovery_prob - 0.15)

        if signals.retry_exhaustion_risk:
            retry_likelihood = max(0.05, retry_likelihood - 0.25)

        return PredictiveSignals(
            estimated_recovery_probability=round(recovery_prob, 4),
            retry_success_likelihood=round(retry_likelihood, 4),
            responsiveness_score=round(min(1.0, responsiveness), 4),
            source="deterministic",
        )


# Protocol satisfaction
_: PredictiveIntelligence = DeterministicPredictiveIntelligence()
