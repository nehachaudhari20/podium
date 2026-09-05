"""Bounded probability blending with historical evidence (Phase 8)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from recovery.learning.config import LearningConfig, load_learning_config
from recovery.learning.effectiveness import (
    HistoricalEvidence,
    confidence_for_count,
    get_historical_evidence,
    smoothed_success_rate,
)
from recovery.learning.store import ExperienceStore


@dataclass(frozen=True, slots=True)
class BlendedProbability:
    action: str
    lane: str | None
    model_probability: float
    historical_success_rate: float | None
    blended_probability: float
    alpha: float
    observations: int
    confidence: str
    used_history: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clamp_probability(value: float, config: LearningConfig | None = None) -> float:
    cfg = config or load_learning_config()
    return round(min(cfg.max_probability, max(cfg.min_probability, value)), 4)


def blend_probability(
    model_probability: float,
    evidence: HistoricalEvidence | None,
    *,
    config: LearningConfig | None = None,
) -> BlendedProbability:
    cfg = config or load_learning_config()
    model_p = clamp_probability(model_probability, cfg)
    action = evidence.action if evidence else "unknown"
    lane = evidence.lane if evidence else None

    if not cfg.enabled:
        return BlendedProbability(
            action=action,
            lane=lane,
            model_probability=model_p,
            historical_success_rate=None,
            blended_probability=model_p,
            alpha=cfg.alpha,
            observations=0,
            confidence="low",
            used_history=False,
            reason="learning_disabled",
        )

    if evidence is None or evidence.observations == 0:
        return BlendedProbability(
            action=action,
            lane=lane,
            model_probability=model_p,
            historical_success_rate=None,
            blended_probability=model_p,
            alpha=cfg.alpha,
            observations=0,
            confidence="low",
            used_history=False,
            reason="cold_start_no_history",
        )

    hist = smoothed_success_rate(evidence.successes, evidence.observations, cfg)
    if evidence.observations < cfg.min_observations_for_blend:
        soft_alpha = min(0.9, cfg.alpha + 0.15)
        blended = soft_alpha * model_p + (1.0 - soft_alpha) * hist
        return BlendedProbability(
            action=action,
            lane=lane,
            model_probability=model_p,
            historical_success_rate=round(hist, 4),
            blended_probability=clamp_probability(blended, cfg),
            alpha=soft_alpha,
            observations=evidence.observations,
            confidence=confidence_for_count(evidence.observations, cfg),
            used_history=True,
            reason="insufficient_samples_soft_blend",
        )

    blended = cfg.alpha * model_p + (1.0 - cfg.alpha) * hist
    return BlendedProbability(
        action=action,
        lane=lane,
        model_probability=model_p,
        historical_success_rate=round(hist, 4),
        blended_probability=clamp_probability(blended, cfg),
        alpha=cfg.alpha,
        observations=evidence.observations,
        confidence=confidence_for_count(evidence.observations, cfg),
        used_history=True,
        reason="historical_blend",
    )


def blend_from_store(
    store: ExperienceStore,
    *,
    action: str,
    lane: str | None,
    model_probability: float,
    diagnosis: str | None = None,
    config: LearningConfig | None = None,
) -> BlendedProbability:
    evidence = get_historical_evidence(
        store, action=action, lane=lane, diagnosis=diagnosis, config=config
    )
    if evidence.observations == 0 and diagnosis is not None:
        evidence = get_historical_evidence(store, action=action, lane=lane, config=config)
    if evidence.observations == 0 and lane is not None:
        evidence = get_historical_evidence(store, action=action, config=config)
    return blend_probability(model_probability, evidence, config=config)
