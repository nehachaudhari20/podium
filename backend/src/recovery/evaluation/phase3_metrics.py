"""Phase 3 intelligence evaluation metrics (evaluator-only ground truth)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from recovery.intelligence.diagnosis import FAILURE_TO_CAUSE


def expected_cause_for_failure(failure_reason: str | None) -> str | None:
    if not failure_reason:
        return None
    entry = FAILURE_TO_CAUSE.get(failure_reason)
    return entry[0] if entry else None


@dataclass(frozen=True, slots=True)
class CaseEvaluationRecord:
    """Per-case evaluation outcome — may include evaluator-only fields."""

    case_id: str
    lane: str
    failure_reason: str | None
    amount: float
    currency: str
    recovered: bool
    amount_recovered: float
    terminal_state: str
    diagnosis_cause: str
    decision_source: str
    agent_steps: int
    replan_count: int
    diagnosis_aligned: bool
    p_pay_anyway: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Phase3EvaluationSummary:
    """Aggregate Phase 3 evaluation metrics."""

    intelligence_mode: str
    lane: str
    cases_evaluated: int
    recovery_rate: float
    amount_at_risk: float
    amount_recovered: float
    recovery_yield: float
    avg_agent_steps: float
    avg_replan_count: float
    diagnosis_alignment_rate: float
    avg_p_pay_anyway_recovered: float | None
    avg_p_pay_anyway_not_recovered: float | None
    records: list[CaseEvaluationRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["records"] = [r.to_dict() for r in self.records]
        return payload


def summarize_records(
    records: list[CaseEvaluationRecord],
    *,
    intelligence_mode: str,
    lane: str,
) -> Phase3EvaluationSummary:
    if not records:
        return Phase3EvaluationSummary(
            intelligence_mode=intelligence_mode,
            lane=lane,
            cases_evaluated=0,
            recovery_rate=0.0,
            amount_at_risk=0.0,
            amount_recovered=0.0,
            recovery_yield=0.0,
            avg_agent_steps=0.0,
            avg_replan_count=0.0,
            diagnosis_alignment_rate=0.0,
            avg_p_pay_anyway_recovered=None,
            avg_p_pay_anyway_not_recovered=None,
            records=[],
        )

    recovered = [r for r in records if r.recovered]
    not_recovered = [r for r in records if not r.recovered]
    amount_at_risk = sum(r.amount for r in records)
    amount_recovered = sum(r.amount_recovered for r in records)

    def _avg_payanyway(items: list[CaseEvaluationRecord]) -> float | None:
        values = [r.p_pay_anyway for r in items if r.p_pay_anyway is not None]
        return sum(values) / len(values) if values else None

    aligned = sum(1 for r in records if r.diagnosis_aligned)

    return Phase3EvaluationSummary(
        intelligence_mode=intelligence_mode,
        lane=lane,
        cases_evaluated=len(records),
        recovery_rate=len(recovered) / len(records),
        amount_at_risk=amount_at_risk,
        amount_recovered=amount_recovered,
        recovery_yield=amount_recovered / amount_at_risk if amount_at_risk else 0.0,
        avg_agent_steps=sum(r.agent_steps for r in records) / len(records),
        avg_replan_count=sum(r.replan_count for r in records) / len(records),
        diagnosis_alignment_rate=aligned / len(records),
        avg_p_pay_anyway_recovered=_avg_payanyway(recovered),
        avg_p_pay_anyway_not_recovered=_avg_payanyway(not_recovered),
        records=records,
    )


def format_evaluation_report(summary: Phase3EvaluationSummary) -> str:
    lines = [
        "=" * 72,
        "Podium Phase 3 Intelligence Evaluation (3G)",
        f"Mode: {summary.intelligence_mode}  Lane: {summary.lane}",
        "=" * 72,
        f"Cases evaluated:          {summary.cases_evaluated}",
        f"Recovery rate:            {summary.recovery_rate:.1%}",
        f"Amount at risk:           INR {summary.amount_at_risk:,.2f}",
        f"Amount recovered:         INR {summary.amount_recovered:,.2f}",
        f"Recovery yield:           {summary.recovery_yield:.1%}",
        f"Avg agent steps:          {summary.avg_agent_steps:.2f}",
        f"Avg replans:              {summary.avg_replan_count:.2f}",
        f"Diagnosis alignment:      {summary.diagnosis_alignment_rate:.1%}",
    ]
    if summary.avg_p_pay_anyway_recovered is not None:
        lines.append(
            f"Avg p_pay_anyway (recovered):     {summary.avg_p_pay_anyway_recovered:.3f}  [evaluator-only]"
        )
    if summary.avg_p_pay_anyway_not_recovered is not None:
        lines.append(
            f"Avg p_pay_anyway (not recovered): {summary.avg_p_pay_anyway_not_recovered:.3f}  [evaluator-only]"
        )
    lines.append("=" * 72)
    return "\n".join(lines)
