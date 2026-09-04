"""Gemini-backed reasoning intelligence."""

from __future__ import annotations

from recovery.intelligence.contracts import ReasoningInsight, ReasoningIntelligence
from recovery.intelligence.gemini.client import GeminiStructuredClient
from recovery.intelligence.gemini.config import GeminiConfig
from recovery.intelligence.llm.prompts import build_reasoning_prompt
from recovery.intelligence.llm.schemas import ReasoningPayload
from recovery.models.recovery_context import RecoveryContext


class GeminiReasoningIntelligence:
    """Uses Gemini to interpret RecoveryContext into a ReasoningInsight proposal."""

    def __init__(
        self,
        client: GeminiStructuredClient | None = None,
        config: GeminiConfig | None = None,
    ) -> None:
        self._client = client or GeminiStructuredClient(config=config)

    def interpret(self, context: RecoveryContext) -> ReasoningInsight:
        system, user = build_reasoning_prompt(context)
        raw = self._client.complete_json(system=system, user=user)
        payload = ReasoningPayload.from_dict(raw)
        return ReasoningInsight(
            summary=payload.summary,
            likely_cause=payload.likely_cause,
            confidence=payload.confidence,
            key_factors=payload.key_factors,
            source="gemini",
        )


_: ReasoningIntelligence = GeminiReasoningIntelligence()
