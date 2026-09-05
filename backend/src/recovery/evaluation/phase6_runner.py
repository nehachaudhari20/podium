"""Phase 6 cross-revenue coordination evaluation."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from recovery.demos.coordination import prepare_customer_cases, run_coordination_demos
from recovery.coordination.runner import plan_customer_recovery
from recovery.ingestion.synthetic.hero_scenario import HERO_CUSTOMER_ID
from recovery.paths import GENERATED_DIR


@dataclass
class CoordinationEvaluationSummary:
    mode: str
    scenarios_passed: int
    scenarios_total: int
    independent_actions: int
    coordinated_actions: int
    contacts_deferred: int
    cases_deferred: int
    total_amount_at_risk: float
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_phase6_evaluation(conn: sqlite3.Connection) -> CoordinationEvaluationSummary:
    demo_report = run_coordination_demos(conn)
    prepare_customer_cases(conn, HERO_CUSTOMER_ID, clear_contacts=True)
    view, _, coordinated = plan_customer_recovery(conn, HERO_CUSTOMER_ID, coordinated=True)
    _, _, independent = plan_customer_recovery(
        conn, HERO_CUSTOMER_ID, coordinated=False, audit=False
    )
    return CoordinationEvaluationSummary(
        mode="deterministic",
        scenarios_passed=sum(1 for o in demo_report.outcomes if o.passed),
        scenarios_total=len(demo_report.outcomes),
        independent_actions=len(independent.selected_actions),
        coordinated_actions=len(coordinated.selected_actions),
        contacts_deferred=sum(
            1
            for a in coordinated.deferred_actions
            if "contact" in a.reason or "collision" in a.reason or "fatigue" in a.reason
        ),
        cases_deferred=len(coordinated.deferred_actions),
        total_amount_at_risk=view.total_amount_at_risk,
        detail={
            "coordinated": coordinated.to_dict(),
            "independent": independent.to_dict(),
            "scenarios": [
                {"id": o.scenario_id, "passed": o.passed, "failures": o.failures}
                for o in demo_report.outcomes
            ],
        },
    )


def format_phase6_evaluation_report(summary: CoordinationEvaluationSummary) -> str:
    lines = [
        "=" * 72,
        "Podium Phase 6 Cross-Revenue Coordination Evaluation",
        "=" * 72,
        f"Scenarios passed:         {summary.scenarios_passed}/{summary.scenarios_total}",
        f"Independent actions:      {summary.independent_actions}",
        f"Coordinated actions:      {summary.coordinated_actions}",
        f"Cases deferred:           {summary.cases_deferred}",
        f"Contact-related deferred: {summary.contacts_deferred}",
        f"Total amount at risk:     INR {summary.total_amount_at_risk:,.2f}",
        "=" * 72,
    ]
    return "\n".join(lines)


def export_phase6_evaluation_json(summary: CoordinationEvaluationSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")


def default_phase6_export_path() -> Path:
    return GENERATED_DIR / "phase6_coordination_evaluation.json"
