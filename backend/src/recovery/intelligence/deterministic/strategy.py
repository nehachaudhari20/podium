"""Deterministic strategy proposals from context and reasoning."""

from __future__ import annotations

from recovery.intelligence.adapters import case_facts_to_runtime
from recovery.intelligence.contracts import (
    PredictiveSignals,
    ReasoningInsight,
    StrategyIntelligence,
    StrategyProposal,
)
from recovery.intelligence.strategy import generate_actions
from recovery.models.enums import Lane
from recovery.models.recovery_context import RecoveryContext
from recovery.models.recovery_types import DiagnosisResult, RecoveryAction


class DeterministicStrategyIntelligence:
    """Generates ranked strategy proposals using lane-aware action catalogs."""

    def propose_strategies(
        self,
        context: RecoveryContext,
        reasoning: ReasoningInsight,
        predictive: PredictiveSignals,
    ) -> tuple[StrategyProposal, ...]:
        runtime_case = case_facts_to_runtime(context.case)
        diagnosis = DiagnosisResult(
            likely_cause=reasoning.likely_cause,
            confidence=reasoning.confidence,
            rationale=reasoning.summary,
        )
        actions = generate_actions(runtime_case, diagnosis, context)
        actions = self._filter_actions(context, actions)
        actions = self._reorder_actions(context, actions)

        proposals: list[StrategyProposal] = []
        for idx, action in enumerate(actions, start=1):
            confidence = self._action_confidence(context, predictive, action)
            proposals.append(
                StrategyProposal(
                    action=action,
                    rationale=self._action_rationale(context, action),
                    priority=idx,
                    confidence=confidence,
                    source="deterministic",
                )
            )
        return tuple(proposals)

    def _filter_actions(
        self,
        context: RecoveryContext,
        actions: list[RecoveryAction],
    ) -> list[RecoveryAction]:
        filtered = list(actions)
        if context.case.payment_method_updated:
            filtered = [a for a in filtered if a.action_id != "payment_method_update"]
        if context.derived_signals.customer_opt_out:
            filtered = [a for a in filtered if not a.is_contact]
            if context.case.lane == Lane.CHECKOUT_ABANDONMENT.value and not filtered:
                filtered = [
                    RecoveryAction("stop_recovery", "Stop checkout recovery", "system")
                ]
        return filtered

    def _reorder_actions(
        self,
        context: RecoveryContext,
        actions: list[RecoveryAction],
    ) -> list[RecoveryAction]:
        if context.case.lane == Lane.CHECKOUT_ABANDONMENT.value:
            return self._reorder_checkout(context, actions)
        if context.case.lane == Lane.RECEIVABLE.value:
            return self._reorder_receivable(context, actions)

        if not context.derived_signals.repeated_failure:
            return actions

        retries = [a for a in actions if a.is_retry]
        contacts = [a for a in actions if a.is_contact and a.action_id != "human_escalation"]
        escalations = [a for a in actions if a.action_id == "human_escalation"]
        others = [a for a in actions if a not in retries + contacts + escalations]

        if context.derived_signals.retry_exhaustion_risk:
            return escalations + contacts + retries + others
        return contacts + retries + escalations + others

    def _reorder_checkout(
        self,
        context: RecoveryContext,
        actions: list[RecoveryAction],
    ) -> list[RecoveryAction]:
        last = context.case.last_action
        if not last:
            return actions
        # Push previously executed action later to encourage re-planning diversity.
        preferred = [a for a in actions if a.action_id != last]
        repeated = [a for a in actions if a.action_id == last]
        return preferred + repeated

    def _reorder_receivable(
        self,
        context: RecoveryContext,
        actions: list[RecoveryAction],
    ) -> list[RecoveryAction]:
        if context.derived_signals.active_promise:
            return actions
        last = context.case.last_action
        if not last:
            return actions
        preferred = [a for a in actions if a.action_id != last]
        repeated = [a for a in actions if a.action_id == last]
        return preferred + repeated

    def _action_confidence(
        self,
        context: RecoveryContext,
        predictive: PredictiveSignals,
        action: RecoveryAction,
    ) -> float:
        base = predictive.estimated_recovery_probability
        if action.is_retry:
            base = predictive.retry_success_likelihood
        if action.is_contact:
            base = (base + predictive.responsiveness_score) / 2
        if action.action_id == "human_escalation" and context.derived_signals.repeated_failure:
            base = min(0.85, base + 0.20)
        if action.action_id == "limited_incentive":
            base = min(0.70, base)
        if action.action_id == "stop_recovery":
            base = 0.55
        if (
            context.case.lane == Lane.CHECKOUT_ABANDONMENT.value
            and action.action_id in {"payment_link", "checkout_reminder"}
            and context.derived_signals.high_intent
        ):
            base = min(0.92, base + 0.12)
        if context.case.lane == Lane.RECEIVABLE.value:
            if action.action_id == "invoice_reminder" and context.derived_signals.mildly_overdue:
                base = min(0.90, base + 0.10)
            if action.action_id == "promise_to_pay_request" and context.derived_signals.aged_overdue:
                base = min(0.88, base + 0.08)
            if action.action_id == "track_promise_to_pay" and context.derived_signals.active_promise:
                base = 0.80
            if (
                action.action_id in {"human_escalation", "escalate_collections"}
                and context.derived_signals.promise_broken_before
            ):
                base = min(0.90, base + 0.15)
        return round(min(0.99, max(0.01, base)), 4)

    def _action_rationale(self, context: RecoveryContext, action: RecoveryAction) -> str:
        signals = context.derived_signals
        if action.action_id == "human_escalation" and signals.repeated_failure:
            return "Repeated failures suggest human follow-up may be more effective than another automated retry."
        if action.is_retry and signals.transient_failure:
            return "Transient failure; scheduled retry is a low-friction recovery path."
        if action.action_id == "payment_method_update" and signals.expired_payment_method:
            return "Expired or invalid payment method requires customer update before retry."
        if action.action_id == "checkout_reminder" and signals.high_intent:
            return "High-intent abandonment; low-friction reminder is preferred before incentives."
        if action.action_id == "payment_link" and signals.payment_stage_abandonment:
            return "Payment-stage drop; a direct payment link reduces completion friction."
        if action.action_id == "limited_incentive":
            return "Bounded incentive considered only because context suggests price sensitivity under policy."
        if action.action_id == "stop_recovery":
            return "Intervention cost outweighs expected recovery; stop further checkout outreach."
        if action.action_id == "invoice_reminder" and signals.mildly_overdue:
            return "Recently overdue invoice; low-friction reminder is preferred."
        if action.action_id == "promise_to_pay_request":
            return "Request a payment commitment to structure receivable recovery."
        if action.action_id == "track_promise_to_pay":
            return "Active promise exists; track the commitment instead of stacking outreach."
        if action.action_id == "escalate_collections" and signals.promise_broken_before:
            return "Broken promise history; collections escalation may be warranted."
        return f"Candidate action: {action.label}"


_: StrategyIntelligence = DeterministicStrategyIntelligence()
