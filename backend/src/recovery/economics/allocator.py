"""Explainable greedy capacity allocation for scarce recovery resources."""

from __future__ import annotations

from dataclasses import dataclass, field

from recovery.economics.config import CapacityLimits, EconomicsConfig, load_economics_config
from recovery.economics.model import EconomicCandidate


@dataclass
class CapacityPool:
    """Mutable remaining capacity for a batch (or single-run tracker)."""

    voice_calls_remaining: int
    human_escalations_remaining: int
    incentive_budget_remaining: float

    @classmethod
    def from_limits(cls, limits: CapacityLimits) -> CapacityPool:
        return cls(
            voice_calls_remaining=limits.max_voice_calls_per_batch,
            human_escalations_remaining=limits.max_human_escalations_per_batch,
            incentive_budget_remaining=limits.max_incentive_budget,
        )

    @classmethod
    def from_config(cls, config: EconomicsConfig | None = None) -> CapacityPool:
        cfg = config or load_economics_config()
        return cls.from_limits(cfg.capacity)

    @classmethod
    def unlimited(cls) -> CapacityPool:
        return cls(
            voice_calls_remaining=10**9,
            human_escalations_remaining=10**9,
            incentive_budget_remaining=1e18,
        )

    def can_allocate(self, pool_key: str, cost: float = 0.0) -> bool:
        if pool_key == "voice_call":
            return self.voice_calls_remaining > 0
        if pool_key == "human_escalation":
            return self.human_escalations_remaining > 0
        if pool_key == "incentive_budget":
            return self.incentive_budget_remaining >= cost
        return True

    def consume(self, pool_key: str, cost: float = 0.0) -> None:
        if pool_key == "voice_call":
            self.voice_calls_remaining = max(0, self.voice_calls_remaining - 1)
        elif pool_key == "human_escalation":
            self.human_escalations_remaining = max(0, self.human_escalations_remaining - 1)
        elif pool_key == "incentive_budget":
            self.incentive_budget_remaining = max(0.0, self.incentive_budget_remaining - cost)


@dataclass(frozen=True, slots=True)
class AllocationRequest:
    """One case/action competing for scarce capacity."""

    case_id: str
    candidate: EconomicCandidate


@dataclass(frozen=True, slots=True)
class AllocationResult:
    case_id: str
    action_id: str
    expected_net_value: float
    decision: str  # selected | deferred | rejected
    reason: str


@dataclass
class BatchAllocationReport:
    selected: list[AllocationResult] = field(default_factory=list)
    deferred: list[AllocationResult] = field(default_factory=list)
    rejected: list[AllocationResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        def _row(r: AllocationResult) -> dict:
            return {
                "case_id": r.case_id,
                "action_id": r.action_id,
                "expected_net_value": r.expected_net_value,
                "decision": r.decision,
                "reason": r.reason,
            }

        return {
            "selected": [_row(r) for r in self.selected],
            "deferred": [_row(r) for r in self.deferred],
            "rejected": [_row(r) for r in self.rejected],
        }


def capacity_pool_key(action_id: str, config: EconomicsConfig) -> str | None:
    return config.scarce_capacity.get(action_id)


def try_reserve_capacity(
    pool: CapacityPool | None,
    action_id: str,
    intervention_cost: float,
    config: EconomicsConfig,
) -> tuple[bool, str]:
    """Attempt to reserve scarce capacity for one action. Returns (ok, reason)."""
    if pool is None:
        return True, "capacity_unconstrained"
    key = capacity_pool_key(action_id, config)
    if key is None:
        return True, "action_not_capacity_gated"
    if not pool.can_allocate(key, intervention_cost):
        return False, (
            "economic_value_positive_but_scarce_capacity_allocated_to_higher_value_cases"
            if key != "incentive_budget"
            else "incentive_budget_exhausted"
        )
    pool.consume(key, intervention_cost)
    return True, "capacity_allocated"


def allocate_batch(
    requests: list[AllocationRequest],
    *,
    config: EconomicsConfig | None = None,
    pool: CapacityPool | None = None,
) -> BatchAllocationReport:
    """Decision 2: greedy allocation of scarce capacity by expected net value."""
    cfg = config or load_economics_config()
    capacity = pool or CapacityPool.from_config(cfg)
    report = BatchAllocationReport()

    # Reject ineligible first
    competing: list[AllocationRequest] = []
    for req in requests:
        if not req.candidate.eligible:
            report.rejected.append(
                AllocationResult(
                    case_id=req.case_id,
                    action_id=req.candidate.action_id,
                    expected_net_value=req.candidate.expected_net_value,
                    decision="rejected",
                    reason=req.candidate.reason,
                )
            )
        else:
            competing.append(req)

    competing.sort(key=lambda r: r.candidate.expected_net_value, reverse=True)

    for req in competing:
        key = capacity_pool_key(req.candidate.action_id, cfg)
        if key is None:
            report.selected.append(
                AllocationResult(
                    case_id=req.case_id,
                    action_id=req.candidate.action_id,
                    expected_net_value=req.candidate.expected_net_value,
                    decision="selected",
                    reason="not_capacity_constrained",
                )
            )
            continue

        ok, reason = try_reserve_capacity(
            capacity, req.candidate.action_id, req.candidate.intervention_cost, cfg
        )
        if ok:
            report.selected.append(
                AllocationResult(
                    case_id=req.case_id,
                    action_id=req.candidate.action_id,
                    expected_net_value=req.candidate.expected_net_value,
                    decision="selected",
                    reason=reason,
                )
            )
        else:
            report.deferred.append(
                AllocationResult(
                    case_id=req.case_id,
                    action_id=req.candidate.action_id,
                    expected_net_value=req.candidate.expected_net_value,
                    decision="deferred",
                    reason=reason,
                )
            )

    return report
