"""Tests for Phase 3G intelligence evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest

from recovery.db import connect
from recovery.evaluation.ground_truth import load_ground_truth
from recovery.evaluation.phase3_metrics import summarize_records, CaseEvaluationRecord
from recovery.evaluation.phase3_runner import run_phase3_evaluation
from recovery.ingestion.synthetic.generator import SyntheticDataGenerator, persist_dataset


@pytest.fixture
def eval_db(tmp_path: Path):
    dataset = SyntheticDataGenerator(seed=42).generate()
    db_path = tmp_path / "phase3_eval.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    conn = connect(db_path)
    yield conn
    conn.close()


def test_phase3_evaluation_subset(eval_db):
    summary = run_phase3_evaluation(eval_db, intelligence_mode="deterministic", limit=20)
    assert summary.cases_evaluated == 20
    assert 0.0 <= summary.recovery_rate <= 1.0
    assert summary.amount_at_risk > 0
    assert summary.diagnosis_alignment_rate > 0.5


def test_evaluation_includes_ground_truth_evaluator_only(eval_db):
    summary = run_phase3_evaluation(eval_db, intelligence_mode="deterministic", limit=5)
    assert all(r.p_pay_anyway is not None for r in summary.records)
    assert all(0.0 <= r.p_pay_anyway <= 1.0 for r in summary.records if r.p_pay_anyway is not None)


def test_ground_truth_not_in_runtime_modules():
    root = Path(__file__).resolve().parents[1]
    forbidden_import = "from recovery.evaluation.ground_truth"
    runtime_files = [
        root / "src/recovery/intelligence/decisioning.py",
        root / "src/recovery/pipeline/agentic_loop.py",
        root / "src/recovery/pipeline/subscription_runner.py",
    ]
    for path in runtime_files:
        source = path.read_text(encoding="utf-8")
        assert forbidden_import not in source
        assert "p_pay_anyway" not in source


def test_summarize_records_empty():
    summary = summarize_records([], intelligence_mode="deterministic", lane="subscription_payment")
    assert summary.cases_evaluated == 0
    assert summary.recovery_rate == 0.0


def test_compare_modes(eval_db):
    from recovery.evaluation.phase3_runner import compare_modes

    results = compare_modes(eval_db, limit=10)
    assert "deterministic" in results
    assert "hybrid" in results
    assert results["deterministic"].cases_evaluated == 10
