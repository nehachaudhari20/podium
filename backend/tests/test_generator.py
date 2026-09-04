"""Phase 1 synthetic data generator tests."""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from recovery.db import connect, init_schema
from recovery.evaluation.ground_truth import load_all_ground_truth
from recovery.ingestion.runtime_loader import load_open_cases
from recovery.ingestion.synthetic.generator import (
    LANE_TARGETS,
    SyntheticDataGenerator,
    build_summary,
    persist_dataset,
)
from recovery.ingestion.synthetic.hero_scenario import HERO_CUSTOMER_ID
from recovery.models.case import RUNTIME_CASE_COLUMNS


@pytest.fixture
def dataset():
    return SyntheticDataGenerator(seed=42).generate()


@pytest.fixture
def temp_db(tmp_path: Path, dataset):
    db_path = tmp_path / "test_podium.db"
    persist_dataset(dataset, db_path=db_path, export_json=False)
    return db_path, dataset


def test_lane_targets_met(dataset):
    counts = dataset.lane_counts()
    for lane, target in LANE_TARGETS.items():
        assert counts[lane] == target


def test_total_cases_in_range(dataset):
    assert 250 <= dataset.case_count <= 300


def test_multi_case_customers(dataset):
    by_customer = Counter(c["customer_id"] for c in dataset.cases)
    multi = sum(1 for _cid, count in by_customer.items() if count >= 2)
    assert multi >= 15
    assert by_customer[HERO_CUSTOMER_ID] == 3


def test_hero_scenario_present(dataset):
    hero_cases = [c for c in dataset.cases if c.get("is_hero")]
    assert len(hero_cases) == 3
    lanes = {c["lane"] for c in hero_cases}
    assert lanes == {"subscription_payment", "checkout_abandonment", "receivable"}
    amounts = sorted(c["amount"] for c in hero_cases)
    assert amounts == [5000.0, 20000.0, 80000.0]


def test_ground_truth_complete_and_valid(dataset):
    assert len(dataset.ground_truth) == len(dataset.cases)
    for row in dataset.ground_truth:
        assert 0.0 <= row["p_pay_anyway"] <= 1.0
        assert "failure_reason" in row["feature_snapshot"]


def test_p_pay_anyway_correlated_with_failure_type(dataset):
    by_reason: dict[str, list[float]] = defaultdict(list)
    gt = {g["case_id"]: g["p_pay_anyway"] for g in dataset.ground_truth}
    for case in dataset.cases:
        reason = case["failure_reason"]
        if reason:
            by_reason[reason].append(gt[case["case_id"]])

    assert by_reason["transient_technical"]
    assert by_reason["expired_card"]
    assert (
        sum(by_reason["transient_technical"]) / len(by_reason["transient_technical"])
        > sum(by_reason["expired_card"]) / len(by_reason["expired_card"])
    )
    assert (
        sum(by_reason["invoice_severely_overdue"]) / len(by_reason["invoice_severely_overdue"])
        < sum(by_reason["invoice_mild_overdue"]) / len(by_reason["invoice_mild_overdue"])
    )


def test_runtime_loader_excludes_ground_truth(temp_db):
    db_path, dataset = temp_db
    conn = connect(db_path)
    cases = load_open_cases(conn)

    assert len(cases) == len(dataset.cases)
    assert "p_pay_anyway" not in RUNTIME_CASE_COLUMNS

    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(recovery_cases)").fetchall()
    }
    assert "p_pay_anyway" not in columns

    conn.close()


def test_ground_truth_only_in_evaluator_table(temp_db):
    db_path, _ = temp_db
    conn = connect(db_path)
    truths = load_all_ground_truth(conn)
    assert len(truths) == 300
    conn.close()


def test_schema_and_budget_persisted(temp_db):
    db_path, _ = temp_db
    conn = connect(db_path)
    row = conn.execute("SELECT * FROM merchant_budgets WHERE budget_id = 1").fetchone()
    assert row is not None
    assert row["contact_capacity_per_day"] == 50
    conn.close()


def test_reproducible_generation():
    d1 = SyntheticDataGenerator(seed=99).generate()
    d2 = SyntheticDataGenerator(seed=99).generate()
    assert [c["case_id"] for c in d1.cases] == [c["case_id"] for c in d2.cases]
    assert [g["p_pay_anyway"] for g in d1.ground_truth] == [
        g["p_pay_anyway"] for g in d2.ground_truth
    ]


def test_build_summary_keys(dataset):
    summary = build_summary(dataset)
    assert summary["total_cases"] == 300
    assert summary["multi_case_customers"] >= 18
    assert "p_pay_anyway" in summary
