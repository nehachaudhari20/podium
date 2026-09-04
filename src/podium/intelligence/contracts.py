"""Intelligence layer contracts — Phase 3B hybrid decision boundary.

These protocols define how predictive, reasoning, and strategy components
propose recovery decisions. Implementations propose; deterministic policy
and state systems remain authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from podium.models.recovery_context import RecoveryContext, assert_no_forbidden_fields
from podium.models.recovery_types import RecoveryAction


@dataclass(frozen=True, slots=True)
class PredictiveSignals:
    """Non-LLM statistical-style scores (deterministic or ML-backed later)."""

    estimated_recovery_probability: float
    retry_success_likelihood: float
    responsiveness_score: float
    source: str = "deterministic"


@dataclass(frozen=True, slots=True)
class ReasoningInsight:
    """Interpretation of evidence — reasoning, not execution authority."""

    summary: str
    likely_cause: str
    confidence: float
    key_factors: tuple[str, ...]
    source: str = "deterministic"


@dataclass(frozen=True, slots=True)
class StrategyProposal:
    """One candidate recovery strategy with explainable metadata."""

    action: RecoveryAction
    rationale: str
    priority: int
    confidence: float
    source: str = "deterministic"


@dataclass(frozen=True, slots=True)
class DecisionProposal:
    """Combined proposal from intelligence layers — subject to policy validation."""

    recommended_action: RecoveryAction
    candidate_actions: tuple[RecoveryAction, ...]
    reasoning: ReasoningInsight
    predictive: PredictiveSignals
    strategy_proposals: tuple[StrategyProposal, ...]
    explanation: str
    source: str = "deterministic"

    def to_dict(self) -> dict:
        from dataclasses import asdict

        return asdict(self)

    def validate_no_forbidden_fields(self) -> None:
        assert_no_forbidden_fields(self.to_dict())


class PredictiveIntelligence(Protocol):
    """Scores recovery likelihood from structured context."""

    def score(self, context: RecoveryContext) -> PredictiveSignals: ...


class ReasoningIntelligence(Protocol):
    """Interprets case/customer/history evidence."""

    def interpret(self, context: RecoveryContext) -> ReasoningInsight: ...


class StrategyIntelligence(Protocol):
    """Generates ranked candidate strategies."""

    def propose_strategies(
        self,
        context: RecoveryContext,
        reasoning: ReasoningInsight,
        predictive: PredictiveSignals,
    ) -> tuple[StrategyProposal, ...]: ...


class DecisionIntelligence(Protocol):
    """Composes a decision proposal from intelligence components."""

    def propose_decision(self, context: RecoveryContext) -> DecisionProposal: ...
