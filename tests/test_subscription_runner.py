"""Phase 2 integration tests — subscription recovery pipeline."""

from __future__ import annotations

import ast
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from podium.audit.trail import load_audit_trail
from podium.db import connect
from podium.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
from podium.models.enums import Lane, WorkflowState
from podium.pipeline.subscription_runner import run_subscription_case


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


from podium.state.reset import reset_case_for_run


def test_success_path_transient_failure(phase2_db):
    db_path, conn = phase2_db
    case_id = _find_subscription_case(conn, "network_timeout")
    reset_case_for_run(conn, case_id)
    result = run_subscription_case(conn, case_id)
    assert result.recovered is True
    assert result.terminal_state == WorkflowState.RECOVERED.value
    assert "detected" in result.state_history
    assert "diagnosed" in result.state_history
    assert result.amount_recovered > 0


def test_exhaustion_path_repeated_failure(phase2_db):
    db_path, conn = phase2_db
    case_id = _find_subscription_case(conn, "repeated_failure")
    result = run_subscription_case(conn, case_id)
    assert result.recovered is False
    assert result.terminal_state in (WorkflowState.EXHAUSTED.value, WorkflowState.ESCALATED.value)


def test_expired_card_recovers_after_method_update(phase2_db):
    db_path, conn = phase2_db
    case_id = _find_subscription_case(conn, "expired_card")
    reset_case_for_run(conn, case_id)
    result = run_subscription_case(conn, case_id)
    assert result.recovered is True
    assert "payment_method_update" in [a.action_id for a in result.candidate_actions]


def test_audit_trail_recorded(phase2_db):
    db_path, conn = phase2_db
    case_id = _find_subscription_case(conn, "transient_technical")
    result = run_subscription_case(conn, case_id)
    events = load_audit_trail(conn, case_id)
    event_types = {e.event_type for e in events}
    assert "DIAGNOSED" in event_types
    assert "POLICY_CHECK" in event_types
    assert "ACTION_EXECUTED" in event_types
    assert "STATE_TRANSITION" in event_types
    assert result.audit_event_count >= 4


def test_runtime_modules_do_not_reference_ground_truth():
    """Hard check: Phase 2 runtime modules must not query evaluator ground truth."""
    runtime_modules = [
        Path("src/podium/intelligence/diagnosis.py"),
        Path("src/podium/intelligence/strategy.py"),
        Path("src/podium/policy/gate.py"),
        Path("src/podium/state/machine.py"),
        Path("src/podium/execution/simulator.py"),
        Path("src/podium/execution/outcomes.py"),
        Path("src/podium/pipeline/subscription_runner.py"),
        Path("src/podium/ingestion/runtime_loader.py"),
    ]
    forbidden = ("case_ground_truth", "p_pay_anyway")
    root = Path(__file__).resolve().parents[1]
    for rel in runtime_modules:
        source = (root / rel).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{rel} must not reference {token}"


def test_case_persisted_after_run(phase2_db):
    db_path, conn = phase2_db
    case_id = _find_subscription_case(conn, "issuer_timeout")
    run_subscription_case(conn, case_id)
    row = conn.execute(
        "SELECT workflow_state, status FROM recovery_cases WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    assert row["workflow_state"] in (
        WorkflowState.RECOVERED.value,
        WorkflowState.EXHAUSTED.value,
        WorkflowState.ESCALATED.value,
        WorkflowState.WAITING.value,
    )
