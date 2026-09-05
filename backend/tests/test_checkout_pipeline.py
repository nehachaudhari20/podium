"""Phase 4C — checkout recovery pipeline integration tests."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from recovery.audit.trail import load_audit_trail
from recovery.db import connect
from recovery.execution.simulator import simulate_execution
from recovery.ingestion.customer_loader import CustomerContext
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
from recovery.models.case import RecoveryCaseRuntime
from recovery.models.enums import Lane, WorkflowState
from recovery.models.recovery_types import DiagnosisResult, RecoveryAction
from recovery.pipeline.checkout_runner import run_checkout_case
from recovery.pipeline.subscription_runner import run_subscription_case
from recovery.policy.gate import check_policy
from recovery.state.context import CaseRunContext
from recovery.state.machine import apply_transition
from recovery.state.reset import reset_case_for_run


@pytest.fixture
def checkout_pipeline_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "checkout_pipeline.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def _find_checkout_case(conn: sqlite3.Connection, failure_reason: str) -> str:
    row = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'checkout_abandonment' AND failure_reason = ?
        LIMIT 1
        """,
        (failure_reason,),
    ).fetchone()
    assert row is not None, f"No checkout case with failure_reason={failure_reason}"
    return row["case_id"]


def _prepare_test_case(conn: sqlite3.Connection, case_id: str) -> None:
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
    conn.commit()


def test_payment_page_drop_recovers(checkout_pipeline_db):
    conn = checkout_pipeline_db
    case_id = _find_checkout_case(conn, "checkout_payment_page_drop")
    _prepare_test_case(conn, case_id)
    result = run_checkout_case(conn, case_id, intelligence_mode="deterministic")
    assert result.lane == Lane.CHECKOUT_ABANDONMENT.value
    assert result.recovered is True
    assert result.terminal_state == WorkflowState.RECOVERED.value
    assert result.amount_recovered > 0
    assert "payment_link" in [a.action_id for a in result.candidate_actions] or result.selected_action


def test_cart_abandon_reminder_then_replan(checkout_pipeline_db):
    conn = checkout_pipeline_db
    case_id = _find_checkout_case(conn, "checkout_cart_abandon")
    _prepare_test_case(conn, case_id)
    result = run_checkout_case(conn, case_id, intelligence_mode="deterministic")
    assert result.agent_steps >= 2
    assert result.replan_count >= 1
    events = load_audit_trail(conn, case_id)
    types = {e.event_type for e in events}
    assert "AGENT_OBSERVE" in types
    assert "AGENT_REPLAN" in types
    assert result.recovered is True


def test_checkout_opt_out_stops_without_contact(checkout_pipeline_db):
    conn = checkout_pipeline_db
    case_id = _find_checkout_case(conn, "checkout_cart_abandon")
    _prepare_test_case(conn, case_id)
    row = conn.execute(
        "SELECT customer_id FROM recovery_cases WHERE case_id = ?", (case_id,)
    ).fetchone()
    conn.execute("UPDATE customers SET opt_out = 1 WHERE customer_id = ?", (row["customer_id"],))
    conn.commit()
    result = run_checkout_case(conn, case_id, intelligence_mode="deterministic")
    assert result.recovered is False
    assert result.terminal_state == WorkflowState.EXHAUSTED.value
    assert result.agent_steps == 0


def test_wrong_lane_rejected(checkout_pipeline_db):
    conn = checkout_pipeline_db
    sub = conn.execute(
        "SELECT case_id FROM recovery_cases WHERE lane = 'subscription_payment' LIMIT 1"
    ).fetchone()
    chk = conn.execute(
        "SELECT case_id FROM recovery_cases WHERE lane = 'checkout_abandonment' LIMIT 1"
    ).fetchone()
    assert sub and chk
    with pytest.raises(ValueError, match="checkout_abandonment only"):
        run_checkout_case(conn, sub["case_id"], intelligence_mode="deterministic")
    with pytest.raises(ValueError, match="subscription_payment only"):
        run_subscription_case(conn, chk["case_id"], intelligence_mode="deterministic")


