"""Tests for Phase 3B deterministic intelligence implementations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from recovery.db import connect
from recovery.ingestion.runtime_loader import load_case_by_id
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
from recovery.intelligence.context_builder import build_recovery_context
from recovery.intelligence.deterministic.decision import (
    DeterministicDecisionIntelligence,
    propose_deterministic_decision,
)
from recovery.intelligence.deterministic.predictive import DeterministicPredictiveIntelligence
from recovery.intelligence.deterministic.reasoning import DeterministicReasoningIntelligence
from recovery.intelligence.deterministic.strategy import DeterministicStrategyIntelligence
from recovery.models.recovery_context import FORBIDDEN_CONTEXT_FIELDS
from recovery.state.context import CaseRunContext
from recovery.state.reset import reset_case_for_run


@pytest.fixture
def intel_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "intel.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def _case_id(conn, failure_reason: str) -> str:
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


def _prepare(conn, case_id: str) -> None:
    reset_case_for_run(conn, case_id)
    cust = conn.execute(
        "SELECT customer_id FROM recovery_cases WHERE case_id = ?", (case_id,)
    ).fetchone()[0]
    conn.execute(
        "UPDATE customers SET opt_out = 0, prior_contacts_7d = 0 WHERE customer_id = ?",
        (cust,),
    )
    conn.commit()


def test_predictive_scores_transient_higher_than_repeated(intel_db):
    conn = intel_db
    transient_id = _case_id(conn, "network_timeout")
    repeated_id = _case_id(conn, "repeated_failure")
    _prepare(conn, transient_id)
    _prepare(conn, repeated_id)
    transient_ctx = build_recovery_context(conn, transient_id)
    repeated_ctx = build_recovery_context(conn, repeated_id)

    predictive = DeterministicPredictiveIntelligence()
    t_score = predictive.score(transient_ctx)
    r_score = predictive.score(repeated_ctx)

    assert t_score.retry_success_likelihood > r_score.retry_success_likelihood
    assert t_score.estimated_recovery_probability > r_score.estimated_recovery_probability


def test_reasoning_includes_key_factors(intel_db):
    conn = intel_db
    case_id = _case_id(conn, "transient_technical")
    reset_case_for_run(conn, case_id)
    context = build_recovery_context(conn, case_id)

    insight = DeterministicReasoningIntelligence().interpret(context)

    assert insight.likely_cause == "transient_failure"
    assert "transient_failure" in insight.key_factors or insight.confidence > 0


def test_strategy_adapts_for_repeated_failure(intel_db):
    conn = intel_db
    case_id = _case_id(conn, "repeated_failure")
    _prepare(conn, case_id)
    context = build_recovery_context(conn, case_id)
    reasoning = DeterministicReasoningIntelligence().interpret(context)
    predictive = DeterministicPredictiveIntelligence().score(context)

    proposals = DeterministicStrategyIntelligence().propose_strategies(
        context, reasoning, predictive
    )
    action_ids = [p.action.action_id for p in proposals]

    assert "human_escalation" in action_ids
    assert proposals[0].action.action_id in ("payment_method_update", "human_escalation", "retry_72h")


def test_strategy_skips_method_update_when_already_updated(intel_db):
    conn = intel_db
    case = load_case_by_id(conn, _case_id(conn, "expired_card"))
    assert case is not None
    run_ctx = CaseRunContext(case=case)
    run_ctx.payment_method_updated = True
    context = build_recovery_context(conn, case.case_id, run_context=run_ctx)

    reasoning = DeterministicReasoningIntelligence().interpret(context)
    predictive = DeterministicPredictiveIntelligence().score(context)
    proposals = DeterministicStrategyIntelligence().propose_strategies(
        context, reasoning, predictive
    )

    assert all(p.action.action_id != "payment_method_update" for p in proposals)


def test_decision_proposal_end_to_end(intel_db):
    conn = intel_db
    case_id = _case_id(conn, "insufficient_funds")
    context = build_recovery_context(conn, case_id)

    decision = propose_deterministic_decision(context)

    assert decision.recommended_action.action_id
    assert len(decision.candidate_actions) >= 1
    assert decision.reasoning.likely_cause
    assert decision.predictive.estimated_recovery_probability > 0
    decision.validate_no_forbidden_fields()
    for forbidden in FORBIDDEN_CONTEXT_FIELDS:
        assert forbidden not in str(decision.to_dict())


def test_decision_deterministic(intel_db):
    conn = intel_db
    context = build_recovery_context(
        conn,
        _case_id(conn, "issuer_timeout"),
        now=datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc),
    )
    d1 = DeterministicDecisionIntelligence().propose_decision(context)
    d2 = DeterministicDecisionIntelligence().propose_decision(context)

    assert d1.recommended_action.action_id == d2.recommended_action.action_id
    assert d1.explanation == d2.explanation
