"""Tests for Phase 4D adaptive checkout demonstration scenarios."""

from __future__ import annotations

from pathlib import Path

import pytest

from recovery.db import connect
from recovery.demos.adaptive_checkout import (
    load_checkout_demo_scenarios,
    run_adaptive_checkout_demos,
)
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset


@pytest.fixture
def checkout_demo_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "adaptive_checkout_demos.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def test_load_checkout_demo_scenarios():
    scenarios = load_checkout_demo_scenarios()
    assert len(scenarios) == 4
    ids = {s.id for s in scenarios}
    assert ids == {
        "high_intent_payment_recovery",
        "non_response_replan",
        "low_intent_bounded",
        "policy_constrained_incentive",
    }


def test_all_checkout_demos_pass_deterministic(checkout_demo_db):
    report = run_adaptive_checkout_demos(checkout_demo_db, intelligence_mode="deterministic")
    assert report.passed, {
        o.scenario.id: o.failures for o in report.outcomes if not o.passed
    }


def test_checkout_scenarios_produce_distinct_paths(checkout_demo_db):
    report = run_adaptive_checkout_demos(checkout_demo_db, intelligence_mode="deterministic")
    action_paths = tuple(tuple(o.action_sequence) for o in report.outcomes)
    assert len(set(action_paths)) >= 3, "Expected distinct action paths across checkout demos"


def test_high_intent_faster_than_incentive_path(checkout_demo_db):
    report = run_adaptive_checkout_demos(checkout_demo_db, intelligence_mode="deterministic")
    by_id = {o.scenario.id: o for o in report.outcomes}
    high = by_id["high_intent_payment_recovery"]
    incentive = by_id["policy_constrained_incentive"]
    assert high.result.agent_steps < incentive.result.agent_steps
    assert "limited_incentive" not in high.action_sequence
    assert "limited_incentive" in incentive.action_sequence


def test_low_intent_does_not_recover(checkout_demo_db):
    report = run_adaptive_checkout_demos(checkout_demo_db, intelligence_mode="deterministic")
    low = next(o for o in report.outcomes if o.scenario.id == "low_intent_bounded")
    assert low.result.recovered is False
    assert "stop_recovery" in low.action_sequence
    assert low.passed is True
