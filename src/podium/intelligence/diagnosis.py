"""Rule-based diagnosis — Phase 2 deterministic implementation.

Phase 3 will replace ``diagnose`` with a Claude-backed implementation
using the same ``DiagnosisResult`` interface.
"""

from __future__ import annotations

from podium.models.case import RecoveryCaseRuntime
from podium.models.enums import Lane
from podium.models.recovery_types import DiagnosisResult

FAILURE_TO_CAUSE: dict[str, tuple[str, float, str]] = {
    "insufficient_funds": (
        "insufficient_funds",
        0.85,
        "Payment failed due to insufficient account balance.",
    ),
    "expired_card": (
        "expired_payment_method",
        0.92,
        "Card on file has expired and cannot be charged.",
    ),
    "invalid_card": (
        "expired_payment_method",
        0.88,
        "Payment method is invalid or no longer usable.",
    ),
    "transient_technical": (
        "transient_failure",
        0.80,
        "Technical or processor-side transient error during charge.",
    ),
    "network_timeout": (
        "transient_failure",
        0.78,
        "Network timeout interrupted the payment attempt.",
    ),
    "issuer_timeout": (
        "transient_failure",
        0.75,
        "Issuer did not respond in time; likely recoverable with retry.",
    ),
    "authentication_failure": (
        "bank_decline",
        0.70,
        "Bank or issuer declined authentication for this payment.",
    ),
    "mandate_revoked": (
        "mandate_failure",
        0.90,
        "Customer mandate was revoked; payment method update required.",
    ),
    "repeated_failure": (
        "repeated_failure",
        0.82,
        "Multiple prior failures suggest persistent recoverability issue.",
    ),
}


def diagnose(case: RecoveryCaseRuntime) -> DiagnosisResult:
    """Return a structured diagnosis for a recovery case."""
    if case.lane != Lane.SUBSCRIPTION_PAYMENT.value:
        raise ValueError(f"Phase 2 diagnosis supports subscription_payment only, got {case.lane}")

    reason = case.failure_reason or "unknown"
    if reason in FAILURE_TO_CAUSE:
        cause, confidence, rationale = FAILURE_TO_CAUSE[reason]
        return DiagnosisResult(
            likely_cause=cause,
            confidence=confidence,
            rationale=rationale,
        )

    hint = case.recoverability_hint or "medium"
    confidence_map = {"high": 0.65, "medium": 0.50, "low": 0.35}
    return DiagnosisResult(
        likely_cause="unknown_failure",
        confidence=confidence_map.get(hint, 0.45),
        rationale=f"Unmapped failure reason '{reason}'; using recoverability hint '{hint}'.",
    )
