"""Phase 3 batch evaluation runner — subscription lane (Phase 3G)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from recovery.demos.adaptive import prepare_demo_case
from recovery.evaluation.ground_truth import load_ground_truth
from recovery.evaluation.phase3_metrics import (
    CaseEvaluationRecord,
    Phase3EvaluationSummary,
    expected_cause_for_failure,
    format_evaluation_report,
    summarize_records,
)
from recovery.models.enums import Lane
from recovery.pipeline.subscription_runner import run_subscription_case
from recovery.paths import GENERATED_DIR


def list_subscription_case_ids(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
) -> list[str]:
    query = """
        SELECT case_id FROM recovery_cases
        WHERE lane = ?
        ORDER BY case_id
    """
    params: list[object] = [Lane.SUBSCRIPTION_PAYMENT.value]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [row["case_id"] for row in rows]


def evaluate_case(
    conn: sqlite3.Connection,
    case_id: str,
    *,
    intelligence_mode: str,
) -> CaseEvaluationRecord:
    row = conn.execute(
        """
        SELECT case_id, lane, failure_reason, amount, currency
        FROM recovery_cases WHERE case_id = ?
        """,
        (case_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Case not found: {case_id}")

    prepare_demo_case(conn, case_id)
    result = run_subscription_case(conn, case_id, intelligence_mode=intelligence_mode)

    gt = load_ground_truth(conn, case_id)
    expected = expected_cause_for_failure(row["failure_reason"])
    aligned = expected is not None and result.diagnosis.likely_cause == expected

    return CaseEvaluationRecord(
        case_id=case_id,
        lane=row["lane"],
        failure_reason=row["failure_reason"],
        amount=float(row["amount"]),
        currency=row["currency"],
        recovered=result.recovered,
        amount_recovered=result.amount_recovered,
        terminal_state=result.terminal_state,
        diagnosis_cause=result.diagnosis.likely_cause,
        decision_source=result.decision_source,
        agent_steps=result.agent_steps,
        replan_count=result.replan_count,
        diagnosis_aligned=aligned,
        p_pay_anyway=gt.p_pay_anyway if gt else None,
    )


def run_phase3_evaluation(
    conn: sqlite3.Connection,
    *,
    intelligence_mode: str = "deterministic",
    limit: int | None = None,
    lane: str = Lane.SUBSCRIPTION_PAYMENT.value,
) -> Phase3EvaluationSummary:
    if lane != Lane.SUBSCRIPTION_PAYMENT.value:
        raise ValueError(f"Phase 3G evaluation supports subscription_payment only, got {lane}")

    case_ids = list_subscription_case_ids(conn, limit=limit)
    records = [
        evaluate_case(conn, case_id, intelligence_mode=intelligence_mode)
        for case_id in case_ids
    ]
    return summarize_records(records, intelligence_mode=intelligence_mode, lane=lane)


def compare_modes(
    conn: sqlite3.Connection,
    modes: tuple[str, ...] = ("deterministic", "hybrid"),
    *,
    limit: int | None = None,
) -> dict[str, Phase3EvaluationSummary]:
    return {
        mode: run_phase3_evaluation(conn, intelligence_mode=mode, limit=limit)
        for mode in modes
    }


def export_evaluation_json(summary: Phase3EvaluationSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")


def default_export_path(mode: str) -> Path:
    return GENERATED_DIR / f"phase3_evaluation_{mode}.json"