def test_subscription_regression_still_recovers(checkout_pipeline_db):
    conn = checkout_pipeline_db
    row = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'subscription_payment' AND failure_reason = 'network_timeout'
        LIMIT 1
        """
    ).fetchone()
    assert row is not None
    _prepare_test_case(conn, row["case_id"])
    result = run_subscription_case(conn, row["case_id"], intelligence_mode="deterministic")
    assert result.recovered is True


def test_checkout_audit_trail(checkout_pipeline_db):
    conn = checkout_pipeline_db
    case_id = _find_checkout_case(conn, "checkout_payment_page_drop")
    _prepare_test_case(conn, case_id)
    result = run_checkout_case(conn, case_id, intelligence_mode="deterministic")
    events = load_audit_trail(conn, case_id)
    types = {e.event_type for e in events}
    assert {"DIAGNOSED", "DECISION_PROPOSED", "POLICY_CHECK", "ACTION_EXECUTED", "STATE_TRANSITION"} <= types
    assert result.audit_event_count >= 5


def test_simulator_checkout_reminder_ignored():
    now = datetime(2026, 2, 1, 10, 0, 0)
    case = RecoveryCaseRuntime(
        case_id="case_chk_sim",
        customer_id="cust_chk_sim",
        lane=Lane.CHECKOUT_ABANDONMENT.value,
        amount=4999.0,
        currency="INR",
        status="open",
        workflow_state="diagnosed",
        created_at=now,
        recovery_window_end=now + timedelta(days=7),
        source_ref_id="chk_sim",
        failure_reason="checkout_high_intent_drop",
        recoverability_hint="high",
        days_overdue=None,
        attempt_count=0,
        estimated_recovery_prob=None,
    )
    ctx = CaseRunContext(case=case)
    diagnosis = DiagnosisResult(likely_cause="distraction_or_delay", confidence=0.8, rationale="test")
    reminder = RecoveryAction("checkout_reminder", "Remind", "email", is_contact=True)
    result = simulate_execution(ctx, reminder, diagnosis)
    assert result.event == "customer_ignored"
    assert ctx.attempt_count == 1


def test_checkout_completed_transition():
    now = datetime(2026, 2, 1, 10, 0, 0)
    case = RecoveryCaseRuntime(
        case_id="case_chk_fsm",
        customer_id="cust_chk_fsm",
        lane=Lane.CHECKOUT_ABANDONMENT.value,
        amount=1000.0,
        currency="INR",
        status="open",
        workflow_state="contacted",
        created_at=now,
        recovery_window_end=now + timedelta(days=7),
        source_ref_id="chk_fsm",
        failure_reason="checkout_payment_page_drop",
        recoverability_hint="high",
        days_overdue=None,
        attempt_count=1,
        estimated_recovery_prob=None,
    )
    ctx = CaseRunContext(case=case)
    apply_transition(ctx, "checkout_completed")
    assert ctx.workflow_state == WorkflowState.RECOVERED.value
    assert ctx.terminal is True


def test_limited_incentive_respects_discount_ceiling():
    now = datetime(2026, 2, 1, 10, 0, 0)
    case = RecoveryCaseRuntime(
        case_id="case_chk_pol",
        customer_id="cust_chk_pol",
        lane=Lane.CHECKOUT_ABANDONMENT.value,
        amount=8000.0,
        currency="INR",
        status="open",
        workflow_state="diagnosed",
        created_at=now,
        recovery_window_end=now + timedelta(days=7),
        source_ref_id="chk_pol",
        failure_reason="checkout_cart_abandon",
        recoverability_hint="medium",
        days_overdue=None,
        attempt_count=0,
        estimated_recovery_prob=None,
    )
    customer = CustomerContext(
        customer_id="cust_chk_pol",
        opt_out=False,
        prior_contacts_7d=0,
        segment="b2c",
    )
    action = RecoveryAction("limited_incentive", "Offer", "system", is_contact=False)
    result = check_policy(case, action, customer)
    assert result.allowed is True


def test_runtime_checkout_modules_forbid_ground_truth():
    modules = [
        Path("src/recovery/pipeline/checkout_runner.py"),
        Path("src/recovery/execution/simulator.py"),
        Path("src/recovery/execution/outcomes.py"),
        Path("src/recovery/pipeline/agentic_loop.py"),
    ]
    forbidden = ("case_ground_truth", "p_pay_anyway")
    root = Path(__file__).resolve().parents[1]
    for rel in modules:
        source = (root / rel).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{rel} must not reference {token}"
