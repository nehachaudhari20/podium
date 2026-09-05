"""Load economic costs, thresholds, and capacity limits from config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from recovery.config import load_actions, load_economics


@dataclass(frozen=True, slots=True)
class CapacityLimits:
    max_voice_calls_per_batch: int
    max_human_escalations_per_batch: int
    max_incentive_budget: float


@dataclass(frozen=True, slots=True)
class EconomicsConfig:
    enabled: bool
    minimum_expected_net_value: float
    minimum_recovery_probability: float
    maximum_intervention_cost: float | None
    incentive_cost_pct: float
    action_costs: dict[str, float]
    scarce_capacity: dict[str, str]
    capacity: CapacityLimits


def load_economics_config(config_dir: Path | None = None) -> EconomicsConfig:
    raw = load_economics(config_dir)
    actions_raw = load_actions(config_dir)
    catalog_costs: dict[str, float] = {}
    for entry in actions_raw.get("actions") or []:
        catalog_costs[str(entry["id"])] = float(entry.get("base_cost", 0))

    overrides = {str(k): float(v) for k, v in (raw.get("action_costs") or {}).items()}
    merged = dict(catalog_costs)
    merged.update(
        {
            "payment_method_update": catalog_costs.get("request_payment_method_update", 2.0),
            "retry_6h": catalog_costs.get("retry_payment", 1.0),
            "retry_24h": catalog_costs.get("wait_and_retry", 1.0),
            "retry_72h": catalog_costs.get("wait_and_retry", 1.0),
            "retry_after_update": catalog_costs.get("retry_payment", 1.0),
        }
    )
    merged.update(overrides)

    cap_raw = raw.get("capacity") or {}
    capacity = CapacityLimits(
        max_voice_calls_per_batch=int(cap_raw.get("max_voice_calls_per_batch", 10)),
        max_human_escalations_per_batch=int(cap_raw.get("max_human_escalations_per_batch", 5)),
        max_incentive_budget=float(cap_raw.get("max_incentive_budget", 5000)),
    )

    max_cost = raw.get("maximum_intervention_cost", None)
    return EconomicsConfig(
        enabled=bool(raw.get("enabled", True)),
        minimum_expected_net_value=float(raw.get("minimum_expected_net_value", 0.0)),
        minimum_recovery_probability=float(raw.get("minimum_recovery_probability", 0.0)),
        maximum_intervention_cost=float(max_cost) if max_cost is not None else None,
        incentive_cost_pct=float(raw.get("incentive_cost_pct", 10.0)),
        action_costs=merged,
        scarce_capacity={str(k): str(v) for k, v in (raw.get("scarce_capacity") or {}).items()},
        capacity=capacity,
    )


def intervention_cost_for(
    action_id: str,
    amount_at_risk: float,
    config: EconomicsConfig,
) -> float:
    if action_id in {"limited_incentive", "offer_discount"}:
        return round(amount_at_risk * (config.incentive_cost_pct / 100.0), 4)
    return float(config.action_costs.get(action_id, 0.0))
