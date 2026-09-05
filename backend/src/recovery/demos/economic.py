"""Run and validate economic decision demonstration scenarios (Phase 5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from recovery.economics.allocator import (
    AllocationRequest,
    CapacityPool,
    allocate_batch,
)
from recovery.economics.config import CapacityLimits, EconomicsConfig, load_economics_config
from recovery.economics.engine import select_best_economic_action
from recovery.economics.model import evaluate_action_economics
from recovery.ingestion.customer_loader import CustomerContext
from recovery.intelligence.contracts import (
    DecisionProposal,
    PredictiveSignals,
    ReasoningInsight,
    StrategyProposal,
)
from recovery.intelligence.decision_evaluator import evaluate_decision_proposal
from recovery.models.case import RecoveryCaseRuntime
from recovery.models.enums import Lane
from recovery.models.recovery_types import RecoveryAction
from recovery.paths import SCENARIOS_DIR
from datetime import datetime, timedelta

DEFAULT_ECONOMIC_SCENARIO_FILE = SCENARIOS_DIR / "economic_demos.yaml"


@dataclass
class EconomicDemoOutcome:
    scenario_id: str
    title: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class EconomicDemoReport:
    outcomes: list[EconomicDemoOutcome]
    intelligence_mode: str = "deterministic"

    @property
    def passed(self) -> bool:
        return all(o.passed for o in self.outcomes)


def load_economic_scenarios(path: Path = DEFAULT_ECONOMIC_SCENARIO_FILE) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return list(data.get("scenarios") or [])


def _action_from_raw(raw: dict[str, Any]) -> RecoveryAction:
    return RecoveryAction(
        action_id=str(raw["id"]),
        label=str(raw.get("label", raw["id"])),
        channel=str(raw.get("channel", "system")),
        is_retry=bool(raw.get("is_retry", False)),
        is_contact=bool(raw.get("is_contact", False)),
        retry_delay_hours=raw.get("retry_delay_hours"),
    )


def _predictive_from_raw(raw: dict[str, Any]) -> PredictiveSignals:
    return PredictiveSignals(
        estimated_recovery_probability=float(raw["estimated_recovery_probability"]),
        retry_success_likelihood=float(raw["retry_success_likelihood"]),
        responsiveness_score=float(raw["responsiveness_score"]),
        source="deterministic",
    )


def run_economic_demos(
    *,
    scenarios: list[dict[str, Any]] | None = None,
    config: EconomicsConfig | None = None,
) -> EconomicDemoReport:
    catalog = scenarios or load_economic_scenarios()
    cfg = config or load_economics_config()
    outcomes: list[EconomicDemoOutcome] = []
    for raw in catalog:
        scenario_type = raw.get("type", "action")
        if scenario_type == "capacity":
            outcomes.append(_run_capacity_scenario(raw, cfg))
        elif scenario_type == "policy":
            outcomes.append(_run_policy_scenario(raw, cfg))
        else:
            outcomes.append(_run_action_scenario(raw, cfg))
    return EconomicDemoReport(outcomes=outcomes)


def _run_action_scenario(raw: dict[str, Any], cfg: EconomicsConfig) -> EconomicDemoOutcome:
    failures: list[str] = []
    actions = [_action_from_raw(a) for a in raw["actions"]]
    predictive = _predictive_from_raw(raw["predictive"])
    decision = select_best_economic_action(
        actions,
        amount_at_risk=float(raw["amount_at_risk"]),
        predictive=predictive,
        config=cfg,
    )
    expected = raw.get("expected_selected")
    selected_id = decision.selected.action_id if decision.selected else None
    if expected and selected_id != expected:
        failures.append(f"expected selected={expected}, got {selected_id}")

    for action_id in raw.get("expect_ineligible") or []:
        match = next((c for c in decision.candidates if c.action_id == action_id), None)
        if match is None or match.eligible:
            failures.append(f"expected {action_id} ineligible")

    return EconomicDemoOutcome(
        scenario_id=str(raw["id"]),
        title=str(raw.get("title", raw["id"])),
        passed=not failures,
        failures=failures,
        detail={
            "selected": selected_id,
            "reason": decision.economic_reason,
            "candidates": [c.to_dict() for c in decision.candidates],
        },
    )


def _run_capacity_scenario(raw: dict[str, Any], cfg: EconomicsConfig) -> EconomicDemoOutcome:
    failures: list[str] = []
    cap_raw = raw.get("capacity") or {}
    limits = CapacityLimits(
        max_voice_calls_per_batch=int(cap_raw.get("max_voice_calls_per_batch", 10)),
        max_human_escalations_per_batch=int(cap_raw.get("max_human_escalations_per_batch", 2)),
        max_incentive_budget=float(cap_raw.get("max_incentive_budget", 5000)),
    )
    pool = CapacityPool.from_limits(limits)
    action = RecoveryAction("human_escalation", "Human escalation", "human", is_contact=True)
    requests: list[AllocationRequest] = []
    for item in raw.get("requests") or []:
        amount = float(item["amount"])
        prob = float(item["probability"])
        cost = float(item["cost"])
        candidate = evaluate_action_economics(
            action,
            amount_at_risk=amount,
            probability=prob,
            intervention_cost=cost,
            minimum_expected_net_value=cfg.minimum_expected_net_value,
        )
        requests.append(AllocationRequest(case_id=str(item["case_id"]), candidate=candidate))

    # Use config with human escalation scarce mapping
    report = allocate_batch(requests, config=cfg, pool=pool)
    selected = {r.case_id for r in report.selected}
    deferred = {r.case_id for r in report.deferred}
    expected_selected = set(raw.get("expected_selected_cases") or [])
    expected_deferred = set(raw.get("expected_deferred_cases") or [])
    if selected != expected_selected:
        failures.append(f"expected selected {expected_selected}, got {selected}")
    if deferred != expected_deferred:
        failures.append(f"expected deferred {expected_deferred}, got {deferred}")

    return EconomicDemoOutcome(
        scenario_id=str(raw["id"]),
        title=str(raw.get("title", raw["id"])),
        passed=not failures,
        failures=failures,
        detail=report.to_dict(),
    )


def _run_policy_scenario(raw: dict[str, Any], cfg: EconomicsConfig) -> EconomicDemoOutcome:
    failures: list[str] = []
    actions = [_action_from_raw(a) for a in raw["actions"]]
    predictive = _predictive_from_raw(raw["predictive"])
    now = datetime(2026, 2, 1, 10, 0, 0)
    case = RecoveryCaseRuntime(
        case_id="case_econ_pol",
        customer_id="cust_econ_pol",
        lane=Lane.SUBSCRIPTION_PAYMENT.value,
        amount=float(raw["amount_at_risk"]),
        currency="INR",
        status="open",
        workflow_state="diagnosed",
        created_at=now,
        recovery_window_end=now + timedelta(days=14),
        source_ref_id="sub_econ",
        failure_reason="repeated_failure",
        recoverability_hint="medium",
        days_overdue=None,
        attempt_count=0,
        estimated_recovery_prob=None,
    )
    customer = CustomerContext(
        customer_id="cust_econ_pol",
        opt_out=bool(raw.get("opt_out", False)),
        prior_contacts_7d=0,
        segment="b2c",
    )
    reasoning = ReasoningInsight(
        summary="policy override demo",
        likely_cause="repeated_failure",
        confidence=0.7,
        key_factors=("demo",),
    )
    proposals = tuple(
        StrategyProposal(action=a, rationale="demo", priority=i + 1, confidence=0.5)
        for i, a in enumerate(actions)
    )
    proposal = DecisionProposal(
        recommended_action=actions[0],
        candidate_actions=tuple(actions),
        reasoning=reasoning,
        predictive=predictive,
        strategy_proposals=proposals,
        explanation="policy vs economics demo",
        source="deterministic",
    )
    evaluated = evaluate_decision_proposal(
        proposal, case, customer, economics_config=cfg, capacity_pool=None
    )
    selected_id = evaluated.selected_action.action_id if evaluated.selected_action else None
    expected = raw.get("expected_selected")
    if expected and selected_id != expected:
        failures.append(f"expected selected={expected}, got {selected_id}")

    blocked = raw.get("expect_policy_blocks")
    if blocked:
        blocked_checks = [c for c in evaluated.policy_checks if c.action == blocked and not c.allowed]
        if not blocked_checks:
            failures.append(f"expected policy to block {blocked}")

    # Economics should still like the expensive action
    econ = select_best_economic_action(
        actions, amount_at_risk=case.amount, predictive=predictive, config=cfg
    )
    if econ.selected and econ.selected.action_id == blocked:
        detail_note = "economics_preferred_blocked_action"
    else:
        detail_note = "economics_selected_" + (econ.selected.action_id if econ.selected else "none")

    return EconomicDemoOutcome(
        scenario_id=str(raw["id"]),
        title=str(raw.get("title", raw["id"])),
        passed=not failures,
        failures=failures,
        detail={
            "selected": selected_id,
            "economics_note": detail_note,
            "policy_checks": [
                {"action": c.action, "allowed": c.allowed, "reason": c.reason}
                for c in evaluated.policy_checks
            ],
        },
    )


def format_economic_demo_report(report: EconomicDemoReport) -> str:
    lines = [
        "=" * 72,
        "Podium Economic Decision Demonstrations (Phase 5)",
        "=" * 72,
    ]
    for outcome in report.outcomes:
        status = "PASS" if outcome.passed else "FAIL"
        lines.extend(
            [
                "",
                f"[{status}] {outcome.scenario_id} — {outcome.title}",
                f"Detail: {outcome.detail}",
            ]
        )
        if outcome.failures:
            lines.append("Failures:")
            lines.extend(f"  - {msg}" for msg in outcome.failures)
    lines.extend(
        [
            "",
            "=" * 72,
            f"Summary: {sum(1 for o in report.outcomes if o.passed)}/{len(report.outcomes)} scenarios passed",
            "=" * 72,
        ]
    )
    return "\n".join(lines)
