"""Structured response schemas for LLM intelligence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from podium.intelligence.diagnosis import VALID_CAUSES

_VALID_CAUSES = set(VALID_CAUSES)


@dataclass(frozen=True)
class ReasoningPayload:
    summary: str
    likely_cause: str
    confidence: float
    key_factors: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReasoningPayload:
        summary = str(data.get("summary", "")).strip()
        if not summary:
            raise ValueError("LLM reasoning response missing summary")

        likely_cause = str(data.get("likely_cause", "")).strip()
        if likely_cause not in _VALID_CAUSES:
            raise ValueError(f"Invalid likely_cause from LLM: {likely_cause!r}")

        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("LLM reasoning confidence must be numeric") from exc
        confidence = max(0.0, min(1.0, confidence))

        raw_factors = data.get("key_factors") or []
        if not isinstance(raw_factors, list):
            raise ValueError("key_factors must be a list")
        factors = tuple(str(f).strip() for f in raw_factors if str(f).strip())
        if not factors:
            factors = (likely_cause,)

        return cls(
            summary=summary,
            likely_cause=likely_cause,
            confidence=confidence,
            key_factors=factors,
        )


@dataclass(frozen=True)
class StrategyItem:
    action_id: str
    rationale: str
    priority: int
    confidence: float

    @classmethod
    def from_dict(cls, data: dict[str, Any], valid_action_ids: set[str]) -> StrategyItem:
        action_id = str(data.get("action_id", "")).strip()
        if action_id not in valid_action_ids:
            raise ValueError(f"Invalid action_id from LLM: {action_id!r}")

        rationale = str(data.get("rationale", "")).strip()
        if not rationale:
            raise ValueError(f"Strategy item for {action_id!r} missing rationale")

        try:
            priority = int(data.get("priority", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError("Strategy priority must be an integer") from exc

        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Strategy confidence must be numeric") from exc
        confidence = max(0.0, min(1.0, confidence))

        return cls(
            action_id=action_id,
            rationale=rationale,
            priority=priority,
            confidence=confidence,
        )


@dataclass(frozen=True)
class StrategyPayload:
    strategies: tuple[StrategyItem, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any], valid_action_ids: set[str]) -> StrategyPayload:
        raw = data.get("strategies") or []
        if not isinstance(raw, list) or not raw:
            raise ValueError("LLM strategy response must include non-empty strategies list")
        items = tuple(
            StrategyItem.from_dict(item, valid_action_ids)
            for item in raw
            if isinstance(item, dict)
        )
        if not items:
            raise ValueError("No valid strategy items in LLM response")
        return cls(strategies=items)


def parse_json_response(text: str) -> dict[str, Any]:
    """Parse JSON from LLM response, tolerating markdown fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object")
    return parsed
