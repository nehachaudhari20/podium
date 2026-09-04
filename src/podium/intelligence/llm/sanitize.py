"""Sanitize recovery context for LLM prompts — no forbidden evaluator fields."""

from __future__ import annotations

from typing import Any

from podium.models.recovery_context import RecoveryContext, assert_no_forbidden_fields

_FORBIDDEN_SUBSTRINGS = (
    "p_pay_anyway",
    "ground_truth",
    "case_ground_truth",
)


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        for key, value in obj.items():
            key_lower = key.lower()
            if any(f in key_lower for f in _FORBIDDEN_SUBSTRINGS):
                continue
            cleaned[key] = _scrub(value)
        return cleaned
    if isinstance(obj, list):
        return [_scrub(item) for item in obj]
    return obj


def context_for_prompt(context: RecoveryContext) -> dict[str, Any]:
    """Build a loggable, evaluator-safe dict for LLM prompts."""
    assert_no_forbidden_fields(context.to_dict())
    raw = context.to_loggable_dict()
    return _scrub(raw)
