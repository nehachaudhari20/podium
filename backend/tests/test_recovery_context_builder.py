"""Tests for Phase 3A context builder."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from recovery.db import connect
from recovery.evaluation.ground_truth import load_ground_truth
from recovery.ingestion.runtime_loader import load_case_by_id
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
from recovery.intelligence.context_builder import ContextBuilder, build_recovery_context
from recovery.models.recovery_context import FORBIDDEN_CONTEXT_FIELDS, assert_no_forbidden_fields
from recovery.pipeline.subscription_runner import run_subscription_case
from recovery.state.context import CaseRunContext
from recovery.state.reset import reset_case_for_run


@pytest.fixture
def ctx_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "context_builder.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def _subscription_case_id(conn, failure_reason: str) -> str:
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


def test_basic_context_construction(ctx_db):
    conn = ctx_db
    case_id = _subscription_case_id(conn, "insufficient_funds")
    context = build_recovery_context(conn, case_id)

    assert context.case.case_id == case_id
    assert context.case.lane == "subscription_payment"
    assert context.customer.customer_id == context.case.customer_id
    assert context.schema_version == "3a.1"
    assert_no_forbidden_fields(context.to_dict())


def test_history_represented_after_run(ctx_db):
    conn = ctx_db
    case_id = _subscription_case_id(conn, "network_timeout")
    reset_case_for_run(conn, case_id)
    run_subscription_case(conn, case_id, intelligence_mode="deterministic")

    context = build_recovery_context(conn, case_id)
    assert len(context.recovery_history) >= 3
    event_types = {e.event_type for e in context.recovery_history}
    assert "DIAGNOSED" in event_types
    assert "ACTION_EXECUTED" in event_types


def test_derived_signals_repeated_failure(ctx_db):
    conn = ctx_db
    case_id = _subscription_case_id(conn, "repeated_failure")
    context = build_recovery_context(conn, case_id)

    assert context.derived_signals.repeated_failure is True
    assert context.derived_signals.first_failure is False


def test_derived_signals_first_failure(ctx_db):
    conn = ctx_db
    case_id = _subscription_case_id(conn, "transient_technical")
    reset_case_for_run(conn, case_id)
    context = build_recovery_context(conn, case_id)

    assert context.derived_signals.first_failure is True
    assert context.derived_signals.transient_failure is True


def test_build_does_not_mutate_source_state(ctx_db):
    conn = ctx_db
    case_id = _subscription_case_id(conn, "issuer_timeout")
    before = load_case_by_id(conn, case_id)
    assert before is not None
    before_snapshot = copy.deepcopy(before)

    builder = ContextBuilder()
    context = builder.build(conn, case_id)

    after = load_case_by_id(conn, case_id)
    assert after == before_snapshot
    assert context.case.case_id == case_id


def test_build_with_run_context_reflects_memory(ctx_db):
    conn = ctx_db
    case = load_case_by_id(conn, _subscription_case_id(conn, "expired_card"))
    assert case is not None
    run_ctx = CaseRunContext(case=case)
    run_ctx.attempt_count = 2
    run_ctx.last_action = "payment_method_update"
    run_ctx.payment_method_updated = True
    run_ctx.record_state("waiting")

    context = ContextBuilder().build(conn, case.case_id, run_context=run_ctx)

    assert context.case.attempt_count == 2
    assert context.case.last_action == "payment_method_update"
    assert context.case.payment_method_updated is True
    assert context.case.workflow_state == "waiting"
    assert run_ctx.attempt_count == 2


def test_evaluator_ground_truth_not_in_context(ctx_db):
    conn = ctx_db
    case_id = _subscription_case_id(conn, "insufficient_funds")
    context = build_recovery_context(conn, case_id)
    serialized = str(context.to_dict())

    assert "p_pay_anyway" not in serialized
    assert "case_ground_truth" not in serialized
    for forbidden in FORBIDDEN_CONTEXT_FIELDS:
        assert forbidden not in context.to_dict()

    gt = load_ground_truth(conn, case_id)
    assert gt is not None
    assert gt.p_pay_anyway > 0


def test_deterministic_output(ctx_db):
    conn = ctx_db
    case_id = _subscription_case_id(conn, "mandate_revoked")
    fixed_now = datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc)

    ctx1 = ContextBuilder().build(conn, case_id, now=fixed_now)
    ctx2 = ContextBuilder().build(conn, case_id, now=fixed_now)

    d1 = ctx1.to_dict()
    d2 = ctx2.to_dict()
    d1.pop("built_at")
    d2.pop("built_at")
    assert d1 == d2
