"""Tests for Phase 4E checkout recovery evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest

from recovery.db import connect
from recovery.evaluation.phase4_metrics import (
    expected_checkout_causes,
    is_checkout_diagnosis_aligned,
)
from recovery.evaluation.phase4_runner import (
    compare_checkout_modes,
    run_phase4_evaluation,
)
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset
from recovery.models.enums import Lane


@pytest.fixture
def checkout_eval_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "phase4_eval.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def test_phase4_evaluation_subset(checkout_eval_db):
    summary = run_phase4_evaluation(checkout_eval_db, intelligence_mode="deterministic", limit=20)
    assert summary.cases_evaluated == 20
    assert summary.lane == Lane.CHECKOUT_ABANDONMENT.value
    assert 0.0 <= summary.recovery_rate <= 1.0
    assert summary.amount_at_risk > 0
    assert summary.diagnosis_alignment_rate > 0.5


def test_checkout_evaluation_includes_ground_truth_evaluator_only(checkout_eval_db):
    summary = run_phase4_evaluation(checkout_eval_db, intelligence_mode="deterministic", limit=5)
    assert all(r.p_pay_anyway is not None for r in summary.records)
    assert all(0.0 <= r.p_pay_anyway <= 1.0 for r in summary.records if r.p_pay_anyway is not None)


def test_checkout_ground_truth_not_in_runtime_modules():
    root = Path(__file__).resolve().parents[1]
    forbidden_import = "from recovery.evaluation.ground_truth"
    runtime_files = [
        root / "src/recovery/intelligence/decisioning.py",
        root / "src/recovery/pipeline/agentic_loop.py",
        root / "src/recovery/pipeline/checkout_runner.py",
        root / "src/recovery/demos/adaptive_checkout.py",
    ]
    for path in runtime_files:
        source = path.read_text(encoding="utf-8")
        assert forbidden_import not in source
        assert "p_pay_anyway" not in source


def test_wrong_lane_rejected_by_phase4(checkout_eval_db):
    with pytest.raises(ValueError, match="checkout_abandonment only"):
        run_phase4_evaluation(
            checkout_eval_db,
            intelligence_mode="deterministic",
            lane=Lane.SUBSCRIPTION_PAYMENT.value,
        )


def test_checkout_diagnosis_alignment_helpers():
    assert "payment_friction" in expected_checkout_causes("checkout_payment_page_drop")
    assert is_checkout_diagnosis_aligned("checkout_cart_abandon", "price_sensitivity")
    assert not is_checkout_diagnosis_aligned("checkout_cart_abandon", "transient_failure")


def test_compare_checkout_modes(checkout_eval_db):
    results = compare_checkout_modes(checkout_eval_db, limit=8)
    assert "deterministic" in results
    assert "hybrid" in results
    assert results["deterministic"].cases_evaluated == 8
    assert results["hybrid"].cases_evaluated == 8
