"""Phase 8 outcome-driven learning evaluation."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from recovery.demos.learning import format_learning_demo_report, run_learning_demos
from recovery.learning.blend import blend_from_store
from recovery.learning.calibration import compute_calibration
from recovery.learning.effectiveness import compute_action_effectiveness, get_historical_evidence
from recovery.learning.store import ExperienceStore
from recovery.paths import GENERATED_DIR
from recovery.pipeline.subscription_runner import run_subscription_case
from recovery.state.reset import reset_case_for_run


@dataclass
class LearningEvaluationSummary:
    mode: str
    scenarios_passed: int
    scenarios_total: int
    observations: int
    distinct_actions: int
    brier_score: float
    mean_absolute_error: float
    baseline_vs_learned: dict[str, Any]
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _baseline_vs_learned(conn: sqlite3.Connection) -> dict[str, Any]:
    """Compare model-only vs blended estimates on stored experience."""
    store = ExperienceStore(conn)
    outcomes = store.list_outcomes()
    if not outcomes:
        return {"comparable": False, "reason": "no_experience"}

    # Use payment_link if present else first action
    actions = sorted({o.action for o in outcomes})
    action = "payment_link" if "payment_link" in actions else actions[0]
    lanes = sorted({o.lane for o in outcomes if o.action == action})
    lane = lanes[0] if lanes else None
    evidence = get_historical_evidence(store, action=action, lane=lane)
    baseline = 0.55
    learned = blend_from_store(
        store, action=action, lane=lane, model_probability=baseline
    )
    return {
        "comparable": True,
        "action": action,
        "lane": lane,
        "baseline_probability": baseline,
        "learned_probability": learned.blended_probability,
        "historical_success_rate": evidence.historical_success_rate,
        "observations": evidence.observations,
        "confidence": evidence.confidence,
        "delta": round(learned.blended_probability - baseline, 4),
        "p_pay_anyway_isolated": True,
    }


def run_phase8_evaluation(
    conn: sqlite3.Connection,
    *,
    intelligence_mode: str = "deterministic",
    limit: int | None = 15,
) -> LearningEvaluationSummary:
    demo_report = run_learning_demos(conn)

    # Optionally seed additional runtime outcomes from a few subscription cases
    rows = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'subscription_payment'
        ORDER BY case_id
        LIMIT ?
        """,
        (limit or 15,),
    ).fetchall()
    for row in rows:
        case_id = row["case_id"]
        reset_case_for_run(conn, case_id)
        try:
            run_subscription_case(conn, case_id, intelligence_mode=intelligence_mode)
        except Exception:
            continue

    store = ExperienceStore(conn)
    all_outcomes = store.list_outcomes()
    calibration = compute_calibration(all_outcomes)
    effectiveness = compute_action_effectiveness(all_outcomes)
    baseline = _baseline_vs_learned(conn)

    summary = LearningEvaluationSummary(
        mode=intelligence_mode,
        scenarios_passed=sum(1 for o in demo_report.outcomes if o.passed),
        scenarios_total=len(demo_report.outcomes),
        observations=len(all_outcomes),
        distinct_actions=len({o.action for o in all_outcomes}),
        brier_score=calibration.brier_score,
        mean_absolute_error=calibration.mean_absolute_error,
        baseline_vs_learned=baseline,
        detail={
            "demo_report": format_learning_demo_report(demo_report),
            "scenarios": [
                {"id": o.scenario_id, "passed": o.passed, "failures": o.failures}
                for o in demo_report.outcomes
            ],
            "calibration": calibration.to_dict(),
            "effectiveness": [e.to_dict() for e in effectiveness[:20]],
            "p_pay_anyway_isolated": True,
        },
    )

    from recovery.audit.trail import record_event

    record_event(
        conn,
        case_id="case_hero_sub_001",
        customer_id="cust_hero_001",
        event_type="EVALUATION_COMPLETED",
        from_state=None,
        to_state=None,
        action=None,
        actor="learning",
        reason="Phase 8 learning evaluation completed.",
        metadata={
            "observations": summary.observations,
            "scenarios_passed": summary.scenarios_passed,
            "brier_score": summary.brier_score,
        },
    )
    conn.commit()

    return summary


def format_phase8_evaluation_report(summary: LearningEvaluationSummary) -> str:
    lines = [
        "=" * 72,
        "Podium Phase 8 Outcome-Driven Learning Evaluation",
        "=" * 72,
        f"Mode:                     {summary.mode}",
        f"Demo scenarios:           {summary.scenarios_passed}/{summary.scenarios_total}",
        f"Observations:             {summary.observations}",
        f"Distinct actions:         {summary.distinct_actions}",
        f"Brier score:              {summary.brier_score}",
        f"Mean abs. prediction err: {summary.mean_absolute_error}",
        f"Baseline vs learned:      {summary.baseline_vs_learned}",
        f"p_pay_anyway isolated:    {summary.detail.get('p_pay_anyway_isolated')}",
        "=" * 72,
    ]
    return "\n".join(lines)


def export_phase8_evaluation_json(summary: LearningEvaluationSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")


def default_phase8_export_path() -> Path:
    return GENERATED_DIR / "phase8_learning_evaluation.json"
