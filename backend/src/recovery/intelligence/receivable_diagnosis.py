"""Receivable-lane diagnosis — Phase 7."""

from __future__ import annotations

from recovery.models.case import RecoveryCaseRuntime
from recovery.models.recovery_context import RecoveryContext
from recovery.models.recovery_types import DiagnosisResult

RECEIVABLE_FAILURE_TO_CAUSE: dict[str, tuple[str, float, str]] = {
    "invoice_mild_overdue": (
        "customer_oversight",
        0.78,
        "Recently overdue invoice; likely oversight or processing delay.",
    ),
    "invoice_aged_overdue": (
        "temporary_cash_constraint",
        0.72,
        "Aged overdue invoice; temporary cash or approval delay is plausible.",
    ),
    "invoice_severely_overdue": (
        "low_responsiveness",
        0.80,
        "Severely overdue with weak responsiveness signals.",
    ),
    "promise_missed": (
        "low_responsiveness",
        0.84,
        "Prior promise was missed; stronger follow-up may be required.",
    ),
}

RECEIVABLE_CAUSES = frozenset(
    {entry[0] for entry in RECEIVABLE_FAILURE_TO_CAUSE.values()}
    | {
        "payment_processing_delay",
        "approval_delay",
        "invoice_dispute",
        "high_value_account",
        "unknown_receivable_risk",
    }
)


def diagnose_receivable(
    case: RecoveryCaseRuntime,
    context: RecoveryContext | None = None,
) -> DiagnosisResult:
    reason = case.failure_reason or "unknown"
    base = RECEIVABLE_FAILURE_TO_CAUSE.get(reason)
    if base is not None:
        cause, confidence, rationale = base
    else:
        days = case.days_overdue or 0
        if days <= 7:
            cause, confidence, rationale = (
                "customer_oversight",
                0.65,
                f"Unmapped receivable failure '{reason}' with mild overdue ({days}d).",
            )
        elif days <= 30:
            cause, confidence, rationale = (
                "temporary_cash_constraint",
                0.60,
                f"Unmapped receivable failure '{reason}' with moderate overdue ({days}d).",
            )
        else:
            cause, confidence, rationale = (
                "unknown_receivable_risk",
                0.45,
                f"Unmapped receivable failure '{reason}' with aged overdue ({days}d).",
            )

    if context is None:
        return DiagnosisResult(likely_cause=cause, confidence=confidence, rationale=rationale)

    signals = context.derived_signals
    invoice = context.invoice
    days = case.days_overdue or (invoice.days_overdue if invoice else 0)

    if signals.customer_opt_out:
        rationale = f"{rationale} Customer opted out; contact paths constrained."

    if invoice is not None and invoice.amount >= 50000 and days <= 45:
        confidence = max(confidence, 0.74)
        rationale = (
            f"{rationale} High-value overdue account; "
            "economics may justify stronger intervention when warranted."
        )
    if signals.active_promise:
        rationale = f"{rationale} Active promise exists; avoid aggressive duplicate outreach."

    if signals.promise_broken_before or reason == "promise_missed":
        cause = "low_responsiveness"
        confidence = max(confidence, 0.82)
        rationale = "Broken or missed promise history; escalate follow-up carefully."

    if days >= 45 and cause not in {"invoice_dispute", "low_responsiveness"}:
        cause = "low_responsiveness"
        confidence = max(confidence, 0.78)
        rationale = "Long-aged receivable; responsiveness risk dominates."

    return DiagnosisResult(
        likely_cause=cause,
        confidence=min(0.95, confidence),
        rationale=rationale,
    )
