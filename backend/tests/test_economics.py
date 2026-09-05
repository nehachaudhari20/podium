"""Focused Phase 5 economic decision tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from recovery.audit.trail import load_audit_trail
from recovery.db import connect
from recovery.demos.economic import run_economic_demos
from recovery.economics.allocator import (
    AllocationRequest,
    CapacityPool,
    allocate_batch,
)
from recovery.economics.config import CapacityLimits, load_economics_config
from recovery.economics.engine import select_best_economic_action
from recovery.economics.model import (
    evaluate_action_economics,
    expected_net_value,
    expected_recovery_value,
)
from recovery.ingestion.customer_loader import CustomerContext
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
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
from recovery.pipeline.subscription_runner import run_subscription_case
from recovery.state.reset import reset_case_for_run


RETRY = RecoveryAction("retry_24h", "Retry", "system", is_retry=True, retry_delay_hours=24)
HUMAN = RecoveryAction("human_escalation", "Escalate", "human", is_contact=True)
VOICE = RecoveryAction("voice_call", "Call", "voice")
STOP = RecoveryAction("stop_recovery", "Stop", "system")


def test_expected_value_math():
    assert expected_recovery_value(10000, 0.6) == 6000.0
    assert expected_net_value(6000, 50) == 5950.0
    assert expected_net_value(100, 200) == -100.0


def test_zero_cost_intervention():
    action = RecoveryAction("retry_6h", "Retry", "system", is_retry=True, retry_delay_hours=6)
    candidate = evaluate_action_economics(
        action, amount_at_risk=1000, probability=0.5, intervention_cost=0.0
    )
    assert candidate.eligible is True
    assert candidate.expected_net_value == 500.0


def test_negative_value_rejected():
    candidate = evaluate_action_economics(
        VOICE, amount_at_risk=1000, probability=0.10, intervention_cost=200.0
    )
    assert candidate.eligible is False
    assert candidate.expected_net_value == -100.0


def test_cheap_beats_higher_probability():
    predictive = PredictiveSignals(0.50, 0.50, 0.55)
    decision = select_best_economic_action(
        [RETRY, HUMAN], amount_at_risk=5000, predictive=predictive
    )
    assert decision.selected is not None
    assert decision.selected.action_id == "retry_24h"


def test_expensive_justified_on_large_amount():
    predictive = PredictiveSignals(0.55, 0.20, 0.60)
    decision = select_best_economic_action(
        [RETRY, HUMAN], amount_at_risk=50000, predictive=predictive
    )
    assert decision.selected is not None
    assert decision.selected.action_id == "human_escalation"


def test_capacity_allocates_highest_value():
    cfg = load_economics_config()
    pool = CapacityPool.from_limits(
        CapacityLimits(
            max_voice_calls_per_batch=10,
            max_human_escalations_per_batch=2,
            max_incentive_budget=5000,
        )
    )
    requests = []
    for case_id, amount in (("A", 10000), ("B", 8000), ("C", 4000)):
        candidate = evaluate_action_economics(
            HUMAN, amount_at_risk=amount, probability=0.5, intervention_cost=500
        )
        requests.append(AllocationRequest(case_id=case_id, candidate=candidate))
    report = allocate_batch(requests, config=cfg, pool=pool)
    assert {r.case_id for r in report.selected} == {"A", "B"}
    assert {r.case_id for r in report.deferred} == {"C"}


def test_policy_overrides_positive_economics():
    now = datetime(2026, 2, 1, 10, 0, 0)
    case = RecoveryCaseRuntime(
        case_id="case_econ_1",
        customer_id="cust_econ_1",
        lane=Lane.SUBSCRIPTION_PAYMENT.value,
        amount=20000.0,
        currency="INR",
        status="open",
        workflow_state="diagnosed",
        created_at=now,
        recovery_window_end=now + timedelta(days=14),
        source_ref_id="sub",
        failure_reason="repeated_failure",
        recoverability_hint="medium",
        days_overdue=None,
        attempt_count=0,
        estimated_recovery_prob=None,
    )
    customer = CustomerContext("cust_econ_1", opt_out=True, prior_contacts_7d=0, segment="b2c")
    predictive = PredictiveSignals(0.70, 0.20, 0.80)
    actions = (HUMAN, RETRY)
    proposal = DecisionProposal(
        recommended_action=HUMAN,
        candidate_actions=actions,
        reasoning=ReasoningInsight("demo", "repeated_failure", 0.7, ("demo",)),
        predictive=predictive,
        strategy_proposals=(
            StrategyProposal(HUMAN, "econ", 1, 0.8),
            StrategyProposal(RETRY, "econ", 2, 0.4),
        ),
        explanation="demo",
    )
    evaluated = evaluate_decision_proposal(proposal, case, customer)
    assert evaluated.selected_action is not None
    assert evaluated.selected_action.action_id == "retry_24h"
    assert any(c.action == "human_escalation" and not c.allowed for c in evaluated.policy_checks)


def test_all_economic_demos_pass():
    report = run_economic_demos()
    assert report.passed, {o.scenario_id: o.failures for o in report.outcomes if not o.passed}


def test_runtime_economics_forbid_p_pay_anyway():
    root = Path(__file__).resolve().parents[1]
    modules = [
        "src/recovery/economics/engine.py",
        "src/recovery/economics/model.py",
        "src/recovery/economics/allocator.py",
        "src/recovery/economics/config.py",
        "src/recovery/intelligence/decision_evaluator.py",
        "src/recovery/pipeline/agentic_loop.py",
    ]
    for rel in modules:
        source = (root / rel).read_text(encoding="utf-8")
        assert "p_pay_anyway" not in source
        assert "case_ground_truth" not in source
        assert "from recovery.evaluation.ground_truth" not in source


@pytest.fixture
def econ_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "econ.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def test_agentic_records_economic_audit(econ_db):
    row = econ_db.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'subscription_payment' AND failure_reason = 'network_timeout'
        LIMIT 1
        """
    ).fetchone()
    reset_case_for_run(econ_db, row["case_id"])
    econ_db.execute(
        "UPDATE customers SET opt_out = 0, prior_contacts_7d = 0 WHERE customer_id = "
        "(SELECT customer_id FROM recovery_cases WHERE case_id = ?)",
        (row["case_id"],),
    )
    econ_db.commit()
    result = run_subscription_case(econ_db, row["case_id"], intelligence_mode="deterministic")
    events = {e.event_type for e in load_audit_trail(econ_db, row["case_id"])}
    assert "ECONOMIC_EVALUATION" in events
    assert result.economic_reason is not None
    assert result.expected_net_value is not None
