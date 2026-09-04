"""Tests for Phase 3E agentic recovery loop."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from recovery.audit.trail import load_audit_trail
from recovery.db import connect
from recovery.execution.sim_clock import SimulatedClock
from recovery.ingestion.customer_loader import load_customer_context
from recovery.ingestion.runtime_loader import load_case_by_id
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
from recovery.intelligence.decision_config import DecisionConfig
from recovery.intelligence.decisioning import HybridDecisionIntelligence
from recovery.models.enums import WorkflowState
from recovery.pipeline.agentic_loop import AgenticRecoveryLoop
from recovery.pipeline.subscription_runner import run_subscription_case
from recovery.policy.gate import load_policy_config
from recovery.state.context import CaseRunContext
from recovery.state.reset import reset_case_for_run


@pytest.fixture
def agent_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "agentic.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def _case_id(conn: sqlite3.Connection, failure_reason: str) -> str:
    row = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'subscription_payment' AND failure_reason = ?
        LIMIT 1
        """,
        (failure_reason,),
    ).fetchone()
    assert row is not None
    return row["case_id"]


def _prepare(conn: sqlite3.Connection, case_id: str) -> None:
    reset_case_for_run(conn, case_id)
    row = conn.execute(
        "SELECT customer_id FROM recovery_cases WHERE case_id = ?", (case_id,)
    ).fetchone()
    conn.execute(
        "UPDATE customers SET opt_out = 0, prior_contacts_7d = 0 WHERE customer_id = ?",
        (row["customer_id"],),
    )
    conn.commit()


def test_agentic_loop_emits_observe_and_replan_events(agent_db):
    conn = agent_db
    case_id = _case_id(conn, "insufficient_funds")
    _prepare(conn, case_id)

    result = run_subscription_case(conn, case_id, intelligence_mode="deterministic")
    events = load_audit_trail(conn, case_id)
    event_types = {e.event_type for e in events}

    assert "AGENT_OBSERVE" in event_types
    assert result.agent_steps >= 1
    assert result.replan_count >= 1
    assert result.recovered is True


def test_agentic_loop_replans_after_failed_retry(agent_db):
    conn = agent_db
    case_id = _case_id(conn, "insufficient_funds")
    _prepare(conn, case_id)

    case = load_case_by_id(conn, case_id)
    customer = load_customer_context(conn, case.customer_id)
    ctx = CaseRunContext(case=case)
    clock = SimulatedClock()
    engine = HybridDecisionIntelligence(
        config=DecisionConfig(mode="deterministic", min_reasoning_confidence=0.4, min_strategy_confidence=0.3)
    )
    loop = AgenticRecoveryLoop(engine, load_policy_config())

    from recovery.state.machine import apply_transition

    apply_transition(ctx, "case_diagnosed")

    loop_result = loop.run(conn, case_id, ctx, customer, clock)

    assert len(loop_result.steps) >= 2
    assert loop_result.replan_count >= 1
    assert any(step.execution is not None for step in loop_result.steps)
    assert loop_result.recovered is True


def test_multiple_decision_proposed_per_run(agent_db):
    conn = agent_db
    case_id = _case_id(conn, "network_timeout")
    _prepare(conn, case_id)

    run_subscription_case(conn, case_id, intelligence_mode="deterministic")
    events = load_audit_trail(conn, case_id)
    proposed = [e for e in events if e.event_type == "DECISION_PROPOSED"]
    assert len(proposed) >= 1


def test_agentic_transient_recovery(agent_db):
    conn = agent_db
    case_id = _case_id(conn, "network_timeout")
    _prepare(conn, case_id)

    result = run_subscription_case(conn, case_id, intelligence_mode="deterministic")
    assert result.recovered is True
    assert result.terminal_state == WorkflowState.RECOVERED.value
    assert result.agent_steps >= 1
