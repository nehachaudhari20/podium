"""Tests for Phase 6 cross-revenue coordination."""

from __future__ import annotations

from pathlib import Path

import pytest

from recovery.db import connect
from recovery.demos.coordination import (
    prepare_customer_cases,
    run_coordination_demos,
    run_hero_coordination_demo,
)
from recovery.coordination.runner import plan_customer_recovery
from recovery.coordination.view import load_customer_recovery_view
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
from recovery.ingestion.synthetic.hero_scenario import HERO_CUSTOMER_ID
from recovery.intelligence.context_builder import build_recovery_context
from recovery.models.enums import Lane
from recovery.models.recovery_context import FORBIDDEN_CONTEXT_FIELDS, assert_no_forbidden_fields


@pytest.fixture
def coord_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "coord.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def test_hero_customer_aggregation(coord_db):
    prepare_customer_cases(coord_db, HERO_CUSTOMER_ID)
    view = load_customer_recovery_view(coord_db, HERO_CUSTOMER_ID)
    assert view.open_case_count == 3
    assert set(view.active_lanes) == {
        Lane.SUBSCRIPTION_PAYMENT.value,
        Lane.CHECKOUT_ABANDONMENT.value,
        Lane.RECEIVABLE.value,
    }
    assert view.total_amount_at_risk == pytest.approx(5000 + 20000 + 80000)
    assert view.highest_value_case_id == "case_hero_inv_001"


def test_cross_revenue_context_on_case(coord_db):
    prepare_customer_cases(coord_db, HERO_CUSTOMER_ID)
    context = build_recovery_context(coord_db, "case_hero_sub_001")
    assert context.cross_revenue is not None
    assert context.cross_revenue.multi_lane_active is True
    assert context.derived_signals.multi_lane_active is True
    assert context.derived_signals.has_sibling_open_cases is True
    assert len(context.cross_revenue.sibling_cases) == 2
    assert_no_forbidden_fields(context.to_dict())
    payload = context.to_dict()
    for key in FORBIDDEN_CONTEXT_FIELDS:
        assert key not in str(payload)


def test_coordination_demos_pass(coord_db):
    report = run_coordination_demos(coord_db)
    assert report.passed, {o.scenario_id: o.failures for o in report.outcomes if not o.passed}


def test_hero_demo_produces_plan(coord_db):
    view, coordinated, independent, text = run_hero_coordination_demo(coord_db)
    assert view.customer_id == HERO_CUSTOMER_ID
    assert "TOTAL AT RISK" in text
    assert coordinated.mode == "coordinated"
    assert independent.mode == "independent"
    assert coordinated.selected_actions or coordinated.deferred_actions


def test_plan_audits_coordination_events(coord_db):
    prepare_customer_cases(coord_db, HERO_CUSTOMER_ID)
    plan_customer_recovery(coord_db, HERO_CUSTOMER_ID, coordinated=True)
    rows = coord_db.execute(
        """
        SELECT DISTINCT event_type FROM audit_events
        WHERE customer_id = ?
        """,
        (HERO_CUSTOMER_ID,),
    ).fetchall()
    types = {r["event_type"] for r in rows}
    assert "CUSTOMER_RECOVERY_VIEW_BUILT" in types
    assert "CUSTOMER_RECOVERY_PLAN_CREATED" in types


def test_runtime_coordination_forbids_ground_truth():
    root = Path(__file__).resolve().parents[1]
    modules = [
        "src/recovery/coordination/view.py",
        "src/recovery/coordination/planner.py",
        "src/recovery/coordination/runner.py",
        "src/recovery/coordination/rules.py",
        "src/recovery/demos/coordination.py",
    ]
    for rel in modules:
        source = (root / rel).read_text(encoding="utf-8")
        assert "p_pay_anyway" not in source
        assert "case_ground_truth" not in source
        assert "from recovery.evaluation.ground_truth" not in source


def test_replan_after_case_closed(coord_db):
    prepare_customer_cases(coord_db, HERO_CUSTOMER_ID)
    view1 = load_customer_recovery_view(coord_db, HERO_CUSTOMER_ID)
    assert view1.open_case_count == 3
    coord_db.execute(
        "UPDATE recovery_cases SET status = 'closed', workflow_state = 'recovered' WHERE case_id = ?",
        ("case_hero_sub_001",),
    )
    coord_db.commit()
    view2 = load_customer_recovery_view(coord_db, HERO_CUSTOMER_ID)
    assert view2.open_case_count == 2
    assert Lane.SUBSCRIPTION_PAYMENT.value not in view2.active_lanes
    _, _, plan = plan_customer_recovery(coord_db, HERO_CUSTOMER_ID, coordinated=True)
    assert all(a.case_id != "case_hero_sub_001" for a in plan.selected_actions)
