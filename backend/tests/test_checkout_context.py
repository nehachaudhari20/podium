"""Tests for Phase 4A checkout recovery context."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from recovery.db import connect
from recovery.evaluation.ground_truth import load_ground_truth
from recovery.ingestion.checkout_loader import (
    count_prior_checkout_abandonments,
    load_checkout_session_by_case,
)
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
from recovery.intelligence.context_builder import ContextBuilder, build_recovery_context
from recovery.models.enums import Lane
from recovery.models.recovery_context import FORBIDDEN_CONTEXT_FIELDS, assert_no_forbidden_fields


@pytest.fixture
def checkout_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "checkout_context.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def _checkout_case_id(conn, failure_reason: str | None = None) -> str:
    if failure_reason:
        row = conn.execute(
            """
            SELECT case_id FROM recovery_cases
            WHERE lane = 'checkout_abandonment' AND failure_reason = ?
            LIMIT 1
            """,
            (failure_reason,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT case_id FROM recovery_cases
            WHERE lane = 'checkout_abandonment'
            ORDER BY case_id
            LIMIT 1
            """
        ).fetchone()
    assert row is not None
    return row["case_id"]


def test_checkout_session_loader(checkout_db):
    conn = checkout_db
    case_id = _checkout_case_id(conn)
    session = load_checkout_session_by_case(conn, case_id)
    assert session is not None
    assert session.case_id == case_id
    assert session.cart_value > 0
    assert session.stage in {"cart", "shipping", "payment_page"}
    assert session.items_count >= 1


def test_checkout_context_includes_session_facts(checkout_db):
    conn = checkout_db
    case_id = _checkout_case_id(conn)
    context = build_recovery_context(conn, case_id)

    assert context.case.lane == Lane.CHECKOUT_ABANDONMENT.value
    assert context.checkout is not None
    assert context.checkout.session_id
    assert context.checkout.cart_value == context.case.amount
    assert context.checkout.stage
    assert context.checkout.hours_since_abandonment >= 0
    assert_no_forbidden_fields(context.to_dict())


def test_hero_checkout_high_intent_signals(checkout_db):
    conn = checkout_db
    context = build_recovery_context(conn, "case_hero_chk_001")

    assert context.checkout is not None
    assert context.checkout.stage == "payment_page"
    assert context.checkout.intent_score == pytest.approx(0.82)
    assert context.derived_signals.high_intent is True
    assert context.derived_signals.payment_stage_abandonment is True
    assert context.derived_signals.high_value_cart is True  # 20000 >= 15000


def test_checkout_payment_page_drop_signal(checkout_db):
    conn = checkout_db
    case_id = _checkout_case_id(conn, "checkout_payment_page_drop")
    context = build_recovery_context(conn, case_id)
    assert context.derived_signals.payment_stage_abandonment is True


def test_checkout_cart_abandon_early_stage(checkout_db):
    conn = checkout_db
    case_id = _checkout_case_id(conn, "checkout_cart_abandon")
    context = build_recovery_context(conn, case_id)
    assert context.derived_signals.early_stage_abandonment is True


def test_subscription_context_has_no_checkout_facts(checkout_db):
    conn = checkout_db
    row = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'subscription_payment'
        LIMIT 1
        """
    ).fetchone()
    context = build_recovery_context(conn, row["case_id"])
    assert context.checkout is None
    assert context.derived_signals.high_intent is False
    assert context.derived_signals.payment_stage_abandonment is False


def test_checkout_context_excludes_ground_truth(checkout_db):
    conn = checkout_db
    case_id = _checkout_case_id(conn)
    context = build_recovery_context(conn, case_id)
    payload = context.to_dict()
    assert "p_pay_anyway" not in str(payload)
    assert FORBIDDEN_CONTEXT_FIELDS.isdisjoint(payload.keys())

    gt = load_ground_truth(conn, case_id)
    assert gt is not None
    assert gt.p_pay_anyway is not None


def test_checkout_context_deterministic(checkout_db):
    conn = checkout_db
    case_id = _checkout_case_id(conn)
    now = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)
    a = ContextBuilder().build(conn, case_id, now=now)
    b = ContextBuilder().build(conn, case_id, now=now)
    assert a.case == b.case
    assert a.checkout == b.checkout
    assert a.derived_signals == b.derived_signals
    assert a.customer == b.customer


def test_checkout_context_does_not_mutate_source(checkout_db):
    conn = checkout_db
    case_id = _checkout_case_id(conn)
    before = conn.execute(
        "SELECT workflow_state, attempt_count FROM recovery_cases WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    build_recovery_context(conn, case_id)
    after = conn.execute(
        "SELECT workflow_state, attempt_count FROM recovery_cases WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    assert before["workflow_state"] == after["workflow_state"]
    assert before["attempt_count"] == after["attempt_count"]


def test_prior_checkout_abandonment_count(checkout_db):
    conn = checkout_db
    # Hero customer has exactly one checkout case among three lanes
    count = count_prior_checkout_abandonments(
        conn, "cust_hero_001", exclude_case_id="case_hero_chk_001"
    )
    assert count == 0
