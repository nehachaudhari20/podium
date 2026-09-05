"""Phase 4 batch evaluation runner — checkout abandonment lane (Phase 4E)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from recovery.demos.adaptive import prepare_demo_case
from recovery.evaluation.ground_truth import load_ground_truth
from recovery.evaluation.phase3_metrics import CaseEvaluationRecord, Phase3EvaluationSummary, summarize_records
from recovery.evaluation.phase4_metrics import format_checkout_evaluation_report, is_checkout_diagnosis_aligned
from recovery.models.enums import Lane
from recovery.paths import GENERATED_DIR
from recovery.pipeline.checkout_runner import run_checkout_case


def list_checkout_case_ids(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
) -> list[str]:
    query = """
        SELECT case_id FROM recovery_cases
        WHERE lane = ?
        ORDER BY case_id
    """
    params: list[object] = [Lane.CHECKOUT_ABANDONMENT.value]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [row["case_id"] for row in rows]


def evaluate_checkout_case(
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
    if row["lane"] != Lane.CHECKOUT_ABANDONMENT.value:
        raise ValueError(
            f"evaluate_checkout_case supports checkout_abandonment only, got {row['lane']}"
        )

    prepare_demo_case(conn, case_id)
    result = run_checkout_case(conn, case_id, intelligence_mode=intelligence_mode)

    gt = load_ground_truth(conn, case_id)
    aligned = is_checkout_diagnosis_aligned(row["failure_reason"], result.diagnosis.likely_cause)

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


def run_phase4_evaluation(
    conn: sqlite3.Connection,
    *,
    intelligence_mode: str = "deterministic",
    limit: int | None = None,
    lane: str = Lane.CHECKOUT_ABANDONMENT.value,
) -> Phase3EvaluationSummary:
    if lane != Lane.CHECKOUT_ABANDONMENT.value:
        raise ValueError(f"Phase 4E evaluation supports checkout_abandonment only, got {lane}")

    case_ids = list_checkout_case_ids(conn, limit=limit)
    records = [
        evaluate_checkout_case(conn, case_id, intelligence_mode=intelligence_mode)
        for case_id in case_ids
    ]
    return summarize_records(records, intelligence_mode=intelligence_mode, lane=lane)


def compare_checkout_modes(
    conn: sqlite3.Connection,
    modes: tuple[str, ...] = ("deterministic", "hybrid"),
    *,
    limit: int | None = None,
) -> dict[str, Phase3EvaluationSummary]:
    return {
        mode: run_phase4_evaluation(conn, intelligence_mode=mode, limit=limit)
        for mode in modes
    }


def export_checkout_evaluation_json(summary: Phase3EvaluationSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")


def default_checkout_export_path(mode: str) -> Path:
    return GENERATED_DIR / f"phase4_checkout_evaluation_{mode}.json"


# Re-export report formatter for CLI convenience
format_evaluation_report = format_checkout_evaluation_report
