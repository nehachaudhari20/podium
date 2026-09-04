"""Deterministic recovery context builder — Phase 3A."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from podium.audit.trail import load_audit_trail
from podium.ingestion.customer_loader import load_customer_context
from podium.ingestion.runtime_loader import load_case_by_id
from podium.models.case import RecoveryCaseRuntime
from podium.models.recovery_context import (
    CaseFacts,
    CustomerHistorySnapshot,
    DerivedSignals,
    RecoveryContext,
    RecoveryHistoryEvent,
    assert_no_forbidden_fields,
    utc_now_iso,
)
from podium.models.recovery_types import AuditEvent
from podium.policy.gate import load_policy_config
from podium.state.context import CaseRunContext

TRANSIENT_FAILURE_REASONS = frozenset(
    {"transient_technical", "network_timeout", "issuer_timeout"}
)
EXPIRED_METHOD_REASONS = frozenset({"expired_card", "invalid_card"})
ACTION_EVENT_TYPES = frozenset(
    {
        "ACTION_EXECUTED",
        "DIAGNOSED",
        "POLICY_CHECK",
        "STATE_TRANSITION",
        "RECOVERED",
        "PAYMENT_FAILED",
        "EXHAUSTED",
        "ESCALATED",
        "RETRY_SCHEDULED",
        "SIM_TIME_ADVANCED",
        "PAYMENT_METHOD_UPDATE",
    }
)


class ContextBuilder:
    """Build structured RecoveryContext from runtime-safe data sources."""

    def build(
        self,
        conn: sqlite3.Connection,
        case_id: str,
        *,
        run_context: CaseRunContext | None = None,
        now: datetime | None = None,
    ) -> RecoveryContext:
        case = load_case_by_id(conn, case_id)
        if case is None:
            raise ValueError(f"Case not found: {case_id}")
        return self.build_from_case(conn, case, run_context=run_context, now=now)

    def build_from_case(
        self,
        conn: sqlite3.Connection,
        case: RecoveryCaseRuntime,
        *,
        run_context: CaseRunContext | None = None,
        now: datetime | None = None,
    ) -> RecoveryContext:
        now = now or datetime.now(timezone.utc)
        customer_ctx = load_customer_context(conn, case.customer_id)
        customer_snapshot = self._load_customer_snapshot(conn, case, customer_ctx)
        audit_events = load_audit_trail(conn, case.case_id)
        recovery_history = self._build_recovery_history(audit_events)

        case_facts = self._build_case_facts(case, run_context)
        signals = self._derive_signals(case_facts, customer_snapshot, recovery_history, now)

        context = RecoveryContext(
            case=case_facts,
            customer=customer_snapshot,
            recovery_history=tuple(recovery_history),
            derived_signals=signals,
            built_at=utc_now_iso(),
        )
        assert_no_forbidden_fields(context.to_dict())
        return context

    def _build_case_facts(
        self,
        case: RecoveryCaseRuntime,
        run_context: CaseRunContext | None,
    ) -> CaseFacts:
        attempt_count = case.attempt_count
        workflow_state = case.workflow_state
        last_action = None
        payment_method_updated = False

        if run_context is not None:
            attempt_count = run_context.attempt_count
            workflow_state = run_context.workflow_state
            last_action = run_context.last_action
            payment_method_updated = run_context.payment_method_updated

        return CaseFacts(
            case_id=case.case_id,
            customer_id=case.customer_id,
            lane=case.lane,
            amount=case.amount,
            currency=case.currency,
            workflow_state=workflow_state,
            status=case.status,
            failure_reason=case.failure_reason,
            recoverability_hint=case.recoverability_hint,
            attempt_count=attempt_count,
            created_at=case.created_at.isoformat(),
            recovery_window_end=case.recovery_window_end.isoformat(),
            source_ref_id=case.source_ref_id,
            days_overdue=case.days_overdue,
            is_hero=case.is_hero,
            last_action=last_action,
            payment_method_updated=payment_method_updated,
        )

    def _load_customer_snapshot(
        self,
        conn: sqlite3.Connection,
        case: RecoveryCaseRuntime,
        customer_ctx,
    ) -> CustomerHistorySnapshot:
        failed = conn.execute(
            """
            SELECT COUNT(*) FROM payments
            WHERE customer_id = ? AND status = 'failed'
            """,
            (case.customer_id,),
        ).fetchone()[0]
        succeeded = conn.execute(
            """
            SELECT COUNT(*) FROM payments
            WHERE customer_id = ? AND status IN ('captured', 'success', 'paid')
            """,
            (case.customer_id,),
        ).fetchone()[0]
        prior_actions = conn.execute(
            """
            SELECT COUNT(*) FROM recovery_action_log
            WHERE case_id = ?
            """,
            (case.case_id,),
        ).fetchone()[0]
        no_response = conn.execute(
            """
            SELECT COUNT(*) FROM contact_history
            WHERE customer_id = ? AND outcome = 'no_response'
            """,
            (case.customer_id,),
        ).fetchone()[0]
        open_cases = conn.execute(
            """
            SELECT COUNT(*) FROM recovery_cases
            WHERE customer_id = ? AND status = 'open'
            """,
            (case.customer_id,),
        ).fetchone()[0]

        return CustomerHistorySnapshot(
            customer_id=customer_ctx.customer_id,
            segment=customer_ctx.segment,
            opt_out=customer_ctx.opt_out,
            prior_contacts_7d=customer_ctx.prior_contacts_7d,
            total_failed_payments=int(failed),
            total_successful_payments=int(succeeded),
            prior_recovery_actions=int(prior_actions),
            contacts_with_no_response=int(no_response),
            open_case_count=int(open_cases),
        )

    def _build_recovery_history(
        self,
        audit_events: list[AuditEvent],
    ) -> list[RecoveryHistoryEvent]:
        history: list[RecoveryHistoryEvent] = []
        for event in audit_events:
            if event.event_type not in ACTION_EVENT_TYPES:
                continue
            result = None
            if event.event_type == "ACTION_EXECUTED":
                result = event.metadata.get("event")
            elif event.event_type in ("RECOVERED", "PAYMENT_FAILED", "EXHAUSTED", "ESCALATED"):
                result = event.event_type.lower()
            history.append(
                RecoveryHistoryEvent(
                    timestamp=event.timestamp,
                    event_type=event.event_type,
                    action=event.action,
                    result=result,
                    state_before=event.from_state,
                    state_after=event.to_state,
                    actor=event.actor,
                    detail=event.reason,
                )
            )
        return history

    def _derive_signals(
        self,
        case: CaseFacts,
        customer: CustomerHistorySnapshot,
        history: list[RecoveryHistoryEvent],
        now: datetime,
    ) -> DerivedSignals:
        policy = load_policy_config()
        reason = case.failure_reason or ""

        first_failure = case.attempt_count == 0 and reason != "repeated_failure"
        repeated_failure = reason == "repeated_failure" or case.attempt_count >= 2
        prior_successful_payment = customer.total_successful_payments > 0
        retry_exhaustion_risk = case.attempt_count >= max(policy.max_retries - 1, 0)
        recent_contact = customer.prior_contacts_7d > 0 or any(
            e.event_type in ("ACTION_EXECUTED", "STATE_TRANSITION")
            and e.action in ("payment_method_update", "send_email", "send_whatsapp", "send_sms")
            for e in history
        )
        customer_non_response = customer.contacts_with_no_response > 0

        window_end = datetime.fromisoformat(case.recovery_window_end)
        if window_end.tzinfo is None:
            window_end = window_end.replace(tzinfo=timezone.utc)
        near_window_end = (window_end - now) <= timedelta(days=3)

        return DerivedSignals(
            first_failure=first_failure,
            repeated_failure=repeated_failure,
            prior_successful_payment=prior_successful_payment,
            retry_exhaustion_risk=retry_exhaustion_risk,
            recent_contact=recent_contact,
            customer_non_response=customer_non_response,
            customer_opt_out=customer.opt_out,
            near_recovery_window_end=near_window_end,
            transient_failure=reason in TRANSIENT_FAILURE_REASONS,
            expired_payment_method=reason in EXPIRED_METHOD_REASONS,
        )


def build_recovery_context(
    conn: sqlite3.Connection,
    case_id: str,
    *,
    run_context: CaseRunContext | None = None,
    now: datetime | None = None,
) -> RecoveryContext:
    """Convenience wrapper for ContextBuilder.build."""
    return ContextBuilder().build(conn, case_id, run_context=run_context, now=now)
