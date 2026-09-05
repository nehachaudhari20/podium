"""Phase 5 evaluation — demonstrate economics changes decisions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from recovery.audit.trail import load_audit_trail
from recovery.demos.adaptive import prepare_demo_case
from recovery.demos.economic import format_economic_demo_report, run_economic_demos
from recovery.evaluation.phase3_metrics import CaseEvaluationRecord
from recovery.evaluation.phase5_metrics import (
    CHEAP_ACTIONS,
    EXPENSIVE_ACTIONS,
    EconomicEvaluationSummary,
    format_economic_evaluation_report,
)
from recovery.models.enums import Lane
from recovery.paths import GENERATED_DIR
from recovery.pipeline.subscription_runner import run_subscription_case


def run_phase5_demo_evaluation() -> EconomicEvaluationSummary:
    """Run deterministic economic scenarios and summarize pass/fail."""
    report = run_economic_demos()
    return EconomicEvaluationSummary(
        intelligence_mode="deterministic",
        cases_evaluated=len(report.outcomes),
        recovery_rate=sum(1 for o in report.outcomes if o.passed) / max(1, len(report.outcomes)),
        avg_expected_net_value=None,
        cheap_action_share=0.0,
        expensive_action_share=0.0,
        economic_audit_rate=1.0 if report.passed else 0.0,
        records=[],
        extra={
            "demo_passed": report.passed,
            "outcomes": [
                {"id": o.scenario_id, "passed": o.passed, "failures": o.failures}
                for o in report.outcomes
            ],
            "report": format_economic_demo_report(report),
        },
    )


def run_phase5_pipeline_evaluation(
    conn: sqlite3.Connection,
    *,
    intelligence_mode: str = "deterministic",
    limit: int | None = 30,
) -> EconomicEvaluationSummary:
    """Evaluate subscription cases for economic audit coverage and action mix."""
    query = """
        SELECT case_id FROM recovery_cases
        WHERE lane = ?
        ORDER BY case_id
    """
    params: list[object] = [Lane.SUBSCRIPTION_PAYMENT.value]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    case_ids = [row["case_id"] for row in conn.execute(query, params).fetchall()]

    records: list[CaseEvaluationRecord] = []
    cheap = 0
    expensive = 0
    with_econ_audit = 0
    env_values: list[float] = []

    for case_id in case_ids:
        prepare_demo_case(conn, case_id)
        result = run_subscription_case(conn, case_id, intelligence_mode=intelligence_mode)
        events = load_audit_trail(conn, case_id)
        if any(e.event_type == "ECONOMIC_EVALUATION" for e in events):
            with_econ_audit += 1
        selected = result.selected_action.action_id if result.selected_action else ""
        if selected in CHEAP_ACTIONS:
            cheap += 1
        if selected in EXPENSIVE_ACTIONS:
            expensive += 1
        if result.expected_net_value is not None:
            env_values.append(result.expected_net_value)

        records.append(
            CaseEvaluationRecord(
                case_id=case_id,
                lane=result.lane,
                failure_reason=None,
                amount=result.amount,
                currency=result.currency,
                recovered=result.recovered,
                amount_recovered=result.amount_recovered,
                terminal_state=result.terminal_state,
                diagnosis_cause=result.diagnosis.likely_cause,
                decision_source=result.decision_source,
                agent_steps=result.agent_steps,
                replan_count=result.replan_count,
                diagnosis_aligned=True,
                p_pay_anyway=None,
            )
        )

    n = len(records) or 1
    recovered = sum(1 for r in records if r.recovered)
    return EconomicEvaluationSummary(
        intelligence_mode=intelligence_mode,
        cases_evaluated=len(records),
        recovery_rate=recovered / n,
        avg_expected_net_value=(sum(env_values) / len(env_values)) if env_values else None,
        cheap_action_share=cheap / n,
        expensive_action_share=expensive / n,
        economic_audit_rate=with_econ_audit / n,
        records=records,
    )


def export_phase5_evaluation_json(summary: EconomicEvaluationSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")


def default_phase5_export_path(label: str = "demos") -> Path:
    return GENERATED_DIR / f"phase5_economic_evaluation_{label}.json"
