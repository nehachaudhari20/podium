"""Checkout-abandonment diagnosis — Phase 4B.

Uses the same DiagnosisResult interface as subscription diagnosis.
Context-aware refinement prefers derived signals when available.
"""

from __future__ import annotations

from recovery.models.case import RecoveryCaseRuntime
from recovery.models.recovery_context import RecoveryContext
from recovery.models.recovery_types import DiagnosisResult

# failure_reason → (cause, confidence, rationale)
CHECKOUT_FAILURE_TO_CAUSE: dict[str, tuple[str, float, str]] = {
    "checkout_payment_page_drop": (
        "payment_friction",
        0.84,
        "Customer reached payment stage but did not complete checkout.",
    ),
    "checkout_cart_abandon": (
        "checkout_friction",
        0.78,
        "Customer abandoned early in checkout before payment.",
    ),
    "checkout_high_intent_drop": (
        "distraction_or_delay",
        0.80,
        "High-intent session dropped; likely distraction or delay rather than low interest.",
    ),
}

CHECKOUT_CAUSES = frozenset(
    {entry[0] for entry in CHECKOUT_FAILURE_TO_CAUSE.values()}
    | {
        "price_sensitivity",
        "low_intent",
        "technical_friction",
        "unknown_abandonment",
    }
)


def diagnose_checkout(
    case: RecoveryCaseRuntime,
    context: RecoveryContext | None = None,
) -> DiagnosisResult:
    """Diagnose a checkout abandonment case from facts and optional context."""
    reason = case.failure_reason or "unknown"
    base = CHECKOUT_FAILURE_TO_CAUSE.get(reason)

    if base is not None:
        cause, confidence, rationale = base
    else:
        hint = case.recoverability_hint or "medium"
        confidence_map = {"high": 0.62, "medium": 0.48, "low": 0.32}
        cause, confidence, rationale = (
            "unknown_abandonment",
            confidence_map.get(hint, 0.40),
            f"Unmapped checkout failure '{reason}'; using recoverability hint '{hint}'.",
        )

    if context is None:
        return DiagnosisResult(likely_cause=cause, confidence=confidence, rationale=rationale)

    signals = context.derived_signals
    checkout = context.checkout

    # Context refinements — never invent data; only reweight from signals.
    if signals.high_intent and signals.payment_stage_abandonment:
        cause = "payment_friction" if cause in {"distraction_or_delay", "unknown_abandonment"} else cause
        if cause == "payment_friction":
            confidence = max(confidence, 0.86)
            rationale = (
                "High-intent payment-stage abandonment; prefer low-friction completion help."
            )
    elif signals.high_intent and signals.recent_abandonment:
        cause = "distraction_or_delay"
        confidence = max(confidence, 0.82)
        rationale = "Recent high-intent drop; reminder/payment link likely sufficient without incentive."
    elif (
        checkout is not None
        and checkout.intent_score is not None
        and checkout.intent_score < 0.45
    ) or (case.recoverability_hint == "low" and not signals.high_intent):
        cause = "low_intent"
        confidence = max(confidence, 0.75)
        rationale = "Low purchase intent signals; prefer bounded or no intervention."
    elif signals.early_stage_abandonment and signals.high_value_cart:
        cause = "price_sensitivity"
        confidence = max(0.70, confidence - 0.05)
        rationale = "Early-stage drop on high-value cart; bounded incentive may be considered under policy."
    elif signals.early_stage_abandonment:
        cause = "checkout_friction"
        confidence = max(confidence, 0.76)
        rationale = "Early checkout stage abandonment suggests friction before payment."

    if signals.customer_opt_out:
        rationale = f"{rationale} Customer opted out; contact paths constrained."

    return DiagnosisResult(likely_cause=cause, confidence=min(0.95, confidence), rationale=rationale)
