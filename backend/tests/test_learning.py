"""Phase 8 — outcome-driven learning tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from recovery.db import connect
from recovery.demos.learning import run_learning_demos
from recovery.economics.engine import probability_for_action, select_best_economic_action
from recovery.evaluation.phase8_runner import run_phase8_evaluation
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
from recovery.intelligence.contracts import PredictiveSignals
from recovery.learning.blend import blend_probability, clamp_probability
from recovery.learning.calibration import compute_calibration
from recovery.learning.effectiveness import confidence_for_count, get_historical_evidence
from recovery.learning.records import FORBIDDEN_LEARNING_FIELDS, build_decision_outcome
from recovery.learning.replay import replay_outcomes
from recovery.learning.signals import generate_learning_signal
from recovery.learning.store import ExperienceQuery, ExperienceStore
from recovery.models.recovery_types import RecoveryAction
from recovery.pipeline.subscription_runner import run_subscription_case
from recovery.state.reset import reset_case_for_run
from recovery.audit.trail import load_audit_trail


@pytest.fixture
def learning_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "learning.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def _mk(
    *,
    action: str = "payment_link",
    lane: str = "receivable",
    recovered: bool = True,
    amount: float = 10000,
    cost: float = 2,
    prob: float = 0.6,
    idx: int = 0,
):
    return build_decision_outcome(
        case_id=f"case_l_{idx}",
        customer_id="cust_l",
        lane=lane,
        action=action,
        amount_at_risk=amount,
        intervention_cost=cost,
        estimated_recovery_probability=prob,
        observed_recovered=recovered,
        amount_recovered=amount if recovered else 0,
        amount_remaining=0 if recovered else amount,
        diagnosis="temporary_cash_constraint",
        timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc).isoformat(),
    )


def test_outcome_record_forbids_evaluator_fields():
    outcome = _mk()
    data = outcome.to_dict()
    for key in FORBIDDEN_LEARNING_FIELDS:
        assert key not in data
        assert key not in data.get("metadata", {})


def test_learning_signal_prediction_error():
    success = _mk(recovered=True, prob=0.7)
    signal = generate_learning_signal(success)
    assert signal.recovered is True
    assert signal.prediction_error == pytest.approx(0.3)
    fail = _mk(recovered=False, prob=0.7, idx=1)
    signal_f = generate_learning_signal(fail)
    assert signal_f.prediction_error == pytest.approx(-0.7)


def test_experience_store_roundtrip(learning_db):
    conn = learning_db
    store = ExperienceStore(conn)
    store.clear()
    outcome = _mk()
    store.record(outcome)
    loaded = store.get(outcome.outcome_id)
    assert loaded is not None
    assert loaded.action == "payment_link"
    assert store.count(ExperienceQuery(action="payment_link")) == 1


def test_confidence_thresholds():
    assert confidence_for_count(2) == "low"
    assert confidence_for_count(10) == "medium"
    assert confidence_for_count(25) == "high"


def test_cold_start_blend():
    blended = blend_probability(0.55, None)
    assert blended.used_history is False
    assert blended.confidence == "low"
    assert blended.blended_probability == 0.55


def test_blend_uses_history(learning_db):
    conn = learning_db
    store = ExperienceStore(conn)
    store.clear()
    rows = [_mk(recovered=True, idx=i) for i in range(10)]
    replay_outcomes(conn, rows, clear=False)
    evidence = get_historical_evidence(store, action="payment_link", lane="receivable")
    blended = blend_probability(0.50, evidence)
    assert blended.used_history is True
    assert blended.blended_probability > 0.50
    assert 0.01 <= blended.blended_probability <= 0.99


def test_clamp_probability():
    assert clamp_probability(-1) >= 0.01
    assert clamp_probability(2) <= 0.99


def test_calibration_metrics(learning_db):
    conn = learning_db
    store = ExperienceStore(conn)
    store.clear()
    rows = [_mk(recovered=True, prob=0.75, idx=i) for i in range(8)] + [
        _mk(recovered=False, prob=0.75, idx=100 + i) for i in range(2)
    ]
    replay_outcomes(conn, rows)
    report = compute_calibration(store.list_outcomes())
    assert report.cases == 10
    assert report.brier_score >= 0
    assert report.buckets


def test_economics_uses_learning(learning_db):
    conn = learning_db
    store = ExperienceStore(conn)
    store.clear()
    rows = [
        _mk(action="payment_link", recovered=True, amount=40000, cost=2, idx=i)
        for i in range(12)
    ] + [
        _mk(
            action="human_escalation",
            recovered=(i < 2),
            amount=40000,
            cost=500,
            idx=50 + i,
        )
        for i in range(12)
    ]
    replay_outcomes(conn, rows)
    predictive = PredictiveSignals(0.55, 0.4, 0.5)
    actions = [
        RecoveryAction("payment_link", "Link", "email", is_contact=True),
        RecoveryAction("human_escalation", "Human", "human", is_contact=True),
    ]
    decision = select_best_economic_action(
        actions,
        amount_at_risk=40000,
        predictive=predictive,
        experience_store=store,
        lane="receivable",
    )
    assert decision.selected is not None
    assert decision.selected.action_id == "payment_link"


def test_agentic_records_outcomes(learning_db):
    conn = learning_db
    store = ExperienceStore(conn)
    store.clear()
    row = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'subscription_payment' AND failure_reason = 'transient_technical'
        LIMIT 1
        """
    ).fetchone()
    assert row is not None
    case_id = row["case_id"]
    reset_case_for_run(conn, case_id)
    cust = conn.execute(
        "SELECT customer_id FROM recovery_cases WHERE case_id = ?", (case_id,)
    ).fetchone()["customer_id"]
    conn.execute(
        "UPDATE customers SET opt_out = 0, prior_contacts_7d = 0 WHERE customer_id = ?",
        (cust,),
    )
    conn.commit()
    result = run_subscription_case(conn, case_id, intelligence_mode="deterministic")
    assert result.terminal_state
    events = {e.event_type for e in load_audit_trail(conn, case_id)}
    assert "OUTCOME_RECORDED" in events or "EXPERIENCE_UPDATED" in events
    assert store.count() >= 1
    # Ensure evaluator-only field never appears in stored metadata
    for outcome in store.list_outcomes():
        assert "p_pay_anyway" not in outcome.to_dict()
        assert "p_pay_anyway" not in outcome.metadata


def test_probability_for_action_cold_start_unchanged():
    predictive = PredictiveSignals(0.6, 0.5, 0.5)
    action = RecoveryAction("payment_link", "Link", "email", is_contact=True)
    p = probability_for_action(action, predictive)
    assert 0 < p <= 0.99


def test_learning_demos_and_evaluation(learning_db):
    conn = learning_db
    report = run_learning_demos(conn)
    assert sum(1 for o in report.outcomes if o.passed) >= 6
    summary = run_phase8_evaluation(conn, limit=5)
    assert summary.scenarios_passed >= 6
    assert summary.detail.get("p_pay_anyway_isolated") is True
    assert summary.baseline_vs_learned.get("p_pay_anyway_isolated") is True
