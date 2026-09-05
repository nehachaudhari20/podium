"""Phase 4 checkout evaluation metrics (evaluator-only ground truth)."""

from __future__ import annotations

from recovery.evaluation.phase3_metrics import (
    CaseEvaluationRecord,
    Phase3EvaluationSummary,
    summarize_records,
)
from recovery.intelligence.checkout_diagnosis import CHECKOUT_FAILURE_TO_CAUSE

# Context-aware diagnosis may refine the base failure→cause mapping.
_CHECKOUT_CAUSE_REFINEMENTS: dict[str, frozenset[str]] = {
    "checkout_payment_page_drop": frozenset(
        {"payment_friction", "distraction_or_delay", "low_intent", "technical_friction"}
    ),
    "checkout_cart_abandon": frozenset(
        {"checkout_friction", "price_sensitivity", "low_intent", "unknown_abandonment"}
    ),
    "checkout_high_intent_drop": frozenset(
        {"distraction_or_delay", "payment_friction", "low_intent"}
    ),
}


def expected_checkout_causes(failure_reason: str | None) -> frozenset[str]:
    """Acceptable diagnosis causes for a checkout failure reason (evaluator-only)."""
    if not failure_reason:
        return frozenset()
    if failure_reason in _CHECKOUT_CAUSE_REFINEMENTS:
        return _CHECKOUT_CAUSE_REFINEMENTS[failure_reason]
    entry = CHECKOUT_FAILURE_TO_CAUSE.get(failure_reason)
    return frozenset({entry[0]}) if entry else frozenset()


def base_checkout_cause(failure_reason: str | None) -> str | None:
    if not failure_reason:
        return None
    entry = CHECKOUT_FAILURE_TO_CAUSE.get(failure_reason)
    return entry[0] if entry else None


def is_checkout_diagnosis_aligned(failure_reason: str | None, diagnosis_cause: str) -> bool:
    allowed = expected_checkout_causes(failure_reason)
    return bool(allowed) and diagnosis_cause in allowed


def format_checkout_evaluation_report(summary: Phase3EvaluationSummary) -> str:
    lines = [
        "=" * 72,
        "Podium Phase 4 Checkout Evaluation (4E)",
        f"Mode: {summary.intelligence_mode}  Lane: {summary.lane}",
        "=" * 72,
        f"Cases evaluated:          {summary.cases_evaluated}",
        f"Recovery rate:            {summary.recovery_rate:.1%}",
        f"Amount at risk:           INR {summary.amount_at_risk:,.2f}",
        f"Amount recovered:         INR {summary.amount_recovered:,.2f}",
        f"Recovery yield:           {summary.recovery_yield:.1%}",
        f"Avg agent steps:          {summary.avg_agent_steps:.2f}",
        f"Avg replans:              {summary.avg_replan_count:.2f}",
        f"Diagnosis alignment:      {summary.diagnosis_alignment_rate:.1%}",
    ]
    if summary.avg_p_pay_anyway_recovered is not None:
        lines.append(
            f"Avg p_pay_anyway (recovered):     {summary.avg_p_pay_anyway_recovered:.3f}  [evaluator-only]"
        )
    if summary.avg_p_pay_anyway_not_recovered is not None:
        lines.append(
            f"Avg p_pay_anyway (not recovered): {summary.avg_p_pay_anyway_not_recovered:.3f}  [evaluator-only]"
        )

    cause_counts: dict[str, int] = {}
    for record in summary.records:
        cause_counts[record.diagnosis_cause] = cause_counts.get(record.diagnosis_cause, 0) + 1
    if cause_counts:
        lines.append("Diagnosis cause mix:")
        for cause, count in sorted(cause_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"  {cause}: {count}")

    lines.append("=" * 72)
    return "\n".join(lines)


__all__ = [
    "CaseEvaluationRecord",
    "Phase3EvaluationSummary",
    "base_checkout_cause",
    "expected_checkout_causes",
    "format_checkout_evaluation_report",
    "is_checkout_diagnosis_aligned",
    "summarize_records",
]
