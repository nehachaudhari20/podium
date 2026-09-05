"""Receivable recovery demos — overdue invoices and promise-to-pay (Phase 7)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from recovery.audit.trail import load_audit_trail
from recovery.coordination.runner import plan_customer_recovery
from recovery.demos.adaptive import AdaptiveDemoOutcome, AdaptiveDemoReport, AdaptiveDemoScenario
from recovery.ingestion.synthetic.hero_scenario import HERO_CUSTOMER_ID
from recovery.models.enums import Lane
from recovery.pipeline.receivables_runner import format_run_summary, run_receivable_case
from recovery.promises import validate_promise
from recovery.state.reset import reset_case_for_run


@dataclass(frozen=True, slots=True)
class ReceivableDemoScenario:
    id: str
    title: str
    narrative: str
    failure_reason: str | None = None
    case_id: str | None = None
    simulated_payment_amount: float | None = None
    expect_recovered: bool | None = None
    expect_promise_kept: bool = False
    expect_promise_broken: bool = False
    expect_partial: bool = False
    expect_replan: bool = False
    min_replan_count: int = 0
    required_actions: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()


@dataclass
class ReceivableDemoOutcome:
    scenario: ReceivableDemoScenario
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


def _find_receivable_case(conn: sqlite3.Connection, failure_reason: str) -> str:
    row = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'receivable'
          AND failure_reason = ?
          AND case_id != 'case_hero_inv_001'
        ORDER BY case_id
        LIMIT 1
        """,
        (failure_reason,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No receivable case for failure_reason={failure_reason}")
    return row["case_id"]


def _prepare(conn: sqlite3.Connection, case_id: str) -> None:
    reset_case_for_run(conn, case_id)
    row = conn.execute(
        "SELECT customer_id FROM recovery_cases WHERE case_id = ?", (case_id,)
    ).fetchone()
    conn.execute(
        """
        UPDATE customers SET opt_out = 0, prior_contacts_7d = 0
        WHERE customer_id = ?
        """,
        (row["customer_id"],),
    )
    # Ensure recovery window allows a 7-day promise from case created_at.
    created = conn.execute(
        "SELECT created_at FROM recovery_cases WHERE case_id = ?", (case_id,)
    ).fetchone()["created_at"]
    created_dt = datetime.fromisoformat(created)
    if created_dt.tzinfo is None:
        created_dt = created_dt.replace(tzinfo=timezone.utc)
    conn.execute(
        """
        UPDATE recovery_cases
        SET recovery_window_end = ?
        WHERE case_id = ?
        """,
        ((created_dt + timedelta(days=45)).isoformat(), case_id),
    )
    conn.commit()


def run_receivable_demos(conn: sqlite3.Connection) -> AdaptiveDemoReport:
    scenarios = [
        ReceivableDemoScenario(
            id="recv_simple_overdue",
            title="Simple overdue invoice",
            narrative="Mild overdue with high recovery likelihood → low-friction action.",
            failure_reason="invoice_mild_overdue",
            required_actions=("invoice_reminder",),
            forbidden_actions=("escalate_collections",),
        ),
        ReceivableDemoScenario(
            id="recv_ptp_kept",
            title="Promise-to-pay succeeds",
            narrative="Aged overdue → PTP → full payment → recovered.",
            failure_reason="invoice_aged_overdue",
            expect_recovered=True,
            expect_promise_kept=True,
            required_actions=("promise_to_pay_request",),
        ),
        ReceivableDemoScenario(
            id="recv_ptp_broken",
            title="Promise broken then re-plan",
            narrative="PTP created → no payment → broken → stronger follow-up.",
            failure_reason="invoice_aged_overdue",
            simulated_payment_amount=0.0,
            expect_recovered=False,
            expect_promise_broken=True,
            expect_replan=True,
            min_replan_count=1,
        ),
        ReceivableDemoScenario(
            id="recv_partial_payment",
            title="Partial payment leaves remaining exposure",
            narrative="Invoice paid partially against promise; recovery continues.",
            failure_reason="invoice_aged_overdue",
            simulated_payment_amount=20000.0,
            expect_partial=True,
            expect_replan=True,
            min_replan_count=1,
        ),
        ReceivableDemoScenario(
            id="recv_high_value",
            title="High-value receivable economics",
            narrative="Large overdue invoice; economics ranks candidates including human follow-up.",
            case_id="case_hero_inv_001",
            expect_recovered=True,
            required_actions=("promise_to_pay_request",),
        ),
    ]

    outcomes: list[AdaptiveDemoOutcome] = []
    for scenario in scenarios:
        case_id = scenario.case_id or _find_receivable_case(conn, scenario.failure_reason or "")
        _prepare(conn, case_id)
        result = run_receivable_case(
            conn,
            case_id,
            intelligence_mode="deterministic",
            simulated_payment_amount=scenario.simulated_payment_amount,
        )
        events = load_audit_trail(conn, case_id)
        event_types = {e.event_type for e in events}
        actions = [e.action for e in events if e.action]
        failures: list[str] = []

        if scenario.expect_recovered is True and not result.recovered:
            failures.append("expected recovery")
        if scenario.expect_recovered is False and result.recovered:
            failures.append("did not expect recovery")
        if scenario.expect_promise_kept and "PROMISE_KEPT" not in event_types:
            failures.append("expected PROMISE_KEPT")
        if scenario.expect_promise_broken and "PROMISE_BROKEN" not in event_types:
            failures.append("expected PROMISE_BROKEN")
        if scenario.expect_partial and "PARTIAL_PAYMENT_RECEIVED" not in event_types:
            failures.append("expected PARTIAL_PAYMENT_RECEIVED")
        if scenario.expect_replan and result.replan_count < scenario.min_replan_count:
            failures.append(f"expected replan>={scenario.min_replan_count}, got {result.replan_count}")
        for action in scenario.required_actions:
            if action not in actions and (
                result.selected_action is None or result.selected_action.action_id != action
            ):
                if action not in [a.action_id for a in result.candidate_actions]:
                    failures.append(f"missing required action {action}")
        for action in scenario.forbidden_actions:
            if result.selected_action and result.selected_action.action_id == action:
                failures.append(f"forbidden action selected: {action}")

        outcomes.append(
            AdaptiveDemoOutcome(
                scenario=AdaptiveDemoScenario(
                    id=scenario.id,
                    title=scenario.title,
                    narrative=scenario.narrative,
                    failure_reason=scenario.failure_reason,
                    case_id=scenario.case_id,
                ),
                case_id=case_id,
                result=result,
                passed=not failures,
                failures=failures,
                action_sequence=actions,
            )
        )

    # Invalid promise unit scenario
    now = datetime(2026, 2, 15, tzinfo=timezone.utc)
    invalid = validate_promise(
        promised_amount=100000,
        promise_date=now + timedelta(days=3),
        remaining_balance=38000,
        recovery_window_end=now + timedelta(days=30),
        now=now,
    )
    outcomes.append(
        AdaptiveDemoOutcome(
            scenario=AdaptiveDemoScenario(
                id="recv_invalid_promise",
                title="Invalid promise rejected",
                narrative="Promised amount exceeds remaining balance.",
            ),
            case_id="n/a",
            result=outcomes[0].result,
            passed=not invalid.allowed and invalid.reason == "promised_amount_exceeds_remaining_balance",
            failures=[]
            if (not invalid.allowed and invalid.reason == "promised_amount_exceeds_remaining_balance")
            else [f"expected rejection, got {invalid}"],
            action_sequence=[],
        )
    )

    # Coordination reuse: receivable in customer view with contact collision
    from recovery.demos.coordination import prepare_customer_cases

    prepare_customer_cases(conn, HERO_CUSTOMER_ID, clear_contacts=False)
    conn.execute(
        "UPDATE customers SET prior_contacts_7d = 2 WHERE customer_id = ?",
        (HERO_CUSTOMER_ID,),
    )
    conn.commit()
    view, _, plan = plan_customer_recovery(conn, HERO_CUSTOMER_ID, coordinated=True)
    recv_present = any(c.lane == Lane.RECEIVABLE.value for c in view.active_cases)
    coord_ok = recv_present and (
        len(plan.deferred_actions) > 0
        or any("contact" in r or "fatigue" in r for r in plan.coordination_reasons)
    )
    outcomes.append(
        AdaptiveDemoOutcome(
            scenario=AdaptiveDemoScenario(
                id="recv_coordination",
                title="Receivable participates in coordination",
                narrative="Receivable in customer view; recent contacts defer/consolidate outreach.",
            ),
            case_id="case_hero_inv_001",
            result=outcomes[0].result,
            passed=coord_ok,
            failures=[] if coord_ok else ["receivable missing from coordinated plan behavior"],
            action_sequence=[],
        )
    )

    return AdaptiveDemoReport(outcomes=outcomes, intelligence_mode="deterministic")


def run_hero_receivable_demo(conn: sqlite3.Connection) -> str:
    case_id = "case_hero_inv_001"
    _prepare(conn, case_id)
    # Reset attempt_count for clean hero demo but keep amount.
    conn.execute(
        "UPDATE recovery_cases SET attempt_count = 0, days_overdue = 38 WHERE case_id = ?",
        (case_id,),
    )
    conn.commit()
    result = run_receivable_case(conn, case_id, intelligence_mode="deterministic")
    events = load_audit_trail(conn, case_id)
    lines = [
        "=" * 72,
        "RECEIVABLE RECOVERY — Hero (NovaTech / case_hero_inv_001)",
        "=" * 72,
        f"Customer: NovaTech Solutions ({HERO_CUSTOMER_ID})",
        f"Invoice:  inv_hero_001",
        f"Amount:   INR {result.amount:,.2f}",
        f"Diagnosis:{result.diagnosis.likely_cause} — {result.diagnosis.rationale}",
        "",
        "CANDIDATE ACTIONS",
        *[f"  - {a.action_id}" for a in result.candidate_actions],
        "",
        "ECONOMICS",
        f"  ERV={result.expected_recovery_value}  ENV={result.expected_net_value}  cost={result.intervention_cost}",
        "",
        f"SELECTED: {result.selected_action.action_id if result.selected_action else None}",
        f"TERMINAL: {result.terminal_state}  recovered={result.recovered}  amount={result.amount_recovered:,.2f}",
        "",
        "AUDIT HIGHLIGHTS",
    ]
    for event in events:
        if event.event_type in {
            "PROMISE_CREATED",
            "PROMISE_DUE",
            "PROMISE_KEPT",
            "PROMISE_BROKEN",
            "PARTIAL_PAYMENT_RECEIVED",
            "RECOVERED",
            "AGENT_REPLAN",
            "ECONOMIC_ACTION_SELECTED",
        }:
            lines.append(f"  [{event.event_type}] {event.reason}")
    lines.append("=" * 72)
    lines.append(format_run_summary(result))
    return "\n".join(lines)


def format_receivable_demo_report(report: AdaptiveDemoReport) -> str:
    lines = [
        "=" * 72,
        "Podium Phase 7 Receivable Recovery Demos",
        "=" * 72,
    ]
    for outcome in report.outcomes:
        status = "PASS" if outcome.passed else "FAIL"
        lines.append(f"[{status}] {outcome.scenario.id}: {outcome.scenario.title}")
        if outcome.failures:
            for f in outcome.failures:
                lines.append(f"    - {f}")
    passed = sum(1 for o in report.outcomes if o.passed)
    lines.append(f"\n{passed}/{len(report.outcomes)} scenarios passed")
    lines.append("=" * 72)
    return "\n".join(lines)
