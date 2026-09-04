"""Deterministic decision composer — combines intelligence components."""

from __future__ import annotations

from podium.intelligence.contracts import (
    DecisionIntelligence,
    DecisionProposal,
    PredictiveIntelligence,
    ReasoningIntelligence,
    StrategyIntelligence,
)
from podium.intelligence.deterministic.predictive import DeterministicPredictiveIntelligence
from podium.intelligence.deterministic.reasoning import DeterministicReasoningIntelligence
from podium.intelligence.deterministic.strategy import DeterministicStrategyIntelligence
from podium.models.recovery_context import RecoveryContext
from podium.models.recovery_types import RecoveryAction


class DeterministicDecisionIntelligence:
    """Composes a decision proposal from deterministic intelligence layers."""

    def __init__(
        self,
        predictive: PredictiveIntelligence | None = None,
        reasoning: ReasoningIntelligence | None = None,
        strategy: StrategyIntelligence | None = None,
    ) -> None:
        self._predictive = predictive or DeterministicPredictiveIntelligence()
        self._reasoning = reasoning or DeterministicReasoningIntelligence()
        self._strategy = strategy or DeterministicStrategyIntelligence()

    def propose_decision(self, context: RecoveryContext) -> DecisionProposal:
        predictive = self._predictive.score(context)
        reasoning = self._reasoning.interpret(context)
        strategy_proposals = self._strategy.propose_strategies(context, reasoning, predictive)

        if not strategy_proposals:
            raise ValueError("No strategy proposals generated for context.")

        recommended = strategy_proposals[0].action
        candidates = tuple(p.action for p in strategy_proposals)
        explanation = self._build_explanation(context, reasoning, recommended)

        proposal = DecisionProposal(
            recommended_action=recommended,
            candidate_actions=candidates,
            reasoning=reasoning,
            predictive=predictive,
            strategy_proposals=strategy_proposals,
            explanation=explanation,
            source="deterministic",
        )
        proposal.validate_no_forbidden_fields()
        return proposal

    def _build_explanation(
        self,
        context: RecoveryContext,
        reasoning,
        recommended: RecoveryAction,
    ) -> str:
        return (
            f"Given {reasoning.likely_cause} with factors {', '.join(reasoning.key_factors)}, "
            f"recommend {recommended.action_id} for case {context.case.case_id}."
        )


def propose_deterministic_decision(context: RecoveryContext) -> DecisionProposal:
    """Convenience wrapper for the default deterministic decision stack."""
    return DeterministicDecisionIntelligence().propose_decision(context)


_: DecisionIntelligence = DeterministicDecisionIntelligence()
