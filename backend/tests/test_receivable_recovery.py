"""Phase 7 — receivable recovery and promise-to-pay tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from recovery.audit.trail import load_audit_trail
from recovery.coordination.runner import plan_customer_recovery
from recovery.coordination.view import load_customer_recovery_view
from recovery.db import connect
from recovery.demos.coordination import prepare_customer_cases
from recovery.demos.receivable import run_hero_receivable_demo, run_receivable_demos
from recovery.evaluation.phase7_runner import run_phase7_evaluation
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
from recovery.ingestion.synthetic.hero_scenario import HERO_CUSTOMER_ID
from recovery.intelligence.context_builder import build_recovery_context
from recovery.intelligence.diagnosis import diagnose
from recovery.intelligence.strategy import generate_actions
from recovery.models.enums import Lane, WorkflowState
from recovery.pipeline.receivables_runner import run_receivable_case
from recovery.promises import observe_promise_payment, validate_promise
from recovery.state.context import CaseRunContext
from recovery.state.machine import apply_transition, can_transition
from recovery.state.reset import reset_case_for_run
from recovery.ingestion.runtime_loader import load_case_by_id


@pytest.fixture
def receivable_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "receivable.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def _find_recv(conn, failure_reason: str) -> str:
    row = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'receivable' AND failure_reason = ?
          AND case_id != 'case_hero_inv_001'
        LIMIT 1
        """,
        (failure_reason,),
    ).fetchone()
    assert row is not None
    return row["case_id"]


