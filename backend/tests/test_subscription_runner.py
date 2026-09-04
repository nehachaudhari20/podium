"""Phase 2 integration tests — subscription recovery pipeline."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from recovery.audit.trail import load_audit_trail
from recovery.db import connect
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
from recovery.models.enums import WorkflowState
from recovery.pipeline.subscription_runner import run_subscription_case
from recovery.state.reset import reset_case_for_run


@pytest.fixture
def phase2_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "phase2.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield db_path, conn
    conn.close()


def _find_subscription_case(conn: sqlite3.Connection, failure_reason: str) -> str:
    row = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'subscription_payment' AND failure_reason = ?
        LIMIT 1
        """,
        (failure_reason,),
    ).fetchone()
    assert row is not None, f"No case with failure_reason={failure_reason}"
    return row["case_id"]


def _prepare_test_case(conn: sqlite3.Connection, case_id: str) -> None:
    """Test fixture: reset case and isolate customer contact state for deterministic runs."""
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


def test_success_path_transient_failure(phase2_db):
    _, conn = phase2_db
    case_id = _find_subscription_case(conn, "network_timeout")
    _prepare_test_case(conn, case_id)
    result = run_subscription_case(conn, case_id)
    assert result.recovered is True
    assert result.terminal_state == WorkflowState.RECOVERED.value
    assert result.state_history[:4] == ["detected", "diagnosed", "retry_scheduled", "waiting"]
    assert "contacted" not in result.state_history
    assert result.amount_recovered > 0


def test_transient_failure_advances_simulated_time(phase2_db):
    _, conn = phase2_db
    case_id = _find_subscription_case(conn, "transient_technical")
    _prepare_test_case(conn, case_id)
    run_subscription_case(conn, case_id)
    events = load_audit_trail(conn, case_id)
    event_types = {e.event_type for e in events}
    assert "RETRY_SCHEDULED" in event_types


def test_exhaustion_path_repeated_failure(phase2_db):
    _, conn = phase2_db
    case_id = _find_subscription_case(conn, "repeated_failure")
    _prepare_test_case(conn, case_id)
    result = run_subscription_case(conn, case_id)
    assert result.recovered is False
    assert result.terminal_state in (WorkflowState.EXHAUSTED.value, WorkflowState.ESCALATED.value)
    assert "retry_scheduled" in result.state_history


def test_insufficient_funds_recovers_after_retries(phase2_db):
    _, conn = phase2_db
    case_id = _find_subscription_case(conn, "insufficient_funds")
    _prepare_test_case(conn, case_id)
    result = run_subscription_case(conn, case_id)
    assert result.recovered is True
    events = load_audit_trail(conn, case_id)
    assert "SIM_TIME_ADVANCED" in {e.event_type for e in events}


def test_expired_card_recovers_after_method_update(phase2_db):
    _, conn = phase2_db
    case_id = _find_subscription_case(conn, "expired_card")
    _prepare_test_case(conn, case_id)
    result = run_subscription_case(conn, case_id)
    assert result.recovered is True
    assert "contacted" in result.state_history
    assert "payment_method_update" in [a.action_id for a in result.candidate_actions]


def test_audit_trail_complete(phase2_db):
    _, conn = phase2_db
    case_id = _find_subscription_case(conn, "issuer_timeout")
    _prepare_test_case(conn, case_id)
    result = run_subscription_case(conn, case_id)
    events = load_audit_trail(conn, case_id)
    event_types = {e.event_type for e in events}
    assert {"DIAGNOSED", "ACTION_PROPOSED", "POLICY_CHECK", "ACTION_EXECUTED", "STATE_TRANSITION"} <= event_types
    assert result.audit_event_count >= 5


def test_reset_does_not_mutate_customer(phase2_db):
    _, conn = phase2_db
    case_id = _find_subscription_case(conn, "network_timeout")
    row = conn.execute(
        "SELECT customer_id FROM recovery_cases WHERE case_id = ?", (case_id,)
    ).fetchone()
    conn.execute(
        "UPDATE customers SET opt_out = 1, prior_contacts_7d = 2 WHERE customer_id = ?",
        (row["customer_id"],),
    )
    conn.commit()
    reset_case_for_run(conn, case_id)
    customer = conn.execute(
        "SELECT opt_out, prior_contacts_7d FROM customers WHERE customer_id = ?",
        (row["customer_id"],),
    ).fetchone()
    assert customer["opt_out"] == 1
    assert customer["prior_contacts_7d"] == 2


def test_runtime_modules_do_not_reference_ground_truth():
    runtime_modules = [
        Path("src/recovery/intelligence/diagnosis.py"),
        Path("src/recovery/intelligence/strategy.py"),
        Path("src/recovery/policy/gate.py"),
        Path("src/recovery/state/machine.py"),
        Path("src/recovery/execution/simulator.py"),
        Path("src/recovery/execution/sim_clock.py"),
        Path("src/recovery/execution/outcomes.py"),
        Path("src/recovery/pipeline/subscription_runner.py"),
        Path("src/recovery/ingestion/runtime_loader.py"),
    ]
    forbidden = ("case_ground_truth", "p_pay_anyway")
    root = Path(__file__).resolve().parents[1]
    for rel in runtime_modules:
        source = (root / rel).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{rel} must not reference {token}"


def test_case_persisted_after_run(phase2_db):
    _, conn = phase2_db
    case_id = _find_subscription_case(conn, "issuer_timeout")
    _prepare_test_case(conn, case_id)
    run_subscription_case(conn, case_id)
    row = conn.execute(
        "SELECT workflow_state, status FROM recovery_cases WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    assert row["workflow_state"] in (
        WorkflowState.RECOVERED.value,
        WorkflowState.EXHAUSTED.value,
        WorkflowState.ESCALATED.value,
    )
