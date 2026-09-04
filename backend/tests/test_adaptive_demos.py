"""Tests for Phase 3F adaptive demonstration scenarios."""

from __future__ import annotations

from pathlib import Path

import pytest

from recovery.db import connect
from recovery.demos.adaptive import (
    load_adaptive_scenarios,
    run_adaptive_demos,
)
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset


@pytest.fixture
def demo_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "adaptive_demos.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def test_load_adaptive_scenarios():
    scenarios = load_adaptive_scenarios()
    assert len(scenarios) >= 5
    ids = {s.id for s in scenarios}
    assert "transient_fast_retry" in ids
    assert "insufficient_funds_adaptive" in ids
    assert "hero_expired_subscription" in ids


def test_all_adaptive_demos_pass_deterministic(demo_db):
    report = run_adaptive_demos(demo_db, intelligence_mode="deterministic")
    assert report.passed, [o.failures for o in report.outcomes if not o.passed]


def test_scenarios_produce_distinct_paths(demo_db):
    report = run_adaptive_demos(demo_db, intelligence_mode="deterministic")
    state_paths = tuple("->".join(o.result.state_history) for o in report.outcomes)
    assert len(set(state_paths)) >= 3, "Expected distinct recovery paths across scenarios"


def test_insufficient_funds_has_more_steps_than_transient(demo_db):
    report = run_adaptive_demos(demo_db, intelligence_mode="deterministic")
    by_id = {o.scenario.id: o for o in report.outcomes}
    transient = by_id["transient_fast_retry"]
    funds = by_id["insufficient_funds_adaptive"]
    assert funds.result.agent_steps > transient.result.agent_steps
    assert funds.result.replan_count > transient.result.replan_count


def test_repeated_failure_does_not_recover(demo_db):
    report = run_adaptive_demos(demo_db, intelligence_mode="deterministic")
    repeated = next(o for o in report.outcomes if o.scenario.id == "repeated_failure_terminal")
    assert repeated.result.recovered is False
    assert repeated.passed is True
