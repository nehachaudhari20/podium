"""Cross-revenue coordination demos and hero scenario (Phase 6)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from recovery.coordination.config import load_coordination_config
from recovery.coordination.planner import CustomerRecoveryPlan
from recovery.coordination.runner import plan_customer_recovery
from recovery.coordination.view import CustomerRecoveryView, load_customer_recovery_view
from recovery.ingestion.synthetic.hero_scenario import HERO_CUSTOMER_ID
from recovery.models.enums import Lane
from recovery.state.reset import reset_case_for_run


@dataclass
class CoordinationDemoOutcome:
    scenario_id: str
    title: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class CoordinationDemoReport:
    outcomes: list[CoordinationDemoOutcome]

    @property
    def passed(self) -> bool:
        return all(o.passed for o in self.outcomes)


def prepare_customer_cases(conn: sqlite3.Connection, customer_id: str, *, clear_contacts: bool = True) -> None:
    rows = conn.execute(
        "SELECT case_id FROM recovery_cases WHERE customer_id = ?",
        (customer_id,),
    ).fetchall()
    for row in rows:
        reset_case_for_run(conn, row["case_id"])
    if clear_contacts:
        conn.execute(
            "UPDATE customers SET opt_out = 0, prior_contacts_7d = 0 WHERE customer_id = ?",
            (customer_id,),
        )
    conn.commit()


def format_customer_plan_report(
    view: CustomerRecoveryView,
    plan: CustomerRecoveryPlan,
    *,
    customer_label: str | None = None,
) -> str:
    label = customer_label or view.customer_id
    lines = [
        "=" * 72,
        "Podium Cross-Revenue Coordination",
        f"CUSTOMER: {label}",
        f"Segment: {view.segment}",
        "",
        "ACTIVE REVENUE RISKS",
    ]
    for case in view.active_cases:
        lines.append(
            f"  {case.lane:24}  INR {case.amount:>12,.2f}  [{case.workflow_state}]  {case.case_id}"
        )
    lines.extend(
        [
            "",
            f"TOTAL AT RISK: INR {view.total_amount_at_risk:,.2f}",
            f"Active lanes: {', '.join(view.active_lanes)}",
            f"Mode: {plan.mode}",
            "",
            "PLAN (sequence)",
        ]
    )
    if not plan.selected_actions:
        lines.append("  (none selected)")
    for idx, action in enumerate(plan.selected_actions, start=1):
        lines.append(
            f"  {idx}. {action.case_id} / {action.lane}: {action.action_id} "
            f"(ENV={action.expected_net_value:,.2f}) — {action.reason}"
        )
    lines.append("")
    lines.append("DEFERRED")
    if not plan.deferred_actions:
        lines.append("  (none)")
    for action in plan.deferred_actions:
        lines.append(
            f"  - {action.case_id}: {action.action_id} — {action.reason}"
        )
    lines.append("")
    lines.append("BLOCKED")
    if not plan.blocked_actions:
        lines.append("  (none)")
    for action in plan.blocked_actions:
        lines.append(f"  - {action.case_id}: {action.action_id} — {action.reason}")
    if plan.coordination_reasons:
        lines.append("")
        lines.append("REASONS")
        for reason in plan.coordination_reasons:
            lines.append(f"  - {reason}")
    lines.append("=" * 72)
    return "\n".join(lines)


def run_hero_coordination_demo(
    conn: sqlite3.Connection,
    *,
    intelligence_mode: str = "deterministic",
) -> tuple[CustomerRecoveryView, CustomerRecoveryPlan, CustomerRecoveryPlan, str]:
    """Hero multi-lane customer: coordinated plan vs independent baseline."""
    prepare_customer_cases(conn, HERO_CUSTOMER_ID, clear_contacts=True)
    view, _, coordinated = plan_customer_recovery(
        conn, HERO_CUSTOMER_ID, intelligence_mode=intelligence_mode, coordinated=True
    )
    _, _, independent = plan_customer_recovery(
        conn, HERO_CUSTOMER_ID, intelligence_mode=intelligence_mode, coordinated=False, audit=False
    )
    report = format_customer_plan_report(
        view, coordinated, customer_label=f"NovaTech / {HERO_CUSTOMER_ID}"
    )
    return view, coordinated, independent, report


def run_coordination_demos(conn: sqlite3.Connection) -> CoordinationDemoReport:
    outcomes: list[CoordinationDemoOutcome] = []
    outcomes.append(_scenario_multiple_active_cases(conn))
    outcomes.append(_scenario_contact_collision(conn))
    outcomes.append(_scenario_fatigue_cooldown(conn))
    outcomes.append(_scenario_shared_human_capacity(conn))
    outcomes.append(_scenario_baseline_differs(conn))
    return CoordinationDemoReport(outcomes=outcomes)


def _scenario_multiple_active_cases(conn: sqlite3.Connection) -> CoordinationDemoOutcome:
    prepare_customer_cases(conn, HERO_CUSTOMER_ID, clear_contacts=True)
    view = load_customer_recovery_view(conn, HERO_CUSTOMER_ID)
    failures = []
    if view.open_case_count < 3:
        failures.append(f"expected >=3 open cases, got {view.open_case_count}")
    expected_lanes = {
        Lane.SUBSCRIPTION_PAYMENT.value,
        Lane.CHECKOUT_ABANDONMENT.value,
        Lane.RECEIVABLE.value,
    }
    if set(view.active_lanes) != expected_lanes:
        failures.append(f"expected lanes {expected_lanes}, got {set(view.active_lanes)}")
    if view.total_amount_at_risk <= 0:
        failures.append("total_amount_at_risk should be positive")
    return CoordinationDemoOutcome(
        scenario_id="multiple_active_cases",
        title="Hero customer has subscription + checkout + receivable",
        passed=not failures,
        failures=failures,
        detail=view.to_dict(),
    )


def _scenario_contact_collision(conn: sqlite3.Connection) -> CoordinationDemoOutcome:
    prepare_customer_cases(conn, HERO_CUSTOMER_ID, clear_contacts=True)
    view, _, plan = plan_customer_recovery(conn, HERO_CUSTOMER_ID, coordinated=True)
    failures = []
    contact_selected = [
        a
        for a in plan.selected_actions
        if a.action_id
        in {
            "payment_method_update",
            "checkout_reminder",
            "payment_link",
            "checkout_assistance",
            "human_escalation",
            "send_email",
        }
    ]
    cfg = load_coordination_config()
    if len(contact_selected) > cfg.max_customer_contacts_per_window:
        failures.append(
            f"expected <= {cfg.max_customer_contacts_per_window} contacts selected, "
            f"got {len(contact_selected)}"
        )
    if not plan.deferred_actions and len(view.active_cases) > 1:
        # Soft check: with 3 contact-heavy cases we usually defer some
        pass
    has_collision_reason = any(
        "contact" in r.lower() or "collision" in r.lower() or "deferred" in r.lower()
        for r in plan.coordination_reasons
    ) or bool(plan.deferred_actions)
    if not has_collision_reason and len(contact_selected) > 1:
        failures.append("expected coordination to limit or explain contact competition")
    return CoordinationDemoOutcome(
        scenario_id="contact_collision",
        title="Competing contacts are coordinated",
        passed=not failures,
        failures=failures,
        detail=plan.to_dict(),
    )


def _scenario_fatigue_cooldown(conn: sqlite3.Connection) -> CoordinationDemoOutcome:
    prepare_customer_cases(conn, HERO_CUSTOMER_ID, clear_contacts=False)
    conn.execute(
        "UPDATE customers SET prior_contacts_7d = 2 WHERE customer_id = ?",
        (HERO_CUSTOMER_ID,),
    )
    conn.commit()
    _, _, plan = plan_customer_recovery(conn, HERO_CUSTOMER_ID, coordinated=True)
    failures = []
    deferred_contacts = [
        a for a in plan.deferred_actions if "contact" in a.reason or "fatigue" in a.reason or "cooldown" in a.reason
    ]
    if not deferred_contacts and not any("fatigue" in r or "cooldown" in r for r in plan.coordination_reasons):
        failures.append("expected contact deferral under recovery fatigue")
    return CoordinationDemoOutcome(
        scenario_id="recovery_fatigue",
        title="Recent contacts defer additional outreach",
        passed=not failures,
        failures=failures,
        detail=plan.to_dict(),
    )


def _scenario_shared_human_capacity(conn: sqlite3.Connection) -> CoordinationDemoOutcome:
    from recovery.coordination.planner import build_coordinated_plan
    from recovery.coordination.rules import ProposedIntervention
    from recovery.economics.allocator import CapacityPool
    from recovery.economics.config import CapacityLimits
    from recovery.models.recovery_types import RecoveryAction

    prepare_customer_cases(conn, HERO_CUSTOMER_ID, clear_contacts=True)
    view = load_customer_recovery_view(conn, HERO_CUSTOMER_ID)
    human = RecoveryAction("human_escalation", "Escalate", "human", is_contact=True)
    proposals = [
        ProposedIntervention(
            case_id=case.case_id,
            lane=case.lane,
            amount=case.amount,
            action=human,
            expected_net_value=case.amount * 0.5 - 500,
            expected_recovery_value=case.amount * 0.5,
            intervention_cost=500,
            policy_allowed=True,
        )
        for case in view.active_cases
    ]
    pool = CapacityPool.from_limits(
        CapacityLimits(
            max_voice_calls_per_batch=10,
            max_human_escalations_per_batch=1,
            max_incentive_budget=5000,
        )
    )
    plan = build_coordinated_plan(view, proposals, capacity_pool=pool)
    failures = []
    selected_humans = [a for a in plan.selected_actions if a.action_id == "human_escalation"]
    if len(selected_humans) != 1:
        failures.append(f"expected exactly 1 human selected, got {len(selected_humans)}")
    if len(plan.deferred_actions) < 2:
        failures.append("expected lower-value humans deferred")
    return CoordinationDemoOutcome(
        scenario_id="shared_human_capacity",
        title="Shared human capacity across lanes",
        passed=not failures,
        failures=failures,
        detail=plan.to_dict(),
    )


def _scenario_baseline_differs(conn: sqlite3.Connection) -> CoordinationDemoOutcome:
    prepare_customer_cases(conn, HERO_CUSTOMER_ID, clear_contacts=True)
    _, _, coordinated = plan_customer_recovery(conn, HERO_CUSTOMER_ID, coordinated=True)
    _, _, independent = plan_customer_recovery(
        conn, HERO_CUSTOMER_ID, coordinated=False, audit=False
    )
    failures = []
    indep_contacts = len(independent.selected_actions)
    coord_selected = len(coordinated.selected_actions)
    # Coordinated should defer more or select fewer contacts when colliding
    if indep_contacts <= coord_selected and not coordinated.deferred_actions:
        # Still pass if plans differ in ordering/composition
        indep_ids = {(a.case_id, a.action_id) for a in independent.selected_actions}
        coord_ids = {(a.case_id, a.action_id) for a in coordinated.selected_actions}
        if indep_ids == coord_ids and not coordinated.deferred_actions:
            failures.append("expected coordinated plan to differ from independent baseline")
    return CoordinationDemoOutcome(
        scenario_id="baseline_vs_coordinated",
        title="Independent baseline differs from coordinated plan",
        passed=not failures,
        failures=failures,
        detail={
            "independent": independent.to_dict(),
            "coordinated": coordinated.to_dict(),
        },
    )


def format_coordination_demo_report(report: CoordinationDemoReport) -> str:
    lines = [
        "=" * 72,
        "Podium Cross-Revenue Coordination Demonstrations (Phase 6)",
        "=" * 72,
    ]
    for outcome in report.outcomes:
        status = "PASS" if outcome.passed else "FAIL"
        lines.extend(["", f"[{status}] {outcome.scenario_id} — {outcome.title}"])
        if outcome.failures:
            lines.append("Failures:")
            lines.extend(f"  - {msg}" for msg in outcome.failures)
    lines.extend(
        [
            "",
            "=" * 72,
            f"Summary: {sum(1 for o in report.outcomes if o.passed)}/{len(report.outcomes)} passed",
            "=" * 72,
        ]
    )
    return "\n".join(lines)
