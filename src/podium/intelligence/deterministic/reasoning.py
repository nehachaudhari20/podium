"""Deterministic reasoning from structured context."""

from __future__ import annotations

from podium.intelligence.adapters import case_facts_to_runtime, context_key_factors
from podium.intelligence.contracts import ReasoningInsight, ReasoningIntelligence
from podium.intelligence.diagnosis import diagnose
from podium.models.recovery_context import RecoveryContext


class DeterministicReasoningIntelligence:
    """Wraps Phase 2 rule-based diagnosis with context-aware factors."""

    def interpret(self, context: RecoveryContext) -> ReasoningInsight:
        runtime_case = case_facts_to_runtime(context.case)
        diagnosis = diagnose(runtime_case)
        factors = context_key_factors(context)

        if context.derived_signals.repeated_failure:
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


_: ReasoningIntelligence = DeterministicReasoningIntelligence()