def _prepare(conn, case_id: str) -> None:
    reset_case_for_run(conn, case_id)
    row = conn.execute(
        "SELECT customer_id, created_at FROM recovery_cases WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    created = datetime.fromisoformat(row["created_at"])
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    conn.execute(
        "UPDATE customers SET opt_out = 0, prior_contacts_7d = 0 WHERE customer_id = ?",
        (row["customer_id"],),
    )
    conn.execute(
        "UPDATE recovery_cases SET recovery_window_end = ?, attempt_count = 0 WHERE case_id = ?",
        ((created + timedelta(days=45)).isoformat(), case_id),
    )
    conn.commit()


def test_validate_promise_rejects_over_balance():
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    result = validate_promise(
        promised_amount=50000,
        promise_date=now + timedelta(days=5),
        remaining_balance=38000,
        recovery_window_end=now + timedelta(days=30),
        now=now,
    )
    assert result.allowed is False
    assert result.reason == "promised_amount_exceeds_remaining_balance"


def test_validate_promise_rejects_outside_window():
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    result = validate_promise(
        promised_amount=1000,
        promise_date=now + timedelta(days=40),
        remaining_balance=1000,
        recovery_window_end=now + timedelta(days=14),
        now=now,
    )
    assert result.allowed is False
    assert result.reason == "promised_date_outside_recovery_window"


def test_observe_promise_partial_and_kept():
    kept = observe_promise_payment(promised_amount=38000, remaining_balance=38000, paid_amount=38000)
    assert kept.outcome == "kept"
    partial = observe_promise_payment(promised_amount=38000, remaining_balance=38000, paid_amount=20000)
    assert partial.outcome == "partial"
    assert partial.remaining_balance == 18000
    missed = observe_promise_payment(promised_amount=38000, remaining_balance=38000, paid_amount=0)
    assert missed.outcome == "missed"


def test_promise_state_machine_transitions():
    from recovery.models.case import RecoveryCaseRuntime

    runtime = RecoveryCaseRuntime(
        case_id="c1",
        customer_id="cust",
        lane=Lane.RECEIVABLE.value,
        amount=1000,
        currency="INR",
        status="open",
        workflow_state=WorkflowState.DETECTED.value,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        recovery_window_end=datetime(2026, 3, 1, tzinfo=timezone.utc),
        source_ref_id="inv1",
        failure_reason="invoice_mild_overdue",
        recoverability_hint="high",
        days_overdue=5,
        attempt_count=0,
        estimated_recovery_prob=None,
        is_hero=False,
    )
    ctx = CaseRunContext(case=runtime)
    apply_transition(ctx, "case_diagnosed")
    apply_transition(ctx, "contact_sent")
    apply_transition(ctx, "promise_made")
    assert ctx.workflow_state == WorkflowState.PROMISED.value
    apply_transition(ctx, "promise_kept")
    assert ctx.workflow_state == WorkflowState.RECOVERED.value
    assert ctx.terminal is True

    ctx2 = CaseRunContext(case=runtime)
    apply_transition(ctx2, "case_diagnosed")
    apply_transition(ctx2, "contact_sent")
    apply_transition(ctx2, "promise_made")
    apply_transition(ctx2, "promise_broken")
    assert ctx2.workflow_state == WorkflowState.WAITING.value
    assert can_transition(ctx2, "contact_sent")


def test_receivable_context_and_diagnosis(receivable_db):
    conn = receivable_db
    case_id = _find_recv(conn, "invoice_mild_overdue")
    _prepare(conn, case_id)
    context = build_recovery_context(conn, case_id)
    assert context.invoice is not None
    assert context.invoice.days_overdue >= 0
    assert "p_pay_anyway" not in context.to_dict()
    case = load_case_by_id(conn, case_id)
    diagnosis = diagnose(case, context)
    assert diagnosis.likely_cause in {
        "customer_oversight",
        "temporary_cash_constraint",
        "payment_processing_delay",
        "high_value_account",
        "unknown_receivable_risk",
    }
    actions = generate_actions(case, diagnosis, context)
    assert actions
    assert any(a.action_id == "invoice_reminder" for a in actions) or any(
        a.action_id == "promise_to_pay_request" for a in actions
    )


def test_ptp_kept_pipeline(receivable_db):
    conn = receivable_db
    case_id = _find_recv(conn, "invoice_aged_overdue")
    _prepare(conn, case_id)
    result = run_receivable_case(conn, case_id, intelligence_mode="deterministic")
    events = {e.event_type for e in load_audit_trail(conn, case_id)}
    assert "PROMISE_CREATED" in events or result.recovered
    if "PROMISE_CREATED" in events:
        assert "PROMISE_KEPT" in events or "PROMISE_BROKEN" in events
    assert "p_pay_anyway" not in str(events)


def test_ptp_broken_replans(receivable_db):
    conn = receivable_db
    case_id = _find_recv(conn, "invoice_aged_overdue")
    _prepare(conn, case_id)
    result = run_receivable_case(
        conn, case_id, intelligence_mode="deterministic", simulated_payment_amount=0.0
    )
    events = {e.event_type for e in load_audit_trail(conn, case_id)}
    assert "PROMISE_BROKEN" in events
    assert result.replan_count >= 1
    assert result.recovered is False or result.terminal_state != WorkflowState.RECOVERED.value


def test_partial_payment_remaining(receivable_db):
    conn = receivable_db
    case_id = _find_recv(conn, "invoice_aged_overdue")
    _prepare(conn, case_id)
    row = conn.execute(
        "SELECT amount FROM recovery_cases WHERE case_id = ?", (case_id,)
    ).fetchone()
    amount = float(row["amount"])
    partial = min(20000.0, amount * 0.5)
    result = run_receivable_case(
        conn, case_id, intelligence_mode="deterministic", simulated_payment_amount=partial
    )
    events = {e.event_type for e in load_audit_trail(conn, case_id)}
    assert "PARTIAL_PAYMENT_RECEIVED" in events
    assert result.replan_count >= 1


def test_receivable_in_customer_view(receivable_db):
    conn = receivable_db
    prepare_customer_cases(conn, HERO_CUSTOMER_ID, clear_contacts=True)
    view = load_customer_recovery_view(conn, HERO_CUSTOMER_ID)
    assert Lane.RECEIVABLE.value in view.active_lanes
    assert any(c.case_id == "case_hero_inv_001" for c in view.active_cases)


def test_coordination_defers_with_recent_contacts(receivable_db):
    conn = receivable_db
    prepare_customer_cases(conn, HERO_CUSTOMER_ID, clear_contacts=False)
    conn.execute(
        "UPDATE customers SET prior_contacts_7d = 2 WHERE customer_id = ?",
        (HERO_CUSTOMER_ID,),
    )
    conn.commit()
    view, _, plan = plan_customer_recovery(conn, HERO_CUSTOMER_ID, coordinated=True)
    assert Lane.RECEIVABLE.value in view.active_lanes
    assert plan.deferred_actions or plan.coordination_reasons


def test_phase7_demos_and_evaluation(receivable_db):
    conn = receivable_db
    report = run_receivable_demos(conn)
    assert report.outcomes
    assert sum(1 for o in report.outcomes if o.passed) >= 5
    summary = run_phase7_evaluation(conn, limit=10)
    assert summary.receivables_cases_processed >= 1
    assert summary.detail.get("p_pay_anyway_isolated") is True
    hero = run_hero_receivable_demo(conn)
    assert "RECEIVABLE RECOVERY" in hero
