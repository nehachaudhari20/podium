"""Deterministic strategy proposals from context and reasoning."""

from __future__ import annotations

from podium.intelligence.adapters import case_facts_to_runtime
from podium.intelligence.contracts import (
    PredictiveSignals,
    ReasoningInsight,
    StrategyIntelligence,
    StrategyProposal,
)
from podium.intelligence.diagnosis import DiagnosisResult
from podium.intelligence.strategy import generate_actions
from podium.models.recovery_context import RecoveryContext
from podium.models.recovery_types import RecoveryAction


class DeterministicStrategyIntelligence:
    """Generates ranked strategy proposals using Phase 2 action catalog."""

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
        actions = generate_actions(runtime_case, diagnosis)
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
        return filtered

    def _reorder_actions(
        self,
        context: RecoveryContext,
        actions: list[RecoveryAction],
    ) -> list[RecoveryAction]:
        if not context.derived_signals.repeated_failure:
            return actions

        retries = [a for a in actions if a.is_retry]
        contacts = [a for a in actions if a.is_contact and a.action_id != "human_escalation"]
        escalations = [a for a in actions if a.action_id == "human_escalation"]
        others = [a for a in actions if a not in retries + contacts + escalations]

        if context.derived_signals.retry_exhaustion_risk:
            return escalations + contacts + retries + others
        return contacts + retries + escalations + others

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
        return round(min(0.99, max(0.01, base)), 4)

    def _action_rationale(self, context: RecoveryContext, action: RecoveryAction) -> str:
        if action.action_id == "human_escalation" and context.derived_signals.repeated_failure:
            return "Repeated failures suggest human follow-up may be more effective than another automated retry."
        if action.is_retry and context.derived_signals.transient_failure:
            return "Transient failure; scheduled retry is a low-friction recovery path."
        if action.action_id == "payment_method_update" and context.derived_signals.expired_payment_method:
            return "Expired or invalid payment method requires customer update before retry."
        return f"Candidate action: {action.label}"


_: StrategyIntelligence = DeterministicStrategyIntelligence()
