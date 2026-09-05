"""Deterministic economic decision engine — ranks candidates by expected net value."""

from __future__ import annotations

from typing import TYPE_CHECKING

from recovery.economics.config import EconomicsConfig, intervention_cost_for, load_economics_config
from recovery.economics.model import EconomicCandidate, EconomicDecision, evaluate_action_economics
from recovery.intelligence.contracts import PredictiveSignals
from recovery.models.recovery_types import RecoveryAction

if TYPE_CHECKING:
    from recovery.learning.store import ExperienceStore


def probability_for_action(
    action: RecoveryAction,
    predictive: PredictiveSignals,
    *,
    last_action: str | None = None,
    experience_store: "ExperienceStore | None" = None,
    lane: str | None = None,
    diagnosis: str | None = None,
) -> float:
    """Map predictive signals to an action-specific recovery probability estimate.

    Distinct from the hidden evaluator-only pay-anyway ground truth — runtime estimate only.
    Optional historical evidence may blend into the model probability (Phase 8).
    """
    base = predictive.estimated_recovery_probability
    if action.action_id in {"stop_recovery", "defer"}:
        return 0.0
    if action.is_retry:
        prob = predictive.retry_success_likelihood
    elif action.action_id == "human_escalation":
        # No artificial probability inflation — cost must justify selection via net value.
        prob = min(0.95, base)
    elif action.action_id == "escalate_collections":
        prob = min(0.92, base)
    elif action.action_id == "voice_call":
        prob = min(0.90, base + 0.05)
    elif action.action_id in {"limited_incentive", "offer_discount"}:
        prob = min(0.90, base + 0.08)
    elif action.action_id == "payment_method_update":
        # Prefer method-update mainly when retries alone look weak (e.g. expired card).
        if predictive.retry_success_likelihood <= 0.28:
            prob = (base + predictive.responsiveness_score) / 2.0
        else:
            prob = base * 0.55
    elif action.action_id == "track_promise_to_pay":
        prob = min(0.85, base + 0.05)
    elif action.action_id == "promise_to_pay_request":
        # Structured commitment — competitive with human on probability; cost decides.
        prob = min(0.90, base + 0.08)
    elif action.action_id == "invoice_reminder":
        prob = (base + predictive.responsiveness_score) / 2.0
    elif action.is_contact:
        prob = (base + predictive.responsiveness_score) / 2.0
    else:
        prob = base

    # Discourage immediately repeating a failed intervention (supports re-plan diversity).
    if last_action and action.action_id == last_action:
        prob *= 0.35
    elif last_action and action.action_id in {"checkout_reminder", "invoice_reminder"}:
        # After any prior outreach, a plain reminder is less valuable than a new tactic.
        prob *= 0.55

    model_prob = round(min(0.99, max(0.0, prob)), 4)
    if experience_store is None:
        return model_prob

    from recovery.learning.blend import blend_from_store

    blended = blend_from_store(
        experience_store,
        action=action.action_id,
        lane=lane,
        model_probability=model_prob,
        diagnosis=diagnosis,
    )
    return blended.blended_probability


def evaluate_candidates(
    actions: list[RecoveryAction],
    *,
    amount_at_risk: float,
    predictive: PredictiveSignals,
    config: EconomicsConfig | None = None,
    last_action: str | None = None,
    experience_store: "ExperienceStore | None" = None,
    lane: str | None = None,
    diagnosis: str | None = None,
) -> list[EconomicCandidate]:
    cfg = config or load_economics_config()
    candidates: list[EconomicCandidate] = []
    for action in actions:
        prob = probability_for_action(
            action,
            predictive,
            last_action=last_action,
            experience_store=experience_store,
            lane=lane,
            diagnosis=diagnosis,
        )
        cost = intervention_cost_for(action.action_id, amount_at_risk, cfg)
        candidates.append(
            evaluate_action_economics(
                action,
                amount_at_risk=amount_at_risk,
                probability=prob,
                intervention_cost=cost,
                minimum_expected_net_value=cfg.minimum_expected_net_value,
                minimum_recovery_probability=cfg.minimum_recovery_probability,
                maximum_intervention_cost=cfg.maximum_intervention_cost,
            )
        )
    return candidates


def rank_eligible(candidates: list[EconomicCandidate]) -> list[EconomicCandidate]:
    """Rank eligible interventions by expected net value (desc), then lower cost."""
    eligible = [c for c in candidates if c.eligible and c.action_id not in {"stop_recovery", "defer"}]
    return sorted(
        eligible,
        key=lambda c: (c.expected_net_value, -c.intervention_cost),
        reverse=True,
    )


def select_best_economic_action(
    actions: list[RecoveryAction],
    *,
    amount_at_risk: float,
    predictive: PredictiveSignals,
    config: EconomicsConfig | None = None,
    last_action: str | None = None,
    experience_store: "ExperienceStore | None" = None,
    lane: str | None = None,
    diagnosis: str | None = None,
) -> EconomicDecision:
    """Decision 1: which action for this case maximizes expected net value."""
    cfg = config or load_economics_config()
    kwargs = dict(
        amount_at_risk=amount_at_risk,
        predictive=predictive,
        config=cfg,
        last_action=last_action,
        experience_store=experience_store,
        lane=lane,
        diagnosis=diagnosis,
    )
    if not cfg.enabled:
        candidates = evaluate_candidates(actions, **kwargs)
        selected = candidates[0] if candidates else None
        return EconomicDecision(
            candidates=tuple(candidates),
            selected=selected,
            economic_reason="economics_disabled_passthrough",
        )

    candidates = evaluate_candidates(actions, **kwargs)
    ranked = rank_eligible(candidates)
    if ranked:
        best = ranked[0]
        return EconomicDecision(
            candidates=tuple(candidates),
            selected=best,
            economic_reason="highest_positive_expected_net_value",
        )

    for candidate in candidates:
        if candidate.action_id in {"stop_recovery", "defer"} and candidate.eligible:
            return EconomicDecision(
                candidates=tuple(candidates),
                selected=candidate,
                economic_reason="all_interventions_uneconomic_stop",
            )

    return EconomicDecision(
        candidates=tuple(candidates),
        selected=None,
        economic_reason="no_economically_eligible_action",
    )


def economically_ordered_actions(decision: EconomicDecision) -> list[RecoveryAction]:
    """Return actions ordered for policy: ranked eligible first, then stop/defer, then rest."""
    ranked = rank_eligible(list(decision.candidates))
    ordered_ids = {c.action_id for c in ranked}
    stop = [
        c.action
        for c in decision.candidates
        if c.action_id in {"stop_recovery", "defer"} and c.action_id not in ordered_ids
    ]
    rest = [
        c.action
        for c in decision.candidates
        if c.action_id not in ordered_ids and c.action_id not in {"stop_recovery", "defer"}
    ]
    return [c.action for c in ranked] + stop + rest
