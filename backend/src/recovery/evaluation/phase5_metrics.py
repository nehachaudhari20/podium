"""Phase 5 economic evaluation metrics and helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from recovery.evaluation.phase3_metrics import CaseEvaluationRecord


@dataclass
class EconomicEvaluationSummary:
    intelligence_mode: str
    cases_evaluated: int
    recovery_rate: float
    avg_expected_net_value: float | None
    cheap_action_share: float
    expensive_action_share: float
    economic_audit_rate: float
    records: list[CaseEvaluationRecord] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["records"] = [r.to_dict() for r in self.records]
        return payload


CHEAP_ACTIONS = frozenset(
    {
        "retry_6h",
        "retry_24h",
        "retry_72h",
        "retry_after_update",
        "retry_payment",
        "checkout_reminder",
        "payment_link",
        "payment_method_update",
        "stop_recovery",
    }
)
EXPENSIVE_ACTIONS = frozenset({"human_escalation", "voice_call", "limited_incentive"})


def format_economic_evaluation_report(summary: EconomicEvaluationSummary) -> str:
    lines = [
        "=" * 72,
        "Podium Phase 5 Economic Evaluation",
        f"Mode: {summary.intelligence_mode}",
        "=" * 72,
        f"Cases evaluated:          {summary.cases_evaluated}",
        f"Recovery rate:            {summary.recovery_rate:.1%}",
        f"Cheap action share:       {summary.cheap_action_share:.1%}",
        f"Expensive action share:   {summary.expensive_action_share:.1%}",
        f"Economic audit coverage:  {summary.economic_audit_rate:.1%}",
    ]
    if summary.avg_expected_net_value is not None:
        lines.append(f"Avg expected net value:   INR {summary.avg_expected_net_value:,.2f}")
    lines.append("=" * 72)
    return "\n".join(lines)
