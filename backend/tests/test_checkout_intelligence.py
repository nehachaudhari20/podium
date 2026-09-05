"""Tests for Phase 4B checkout diagnosis and strategy intelligence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from recovery.db import connect
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
from recovery.intelligence.checkout_diagnosis import diagnose_checkout
from recovery.intelligence.checkout_strategy import generate_checkout_actions
from recovery.intelligence.context_builder import build_recovery_context
from recovery.intelligence.deterministic.decision import propose_deterministic_decision
from recovery.intelligence.deterministic.reasoning import DeterministicReasoningIntelligence
from recovery.intelligence.deterministic.strategy import DeterministicStrategyIntelligence
from recovery.intelligence.deterministic.predictive import DeterministicPredictiveIntelligence
from recovery.intelligence.diagnosis import diagnose
from recovery.models.case import RecoveryCaseRuntime
from recovery.models.enums import Lane
from recovery.models.recovery_types import DiagnosisResult


@pytest.fixture
def checkout_intel_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "checkout_intel.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def _checkout_runtime(failure_reason: str, **overrides) -> RecoveryCaseRuntime:
    now = datetime(2026, 2, 15, 10, 0, 0, tzinfo=timezone.utc)
    defaults = dict(
        case_id="case_chk_test",
        customer_id="cust_chk_test",
        lane=Lane.CHECKOUT_ABANDONMENT.value,
        amount=20000.0,
        currency="INR",
        status="open",
        workflow_state="detected",
        created_at=now,
        recovery_window_end=now + timedelta(days=14),
        source_ref_id="chk_test",
        failure_reason=failure_reason,
        recoverability_hint="high",
        days_overdue=None,
        attempt_count=0,
        estimated_recovery_prob=None,
        is_hero=False,
    )
    defaults.update(overrides)
    return RecoveryCaseRuntime(**defaults)


def test_checkout_diagnose_maps_failure_reasons():
    assert diagnose(_checkout_runtime("checkout_payment_page_drop")).likely_cause == "payment_friction"
    assert diagnose(_checkout_runtime("checkout_cart_abandon")).likely_cause == "checkout_friction"
    assert diagnose(_checkout_runtime("checkout_high_intent_drop")).likely_cause == "distraction_or_delay"


def test_hero_checkout_prefers_low_friction_actions(checkout_intel_db):
    conn = checkout_intel_db
    context = build_recovery_context(conn, "case_hero_chk_001")
    decision = propose_deterministic_decision(context)

    assert decision.reasoning.likely_cause in {
        "payment_friction",
        "distraction_or_delay",
    }
    ids = [a.action_id for a in decision.candidate_actions]
    assert ids[0] in {"payment_link", "checkout_reminder", "checkout_assistance"}
    assert ids[0] != "limited_incentive"
    assert "limited_incentive" not in ids[:1]


def test_high_intent_does_not_lead_with_incentive(checkout_intel_db):
    conn = checkout_intel_db
    case_id = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'checkout_abandonment' AND failure_reason = 'checkout_high_intent_drop'
        LIMIT 1
        """
    ).fetchone()["case_id"]
    context = build_recovery_context(conn, case_id)
    reasoning = DeterministicReasoningIntelligence().interpret(context)
    predictive = DeterministicPredictiveIntelligence().score(context)
    proposals = DeterministicStrategyIntelligence().propose_strategies(context, reasoning, predictive)
    assert proposals[0].action.action_id != "limited_incentive"


def test_low_intent_includes_stop_or_bounded_reminder(checkout_intel_db):
    conn = checkout_intel_db
    # Find a low-intent session via checkout_sessions
    row = conn.execute(
        """
        SELECT c.case_id FROM recovery_cases c
        JOIN checkout_sessions s ON s.case_id = c.case_id
        WHERE c.lane = 'checkout_abandonment' AND s.intent_score < 0.45
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        pytest.skip("No low-intent checkout case in seed dataset")
    context = build_recovery_context(conn, row["case_id"])
    decision = propose_deterministic_decision(context)
    ids = [a.action_id for a in decision.candidate_actions]
    assert "limited_incentive" not in ids
    assert "checkout_reminder" in ids or "stop_recovery" in ids


def test_replan_after_reminder_prefers_different_action(checkout_intel_db):
    conn = checkout_intel_db
    context = build_recovery_context(conn, "case_hero_chk_001")
    # Simulate prior reminder in memory overlay via CaseFacts replacement is hard;
    # call strategy with diagnosis + synthetic last_action through generate_checkout_actions.
    runtime = _checkout_runtime("checkout_high_intent_drop")
    diagnosis = DiagnosisResult(
        likely_cause="distraction_or_delay",
        confidence=0.8,
        rationale="test",
    )
    # Build a shallow context-like object by rebuilding with mutated case facts
    from dataclasses import replace

    mutated = replace(context, case=replace(context.case, last_action="checkout_reminder"))
    actions = generate_checkout_actions(runtime, diagnosis, mutated)
    assert actions[0].action_id != "checkout_reminder"
    assert actions[0].action_id in {"payment_link", "checkout_assistance"}


def test_subscription_diagnosis_unchanged(checkout_intel_db):
    conn = checkout_intel_db
    row = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'subscription_payment' AND failure_reason = 'network_timeout'
        LIMIT 1
        """
    ).fetchone()
    context = build_recovery_context(conn, row["case_id"])
    decision = propose_deterministic_decision(context)
    assert decision.reasoning.likely_cause == "transient_failure"
    assert decision.candidate_actions[0].is_retry


def test_opt_out_blocks_checkout_contacts(checkout_intel_db):
    conn = checkout_intel_db
    context = build_recovery_context(conn, "case_hero_chk_001")
    from dataclasses import replace

    customer = replace(context.customer, opt_out=True)
    signals = replace(context.derived_signals, customer_opt_out=True)
    opted = replace(context, customer=customer, derived_signals=signals)
    decision = propose_deterministic_decision(opted)
    assert all(not a.is_contact for a in decision.candidate_actions)
    assert any(a.action_id == "stop_recovery" for a in decision.candidate_actions)


def test_context_aware_checkout_diagnosis_uses_signals(checkout_intel_db):
    conn = checkout_intel_db
    context = build_recovery_context(conn, "case_hero_chk_001")
    runtime = _checkout_runtime("checkout_high_intent_drop")
    result = diagnose_checkout(runtime, context)
    assert result.likely_cause in {"payment_friction", "distraction_or_delay"}
    assert result.confidence >= 0.8
