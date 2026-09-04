"""Gemini-backed strategy intelligence."""

from __future__ import annotations

from recovery.intelligence.contracts import (
    PredictiveSignals,
    ReasoningInsight,
    StrategyIntelligence,
    StrategyProposal,
)
from recovery.intelligence.gemini.client import GeminiStructuredClient
from recovery.intelligence.gemini.config import GeminiConfig
from recovery.intelligence.llm.prompts import action_metadata, build_strategy_prompt, valid_action_ids
from recovery.intelligence.llm.schemas import StrategyPayload
from recovery.models.recovery_context import RecoveryContext
from recovery.models.recovery_types import RecoveryAction

_RETRY_IDS = frozenset({"retry_payment", "wait_and_retry"})
_CONTACT_PREFIXES = ("send_",)
_CONTACT_IDS = frozenset(
    {"send_email", "send_whatsapp", "send_sms", "voice_call", "request_payment_method_update", "human_escalation"}
)


def _action_from_id(action_id: str) -> RecoveryAction:
    meta = action_metadata(action_id)
    is_retry = action_id in _RETRY_IDS
    is_contact = action_id in _CONTACT_IDS or any(action_id.startswith(p) for p in _CONTACT_PREFIXES)
    return RecoveryAction(
        action_id=action_id,
        label=meta["label"],
        channel=meta["channel"],
        is_retry=is_retry,
        is_contact=is_contact,
    )


class GeminiStrategyIntelligence:
    """Uses Gemini to propose ranked recovery strategies from context + reasoning."""

    def __init__(
        self,
        client: GeminiStructuredClient | None = None,
        config: GeminiConfig | None = None,
    ) -> None:
        self._client = client or GeminiStructuredClient(config=config)
        self._valid_actions = valid_action_ids()

    def propose_strategies(
        self,
        context: RecoveryContext,
        reasoning: ReasoningInsight,
        predictive: PredictiveSignals,
    ) -> tuple[StrategyProposal, ...]:
        del predictive  # reserved for future prompt conditioning
        system, user = build_strategy_prompt(
            context,
            reasoning_summary=reasoning.summary,
            likely_cause=reasoning.likely_cause,
        )
        raw = self._client.complete_json(system=system, user=user)
        payload = StrategyPayload.from_dict(raw, self._valid_actions)
        ranked = sorted(payload.strategies, key=lambda s: s.priority)
        return tuple(
            StrategyProposal(
                action=_action_from_id(item.action_id),
                rationale=item.rationale,
                priority=item.priority,
                confidence=item.confidence,
                source="gemini",
            )
            for item in ranked
        )


_: StrategyIntelligence = GeminiStrategyIntelligence()
