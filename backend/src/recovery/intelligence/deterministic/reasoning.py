"""Deterministic reasoning from structured context."""

from __future__ import annotations

from recovery.intelligence.adapters import case_facts_to_runtime, context_key_factors
from recovery.intelligence.contracts import ReasoningInsight, ReasoningIntelligence
from recovery.intelligence.diagnosis import diagnose
from recovery.models.enums import Lane
from recovery.models.recovery_context import RecoveryContext


class DeterministicReasoningIntelligence:
    """Wraps rule-based diagnosis with context-aware factors."""

    def interpret(self, context: RecoveryContext) -> ReasoningInsight:
        runtime_case = case_facts_to_runtime(context.case)
        diagnosis = diagnose(runtime_case, context)
        factors = context_key_factors(context)

        if context.case.lane == Lane.CHECKOUT_ABANDONMENT.value:
            summary = _checkout_summary(context, diagnosis.likely_cause, diagnosis.rationale)
        elif context.derived_signals.repeated_failure:
            summary = (
                f"Repeated failure pattern for {diagnosis.likely_cause}; "
                "escalation or alternate path may be required."
            )
        elif context.derived_signals.transient_failure:
            summary = "Transient failure with favorable retry conditions."
        elif context.derived_signals.customer_opt_out:
            summary = "Customer opted out; contact-based recovery paths are constrained."
        else:
            summary = diagnosis.rationale

        return ReasoningInsight(
            summary=summary,
            likely_cause=diagnosis.likely_cause,
            confidence=diagnosis.confidence,
            key_factors=factors if factors else (diagnosis.likely_cause,),
            source="deterministic",
        )


def _checkout_summary(context: RecoveryContext, cause: str, rationale: str) -> str:
    signals = context.derived_signals
    if signals.customer_opt_out:
        return "Customer opted out; checkout contact recovery is constrained."
    if signals.high_intent and signals.recent_abandonment:
        return (
            f"{cause}: high-intent recent abandonment; "
            "prefer reminder or payment link before any incentive."
        )
    if cause == "low_intent":
        return "Low-intent abandonment; keep intervention bounded or stop recovery."
    if signals.recovery_attempted_before and signals.customer_non_response:
        return f"{cause}: prior intervention without response; re-plan to a different action."
    return rationale


_: ReasoningIntelligence = DeterministicReasoningIntelligence()
