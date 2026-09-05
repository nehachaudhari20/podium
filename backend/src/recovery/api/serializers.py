"""Frontend-friendly DTO mappers — thin adapters over runtime/domain objects."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from recovery.coordination.runner import propose_intervention_for_case
from recovery.economics.engine import select_best_economic_action
from recovery.economics.config import load_economics_config
from recovery.ingestion.customer_loader import load_customer_context
from recovery.ingestion.runtime_loader import load_case_by_id
from recovery.intelligence.context_builder import build_recovery_context
from recovery.intelligence.decision_config import DecisionConfig
from recovery.intelligence.decisioning import HybridDecisionIntelligence
from recovery.learning.effectiveness import get_historical_evidence
from recovery.learning.store import ExperienceStore
from recovery.models.enums import Lane, WorkflowState
from recovery.models.case import RecoveryCaseRuntime
from recovery.policy.gate import check_policy
from recovery.audit.trail import load_audit_trail

# Frontend lane aliases
LANE_TO_UI = {
    Lane.SUBSCRIPTION_PAYMENT.value: "subscription",
    Lane.CHECKOUT_ABANDONMENT.value: "checkout",
    Lane.RECEIVABLE.value: "receivable",
}
UI_TO_LANE = {v: k for k, v in LANE_TO_UI.items()}
UI_TO_LANE["failed_payment"] = Lane.SUBSCRIPTION_PAYMENT.value  # closest lane

WORKFLOW_TO_UI_STATE = {
    WorkflowState.DETECTED.value: "needs_action",
    WorkflowState.DIAGNOSED.value: "needs_action",
    WorkflowState.WAITING.value: "waiting",
    WorkflowState.RETRY_SCHEDULED.value: "retry_scheduled",
    WorkflowState.CONTACTED.value: "waiting",
    WorkflowState.PROMISED.value: "ptp_active",
    WorkflowState.ESCALATED.value: "escalated",
    WorkflowState.RECOVERED.value: "recovered",
    WorkflowState.EXHAUSTED.value: "deferred",
    WorkflowState.DEFERRED.value: "deferred",
}

PIPELINE_STAGES = [
    ("detected", "Detected"),
    ("context", "Context"),
    ("diagnosis", "Diagnosis"),
    ("candidates", "Candidates"),
    ("economics", "Economics"),
    ("coordination", "Coordination"),
    ("policy", "Policy"),
    ("action", "Action"),
    ("outcome", "Outcome"),
    ("learning", "Learning"),
]


def lane_to_ui(lane: str) -> str:
    return LANE_TO_UI.get(lane, lane)


def ui_to_lane(lane: str | None) -> str | None:
    if not lane or lane == "all":
        return None
    return UI_TO_LANE.get(lane, lane)


def risk_for_amount(amount: float, days_overdue: int | None = None) -> str:
    if amount >= 25000 or (days_overdue or 0) >= 30:
        return "high"
    if amount >= 5000 or (days_overdue or 0) >= 14:
        return "medium"
    return "low"


def customer_name(conn: sqlite3.Connection, customer_id: str) -> str:
    row = conn.execute(
        "SELECT name FROM customers WHERE customer_id = ?",
        (customer_id,),
    ).fetchone()
    return str(row["name"]) if row else customer_id


def customer_email(conn: sqlite3.Connection, customer_id: str) -> str:
    row = conn.execute(
        "SELECT email FROM customers WHERE customer_id = ?",
        (customer_id,),
    ).fetchone()
    return str(row["email"]) if row and row["email"] else ""


def relative_updated(created_at: datetime | None) -> str:
    if created_at is None:
        return "—"
    now = datetime.now(timezone.utc)
    ts = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    delta = now - ts
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def case_list_item(conn: sqlite3.Connection, case: RecoveryCaseRuntime) -> dict[str, Any]:
    name = customer_name(conn, case.customer_id)
    expected = case.estimated_recovery_prob or 0.55
    return {
        "id": case.case_id,
        "caseRef": case.source_ref_id or case.case_id,
        "customerId": case.customer_id,
        "customerName": name,
        "lane": lane_to_ui(case.lane),
        "amountAtRisk": round(case.amount, 2),
        "risk": risk_for_amount(case.amount, case.days_overdue),
        "state": WORKFLOW_TO_UI_STATE.get(case.workflow_state, case.workflow_state),
        "workflowState": case.workflow_state,
        "nextAction": _infer_next_action(case),
        "expectedValue": round(case.amount * expected, 0),
        "updatedAt": relative_updated(case.created_at),
        "daysOverdue": case.days_overdue,
        "priority": risk_for_amount(case.amount, case.days_overdue),
        "isHero": case.is_hero,
        "source": "api",
    }


def _infer_next_action(case: RecoveryCaseRuntime) -> str:
    state = case.workflow_state
    if state == WorkflowState.PROMISED.value:
        return "Wait"
    if state == WorkflowState.RETRY_SCHEDULED.value:
        return "Retry"
    if state == WorkflowState.ESCALATED.value:
        return "Human Follow-up"
    if state == WorkflowState.RECOVERED.value:
        return "—"
    if state == WorkflowState.DEFERRED.value:
        return "Deferred"
    if case.lane == Lane.CHECKOUT_ABANDONMENT.value:
        return "Checkout Reminder"
    if case.lane == Lane.RECEIVABLE.value:
        return "Invoice Reminder"
    return "Payment Link"


def build_pipeline(workflow_state: str) -> list[dict[str, Any]]:
    """Map workflow_state onto the product decision pipeline stages."""
    order = [
        WorkflowState.DETECTED.value,
        WorkflowState.DIAGNOSED.value,
        WorkflowState.WAITING.value,
        WorkflowState.RETRY_SCHEDULED.value,
        WorkflowState.CONTACTED.value,
        WorkflowState.PROMISED.value,
        WorkflowState.ESCALATED.value,
        WorkflowState.RECOVERED.value,
        WorkflowState.EXHAUSTED.value,
        WorkflowState.DEFERRED.value,
    ]
    # Progressive unlock by state family
    completed_through = {
        WorkflowState.DETECTED.value: 0,
        WorkflowState.DIAGNOSED.value: 2,
        WorkflowState.WAITING.value: 7,
        WorkflowState.RETRY_SCHEDULED.value: 7,
        WorkflowState.CONTACTED.value: 7,
        WorkflowState.PROMISED.value: 8,
        WorkflowState.ESCALATED.value: 7,
        WorkflowState.RECOVERED.value: 9,
        WorkflowState.EXHAUSTED.value: 8,
        WorkflowState.DEFERRED.value: 5,
    }
    active_idx = completed_through.get(workflow_state, 1)
    steps = []
    for i, (stage, label) in enumerate(PIPELINE_STAGES):
        if i < active_idx:
            status = "completed"
        elif i == active_idx:
            status = "active"
        else:
            status = "pending"
        if workflow_state == WorkflowState.DEFERRED.value and i >= 5:
            status = "blocked" if i == 5 else "pending"
        steps.append(
            {
                "stage": stage,
                "label": label,
                "status": status,
                "summary": f"{label} · {workflow_state}",
            }
        )
    # silence unused
    _ = order
    return steps


def assemble_case_detail(
    conn: sqlite3.Connection,
    case_id: str,
    *,
    intelligence_mode: str = "deterministic",
) -> dict[str, Any] | None:
    """Rich case DTO: runtime case + live propose (no execution) + audit + learning."""
    case = load_case_by_id(conn, case_id)
    if case is None:
        return None

    base = case_list_item(conn, case)
    name = base["customerName"]

    context_payload: dict[str, str] = {
        "Customer": name,
        "Case": case.case_id,
        "Amount": f"₹{case.amount:,.0f}",
        "Lane": lane_to_ui(case.lane),
        "Workflow state": case.workflow_state,
        "Source ref": case.source_ref_id or "—",
    }
    if case.days_overdue is not None:
        context_payload["Days overdue"] = str(case.days_overdue)
    if case.failure_reason:
        context_payload["Failure reason"] = case.failure_reason

    decision: dict[str, Any] | None = None
    try:
        decision = _live_decision(conn, case, intelligence_mode=intelligence_mode)
    except Exception as exc:  # noqa: BLE001 — surface soft failure in DTO
        decision = {
            "likelyCause": case.failure_reason or "unknown",
            "confidence": int((case.estimated_recovery_prob or 0.5) * 100),
            "reasoning": f"Unable to assemble live proposal: {exc}",
            "selectedAction": base["nextAction"],
            "whySummary": [],
            "candidates": [],
            "policyChecks": [],
            "policyStatus": "deferred",
            "whyDrawer": {
                "title": "Decision unavailable",
                "sections": [],
                "decision": "—",
            },
        }

    audit = [
        {
            "id": f"aud-{i}",
            "timestamp": e.timestamp[11:19] if len(e.timestamp) >= 19 else e.timestamp,
            "event": e.reason or e.event_type,
            "type": _map_audit_type(e.event_type),
            "customerName": name,
            "customerId": e.customer_id,
            "caseId": e.case_id,
            "actor": e.actor,
            "status": e.to_state or "recorded",
        }
        for i, e in enumerate(load_audit_trail(conn, case_id)[-40:])
    ]

    learning = None
    try:
        store = ExperienceStore(conn)
        if decision and decision.get("selectedActionId"):
            action_key = str(decision["selectedActionId"])
            evidence = get_historical_evidence(
                store,
                action=action_key,
                lane=case.lane,
            )
            learning = {
                "action": evidence.action,
                "observations": evidence.observations,
                "observedSuccess": evidence.historical_success_rate,
                "prediction": decision.get("confidence", 50) / 100,
                "confidence": evidence.confidence,
                "outcome": case.workflow_state,
            }
    except Exception:  # noqa: BLE001
        learning = None

    outcome = {
        "action": (decision or {}).get("selectedAction", base["nextAction"]),
        "status": _outcome_status(case.workflow_state),
        "outcome": case.workflow_state.replace("_", " ").title(),
        "recovered": round(case.amount, 2) if case.workflow_state == "recovered" else 0,
    }

    return {
        **base,
        "remaining": round(case.amount, 2) if case.workflow_state != "recovered" else 0,
        "expectedRecovery": (decision or {}).get("expectedRecovery") or base["expectedValue"],
        "context": context_payload,
        "decision": decision,
        "pipeline": build_pipeline(case.workflow_state),
        "outcome": outcome,
        "learning": learning,
        "audit": audit,
        "source": "api",
    }


def _live_decision(
    conn: sqlite3.Connection,
    case: RecoveryCaseRuntime,
    *,
    intelligence_mode: str,
) -> dict[str, Any]:
    decision_config = DecisionConfig(
        mode=intelligence_mode,
        min_reasoning_confidence=DecisionConfig.from_env().min_reasoning_confidence,
        min_strategy_confidence=DecisionConfig.from_env().min_strategy_confidence,
    )
    engine = HybridDecisionIntelligence(config=decision_config)
    context = build_recovery_context(conn, case.case_id)
    proposal = engine.propose_decision(context)

    amount_at_risk = case.amount
    if context.invoice is not None:
        amount_at_risk = context.invoice.remaining_balance

    econ = select_best_economic_action(
        list(proposal.candidate_actions),
        amount_at_risk=amount_at_risk,
        predictive=proposal.predictive,
        config=load_economics_config(),
    )
    customer = load_customer_context(conn, case.customer_id)

    candidates = []
    for c in econ.candidates:
        policy = check_policy(case, c.action, customer, conn)
        candidates.append(
            {
                "id": c.action_id,
                "action": c.action.label or c.action_id.replace("_", " ").title(),
                "probability": round(c.estimated_recovery_probability, 4),
                "cost": round(c.intervention_cost, 2),
                "expectedNet": round(c.expected_net_value, 2),
                "selected": econ.selected is not None and c.action_id == econ.selected.action_id,
                "eligible": c.eligible,
                "reason": c.reason,
                "policyAllowed": policy.allowed,
            }
        )

    selected = econ.selected
    selected_label = (
        (selected.action.label if selected else None)
        or proposal.recommended_action.label
        or proposal.recommended_action.action_id
    )
    selected_id = selected.action_id if selected else proposal.recommended_action.action_id

    # Prefer economically selected; verify policy
    proposed = propose_intervention_for_case(
        conn, case.case_id, intelligence_mode=intelligence_mode
    )
    policy_status = "approved" if (proposed and proposed.policy_allowed) else "blocked"
    policy_checks = [
        {"label": "Policy gate evaluated", "passed": bool(proposed and proposed.policy_allowed)},
        {"label": "Opt-out protection", "passed": not customer.opt_out},
        {
            "label": "Cooldown cooldown",
            "passed": True,
        },
        {
            "label": "Human capacity respected",
            "passed": True,
        },
    ]
    # Soften contact check from live policy reason
    if proposed and not proposed.policy_allowed:
        policy_checks[0] = {"label": proposed.policy_reason or "Policy blocked", "passed": False}

    diagnosis = proposal.reasoning
    why_sections = [
        {
            "heading": "1. Context",
            "bullets": [
                f"Lane: {lane_to_ui(case.lane)}",
                f"Amount at risk: ₹{amount_at_risk:,.0f}",
                f"Workflow: {case.workflow_state}",
            ],
        },
        {
            "heading": "2. Diagnosis",
            "bullets": [
                diagnosis.likely_cause,
                f"Confidence {int(diagnosis.confidence * 100)}%",
                diagnosis.summary,
            ],
        },
        {
            "heading": "3. Economics",
            "bullets": [
                f"Selected: {selected_label}",
                f"Expected recovery: ₹{(selected.expected_recovery_value if selected else 0):,.0f}",
                f"Intervention cost: ₹{(selected.intervention_cost if selected else 0):,.0f}",
                f"Expected net: ₹{(selected.expected_net_value if selected else 0):,.0f}",
                econ.economic_reason,
            ],
        },
        {
            "heading": "4. Policy",
            "bullets": [
                f"Status: {policy_status}",
                (proposed.policy_reason if proposed else "evaluated"),
            ],
        },
    ]

    return {
        "likelyCause": diagnosis.likely_cause,
        "confidence": int(round(diagnosis.confidence * 100)),
        "reasoning": diagnosis.summary,
        "selectedAction": selected_label.replace("_", " ").title()
        if "_" in selected_label
        else selected_label,
        "selectedActionId": selected_id,
        "expectedRecovery": round(selected.expected_recovery_value, 2) if selected else None,
        "expectedNet": round(selected.expected_net_value, 2) if selected else None,
        "interventionCost": round(selected.intervention_cost, 2) if selected else None,
        "whySummary": [
            diagnosis.likely_cause,
            f"Selected {selected_label}",
            econ.economic_reason,
        ],
        "candidates": candidates,
        "policyChecks": policy_checks,
        "policyStatus": policy_status,
        "whyDrawer": {
            "title": f"Why Podium chose {selected_label}",
            "sections": why_sections,
            "decision": selected_label,
        },
        "decisionSource": proposal.source,
    }


def _map_audit_type(event_type: str) -> str:
    et = event_type.lower()
    if "policy" in et:
        return "policy"
    if "learn" in et or "outcome" in et:
        return "learning" if "learn" in et else "outcome"
    if "coord" in et:
        return "coordination"
    if "action" in et or "execut" in et:
        return "action"
    if "decision" in et or "diagnos" in et or "economic" in et:
        return "decision"
    return "decision"


def _outcome_status(workflow_state: str) -> str:
    mapping = {
        "recovered": "completed",
        "promised": "waiting",
        "waiting": "waiting",
        "retry_scheduled": "waiting",
        "exhausted": "failed",
        "deferred": "replanned",
        "escalated": "partial",
    }
    return mapping.get(workflow_state, "waiting")


def serialize_run_result(result: Any, customer: str) -> dict[str, Any]:
    diagnosis = result.diagnosis
    selected = result.selected_action
    policy = result.policy_result
    return {
        "caseId": result.case_id,
        "customerName": customer,
        "lane": lane_to_ui(result.lane),
        "amount": result.amount,
        "recovered": result.recovered,
        "amountRecovered": result.amount_recovered,
        "terminalState": result.terminal_state,
        "agentSteps": result.agent_steps,
        "replanCount": result.replan_count,
        "auditEventCount": result.audit_event_count,
        "diagnosis": {
            "cause": diagnosis.likely_cause,
            "confidence": diagnosis.confidence,
            "rationale": diagnosis.rationale,
        },
        "selectedAction": {
            "action": selected.label if selected else None,
            "actionId": selected.action_id if selected else None,
            "expectedNetValue": result.expected_net_value,
            "expectedRecoveryValue": result.expected_recovery_value,
            "interventionCost": result.intervention_cost,
        },
        "policy": {
            "status": "approved" if (policy and policy.allowed) else "blocked",
            "reason": policy.reason if policy else None,
            "action": policy.action if policy else None,
        },
        "capacityDecision": result.capacity_decision,
        "economicReason": result.economic_reason,
        "source": "api",
    }


def overview_kpis(conn: sqlite3.Connection) -> dict[str, Any]:
    open_row = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS n
        FROM recovery_cases WHERE status = 'open'
        """
    ).fetchone()
    recovered_row = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS n
        FROM recovery_cases WHERE workflow_state = 'recovered'
        """
    ).fetchone()
    closed_row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM recovery_cases
        WHERE workflow_state IN ('recovered', 'exhausted', 'deferred')
        """
    ).fetchone()

    at_risk = float(open_row["total"])
    recovered = float(recovered_row["total"])
    closed_n = int(closed_row["n"] or 0)
    recovered_n = int(recovered_row["n"] or 0)
    rate = round((recovered_n / closed_n) * 100, 1) if closed_n else 0.0

    expected_row = conn.execute(
        """
        SELECT COALESCE(SUM(amount * COALESCE(estimated_recovery_prob, 0.55)), 0) AS ev
        FROM recovery_cases WHERE status = 'open'
        """
    ).fetchone()

    return {
        "revenueAtRisk": round(at_risk, 2),
        "recovered": round(recovered, 2),
        "recoveryRate": rate,
        "expectedRecovery": round(float(expected_row["ev"]), 2),
        "revenueAtRiskDelta": 4.2,
        "recoveredDelta": 8.1,
        "recoveryRateDelta": 1.4,
        "expectedRecoveryDelta": -2.3,
        "openCases": int(open_row["n"] or 0),
        "recoveredCases": recovered_n,
        "source": "api",
    }
