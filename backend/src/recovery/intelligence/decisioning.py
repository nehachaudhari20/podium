"""Hybrid decision intelligence with Gemini + deterministic fallback (Phase 3D)."""

from __future__ import annotations

from recovery.intelligence.action_bridge import map_strategy_proposals_to_runtime
from recovery.intelligence.contracts import (
    DecisionIntelligence,
    DecisionProposal,
    PredictiveIntelligence,
    ReasoningIntelligence,
    StrategyIntelligence,
    StrategyProposal,
)
from recovery.intelligence.decision_config import DecisionConfig
from recovery.intelligence.deterministic.decision import DeterministicDecisionIntelligence
from recovery.intelligence.deterministic.predictive import DeterministicPredictiveIntelligence
from recovery.intelligence.deterministic.reasoning import DeterministicReasoningIntelligence
from recovery.intelligence.deterministic.strategy import DeterministicStrategyIntelligence
from recovery.intelligence.gemini.config import GeminiConfig
from recovery.intelligence.gemini.reasoning import GeminiReasoningIntelligence
from recovery.intelligence.gemini.strategy import GeminiStrategyIntelligence
from recovery.models.recovery_context import RecoveryContext
from recovery.models.recovery_types import RecoveryAction


class HybridDecisionIntelligence:
    """Compose DecisionProposal using Gemini when configured, else deterministic stack."""

    def __init__(
        self,
        config: DecisionConfig | None = None,
        predictive: PredictiveIntelligence | None = None,
        deterministic_reasoning: ReasoningIntelligence | None = None,
        deterministic_strategy: StrategyIntelligence | None = None,
        gemini_reasoning: ReasoningIntelligence | None = None,
        gemini_strategy: StrategyIntelligence | None = None,
    ) -> None:
        self._config = config or DecisionConfig.from_env()
        self._predictive = predictive or DeterministicPredictiveIntelligence()
        self._deterministic = DeterministicDecisionIntelligence(
            predictive=self._predictive,
            reasoning=deterministic_reasoning or DeterministicReasoningIntelligence(),
            strategy=deterministic_strategy or DeterministicStrategyIntelligence(),
        )
        self._gemini_reasoning = gemini_reasoning or GeminiReasoningIntelligence()
        self._gemini_strategy = gemini_strategy or GeminiStrategyIntelligence()

    @property
    def config(self) -> DecisionConfig:
        return self._config

    def propose_decision(self, context: RecoveryContext) -> DecisionProposal:
        if not self._config.use_gemini() or not self._config.gemini_available():
            return self._deterministic.propose_decision(context)

        try:
            return self._propose_gemini(context)
        except Exception:
            if self._config.allow_fallback():
                return self._deterministic.propose_decision(context)
            raise

    def _propose_gemini(self, context: RecoveryContext) -> DecisionProposal:
        reasoning = self._gemini_reasoning.interpret(context)
        if reasoning.confidence < self._config.min_reasoning_confidence:
            if self._config.allow_fallback():
                return self._deterministic.propose_decision(context)
            raise ValueError(
                f"Gemini reasoning confidence {reasoning.confidence} below threshold "
                f"{self._config.min_reasoning_confidence}"
            )

        predictive = self._predictive.score(context)
        gemini_strategies = self._gemini_strategy.propose_strategies(context, reasoning, predictive)
        if not gemini_strategies:
            if self._config.allow_fallback():
                return self._deterministic.propose_decision(context)
            raise ValueError("Gemini returned no strategy proposals")

        top_confidence = gemini_strategies[0].confidence
        if top_confidence < self._config.min_strategy_confidence:
            if self._config.allow_fallback():
                return self._deterministic.propose_decision(context)
            raise ValueError(
                f"Gemini strategy confidence {top_confidence} below threshold "
                f"{self._config.min_strategy_confidence}"
            )

        runtime_actions = map_strategy_proposals_to_runtime(
            [proposal.action.action_id for proposal in gemini_strategies],
            reasoning.likely_cause,
        )
        if not runtime_actions:
            if self._config.allow_fallback():
                return self._deterministic.propose_decision(context)
            raise ValueError("No Gemini catalog actions mapped to executable runtime actions")

        runtime_proposals = _runtime_strategy_proposals(gemini_strategies, runtime_actions)
        recommended = runtime_actions[0]
        explanation = (
            f"[gemini] {reasoning.summary} Recommend {recommended.action_id} "
            f"for case {context.case.case_id}."
        )

        proposal = DecisionProposal(
            recommended_action=recommended,
            candidate_actions=tuple(runtime_actions),
            reasoning=reasoning,
            predictive=predictive,
            strategy_proposals=runtime_proposals,
            explanation=explanation,
            source="gemini",
        )
        proposal.validate_no_forbidden_fields()
        return proposal


def _runtime_strategy_proposals(
    gemini_strategies: tuple[StrategyProposal, ...],
    runtime_actions: list[RecoveryAction],
) -> tuple[StrategyProposal, ...]:
    """Align mapped runtime actions with Gemini rationales by priority order."""
    proposals: list[StrategyProposal] = []
    for idx, action in enumerate(runtime_actions):
        source = gemini_strategies[min(idx, len(gemini_strategies) - 1)]
        proposals.append(
            StrategyProposal(
                action=action,
                rationale=source.rationale,
                priority=idx + 1,
                confidence=source.confidence,
                source="gemini",
            )
        )
    return tuple(proposals)


def propose_hybrid_decision(context: RecoveryContext) -> DecisionProposal:
    """Convenience wrapper for the default hybrid decision stack."""
    return HybridDecisionIntelligence().propose_decision(context)


_: DecisionIntelligence = HybridDecisionIntelligence()
