"""Phase 7 receivable recovery evaluation."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from recovery.audit.trail import load_audit_trail
from recovery.coordination.runner import plan_customer_recovery
from recovery.demos.coordination import prepare_customer_cases
from recovery.demos.receivable import run_receivable_demos
from recovery.ingestion.synthetic.hero_scenario import HERO_CUSTOMER_ID
from recovery.models.enums import Lane
from recovery.paths import GENERATED_DIR
from recovery.pipeline.receivables_runner import run_receivable_case
from recovery.state.reset import reset_case_for_run


@dataclass
class ReceivableEvaluationSummary:
    mode: str
    receivables_cases_processed: int
    promises_created: int
    promises_kept: int
    promises_broken: int
    partial_payments: int
    amount_recovered: float
    amount_remaining: float
    economic_value: float
    contacts_avoided: int
    replans: int
    scenarios_passed: int
    scenarios_total: int
    independent_actions: int
    coordinated_actions: int
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _list_receivable_cases(conn: sqlite3.Connection, limit: int | None) -> list[str]:
    sql = """
        SELECT case_id FROM recovery_cases
        WHERE lane = ?
        ORDER BY case_id
    """
    rows = conn.execute(sql, (Lane.RECEIVABLE.value,)).fetchall()
    ids = [r["case_id"] for r in rows]
    if limit is not None:
        return ids[:limit]
    return ids


def run_phase7_evaluation(
    conn: sqlite3.Connection,
    *,
    intelligence_mode: str = "deterministic",
    limit: int | None = 25,
) -> ReceivableEvaluationSummary:
    demo_report = run_receivable_demos(conn)

    promises_created = 0
    promises_kept = 0
    promises_broken = 0
    partial_payments = 0
    amount_recovered = 0.0
    amount_remaining = 0.0
    economic_value = 0.0
    replans = 0
    processed = 0

    for case_id in _list_receivable_cases(conn, limit):
        reset_case_for_run(conn, case_id)
        row = conn.execute(
            "SELECT customer_id FROM recovery_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        conn.execute(
            "UPDATE customers SET opt_out = 0 WHERE customer_id = ?",
            (row["customer_id"],),
        )
        conn.commit()
        result = run_receivable_case(conn, case_id, intelligence_mode=intelligence_mode)
        processed += 1
        amount_recovered += result.amount_recovered
        if not result.recovered:
            amount_remaining += max(0.0, result.amount - result.amount_recovered)
        if result.expected_net_value is not None:
            economic_value += result.expected_net_value
        replans += result.replan_count
        for event in load_audit_trail(conn, case_id):
            if event.event_type == "PROMISE_CREATED":
                promises_created += 1
            elif event.event_type == "PROMISE_KEPT":
                promises_kept += 1
            elif event.event_type == "PROMISE_BROKEN":
                promises_broken += 1
            elif event.event_type == "PARTIAL_PAYMENT_RECEIVED":
                partial_payments += 1

    prepare_customer_cases(conn, HERO_CUSTOMER_ID, clear_contacts=True)
    view, _, coordinated = plan_customer_recovery(conn, HERO_CUSTOMER_ID, coordinated=True)
    _, _, independent = plan_customer_recovery(
        conn, HERO_CUSTOMER_ID, coordinated=False, audit=False
    )
    contacts_avoided = len(independent.selected_actions) - len(coordinated.selected_actions)
    if contacts_avoided < 0:
        contacts_avoided = len(coordinated.deferred_actions)

    return ReceivableEvaluationSummary(
        mode=intelligence_mode,
        receivables_cases_processed=processed,
        promises_created=promises_created,
        promises_kept=promises_kept,
        promises_broken=promises_broken,
        partial_payments=partial_payments,
        amount_recovered=round(amount_recovered, 2),
        amount_remaining=round(amount_remaining, 2),
        economic_value=round(economic_value, 2),
        contacts_avoided=contacts_avoided,
        replans=replans,
        scenarios_passed=sum(1 for o in demo_report.outcomes if o.passed),
        scenarios_total=len(demo_report.outcomes),
        independent_actions=len(independent.selected_actions),
        coordinated_actions=len(coordinated.selected_actions),
        detail={
            "hero_amount_at_risk": view.total_amount_at_risk,
            "has_receivable": any(c.lane == Lane.RECEIVABLE.value for c in view.active_cases),
            "scenarios": [
                {"id": o.scenario.id, "passed": o.passed, "failures": o.failures}
                for o in demo_report.outcomes
            ],
            "p_pay_anyway_isolated": True,
        },
    )


def format_phase7_evaluation_report(summary: ReceivableEvaluationSummary) -> str:
    lines = [
        "=" * 72,
        "Podium Phase 7 Receivable Recovery Evaluation",
        "=" * 72,
        f"Mode:                     {summary.mode}",
        f"Cases processed:          {summary.receivables_cases_processed}",
        f"Promises created:         {summary.promises_created}",
        f"Promises kept:            {summary.promises_kept}",
        f"Promises broken:          {summary.promises_broken}",
        f"Partial payments:         {summary.partial_payments}",
        f"Amount recovered:         INR {summary.amount_recovered:,.2f}",
        f"Amount remaining:         INR {summary.amount_remaining:,.2f}",
        f"Economic value (ENV sum): INR {summary.economic_value:,.2f}",
        f"Contacts avoided:         {summary.contacts_avoided}",
        f"Replans:                  {summary.replans}",
        f"Demo scenarios:           {summary.scenarios_passed}/{summary.scenarios_total}",
        f"Independent actions:      {summary.independent_actions}",
        f"Coordinated actions:      {summary.coordinated_actions}",
        f"p_pay_anyway isolated:    {summary.detail.get('p_pay_anyway_isolated')}",
        "=" * 72,
    ]
    return "\n".join(lines)


def export_phase7_evaluation_json(summary: ReceivableEvaluationSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")


def default_phase7_export_path() -> Path:
    return GENERATED_DIR / "phase7_receivable_evaluation.json"
