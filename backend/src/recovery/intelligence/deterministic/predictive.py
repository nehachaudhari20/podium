"""Deterministic predictive signals from structured context."""

from __future__ import annotations

from recovery.intelligence.contracts import PredictiveIntelligence, PredictiveSignals
from recovery.models.enums import Lane
from recovery.models.recovery_context import RecoveryContext


class DeterministicPredictiveIntelligence:
    """Rule-based recovery likelihood scores — not ML, not LLM."""

    def score(self, context: RecoveryContext) -> PredictiveSignals:
        if context.case.lane == Lane.CHECKOUT_ABANDONMENT.value:
            return self._score_checkout(context)
        if context.case.lane == Lane.RECEIVABLE.value:
            return self._score_receivable(context)
        return self._score_subscription(context)

    def _score_subscription(self, context: RecoveryContext) -> PredictiveSignals:
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

    def _score_checkout(self, context: RecoveryContext) -> PredictiveSignals:
        signals = context.derived_signals
        checkout = context.checkout

        recovery_prob = 0.40
        retry_likelihood = 0.35
        responsiveness = 0.48

        if signals.high_intent and signals.recent_abandonment:
            recovery_prob = 0.72
            responsiveness = 0.70
        elif signals.high_intent and signals.payment_stage_abandonment:
            recovery_prob = 0.68
            responsiveness = 0.65
        elif signals.early_stage_abandonment and not signals.high_intent:
            recovery_prob = 0.28
            responsiveness = 0.35
        elif checkout is not None and checkout.intent_score is not None and checkout.intent_score < 0.45:
            recovery_prob = 0.22
            responsiveness = 0.30

        if signals.prior_successful_customer:
            recovery_prob = min(0.92, recovery_prob + 0.10)
            responsiveness = min(1.0, responsiveness + 0.12)

        if signals.customer_non_response:
            responsiveness = max(0.05, responsiveness - 0.22)
            recovery_prob = max(0.08, recovery_prob - 0.10)

        if signals.customer_opt_out:
            responsiveness = 0.0
            recovery_prob = max(0.05, recovery_prob - 0.20)

        if signals.recovery_attempted_before:
            recovery_prob = max(0.10, recovery_prob - 0.08)

        return PredictiveSignals(
            estimated_recovery_probability=round(recovery_prob, 4),
            retry_success_likelihood=round(retry_likelihood, 4),
            responsiveness_score=round(min(1.0, responsiveness), 4),
            source="deterministic",
        )

    def _score_receivable(self, context: RecoveryContext) -> PredictiveSignals:
        signals = context.derived_signals
        invoice = context.invoice
        amount = invoice.amount if invoice is not None else context.case.amount
        days = context.case.days_overdue or (invoice.days_overdue if invoice else 0)

        recovery_prob = 0.50
        retry_likelihood = 0.35
        responsiveness = 0.52

        if signals.mildly_overdue and signals.first_failure:
            recovery_prob = 0.68
            responsiveness = 0.70
        elif signals.aged_overdue:
            recovery_prob = 0.55
            responsiveness = 0.55
        elif signals.severely_overdue:
            recovery_prob = 0.32
            responsiveness = 0.30

        if signals.high_value_invoice or amount >= 50000:
            recovery_prob = min(0.88, recovery_prob + 0.08)

        if signals.prior_successful_payment:
            recovery_prob = min(0.92, recovery_prob + 0.08)
            responsiveness = min(1.0, responsiveness + 0.10)

        if signals.active_promise:
            recovery_prob = min(0.90, recovery_prob + 0.12)
            responsiveness = min(1.0, responsiveness + 0.15)

        if signals.promise_broken_before:
            recovery_prob = max(0.12, recovery_prob - 0.18)
            responsiveness = max(0.08, responsiveness - 0.20)

        if signals.partial_payment_received:
            recovery_prob = min(0.85, recovery_prob + 0.10)

        if signals.customer_non_response:
            responsiveness = max(0.05, responsiveness - 0.22)
            recovery_prob = max(0.10, recovery_prob - 0.10)

        if signals.customer_opt_out:
            responsiveness = 0.0
            recovery_prob = max(0.05, recovery_prob - 0.20)

        if days >= 45:
            recovery_prob = max(0.10, recovery_prob - 0.08)

        return PredictiveSignals(
            estimated_recovery_probability=round(recovery_prob, 4),
            retry_success_likelihood=round(retry_likelihood, 4),
            responsiveness_score=round(min(1.0, responsiveness), 4),
            source="deterministic",
        )


_: PredictiveIntelligence = DeterministicPredictiveIntelligence()
