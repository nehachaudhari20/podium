"""Deterministic recovery context builder — Phase 3A / 4A."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from recovery.audit.trail import load_audit_trail
from recovery.ingestion.checkout_loader import (
    count_prior_checkout_abandonments,
    load_checkout_session_by_case,
)
from recovery.ingestion.customer_loader import load_customer_context
from recovery.ingestion.invoice_loader import (
    load_active_promise_by_case,
    load_invoice_by_case,
    load_promises_for_case,
)
from recovery.ingestion.runtime_loader import load_case_by_id
from recovery.models.case import RecoveryCaseRuntime
from recovery.models.enums import Lane
from recovery.models.recovery_context import (
    CaseFacts,
    CheckoutSessionFacts,
    CrossRevenueFacts,
    CustomerHistorySnapshot,
    DerivedSignals,
    InvoiceFacts,
    PromiseFacts,
    RecoveryContext,
    RecoveryHistoryEvent,
    SiblingCaseFacts,
    assert_no_forbidden_fields,
    utc_now_iso,
)
from recovery.models.recovery_types import AuditEvent
from recovery.policy.gate import load_policy_config
from recovery.state.context import CaseRunContext

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
        "AGENT_OBSERVE",
        "AGENT_REPLAN",
        "DECISION_PROPOSED",
        "PROMISE_CREATED",
        "PROMISE_DUE",
        "PROMISE_KEPT",
        "PROMISE_BROKEN",
        "PARTIAL_PAYMENT_RECEIVED",
    }
)

HIGH_INTENT_THRESHOLD = 0.7
HIGH_VALUE_CART_INR = 15000.0
HIGH_VALUE_INVOICE_INR = 50000.0
RECENT_ABANDONMENT_HOURS = 24.0
EARLY_STAGES = frozenset({"cart", "shipping"})
PAYMENT_STAGES = frozenset({"payment_page", "payment"})
RECEIVABLE_CONTACT_ACTIONS = frozenset(
    {
        "invoice_reminder",
        "payment_link",
        "promise_to_pay_request",
        "statement_resend",
        "payment_assistance",
        "human_escalation",
        "escalate_collections",
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
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        customer_ctx = load_customer_context(conn, case.customer_id)
        customer_snapshot = self._load_customer_snapshot(conn, case, customer_ctx)
        audit_events = load_audit_trail(conn, case.case_id)
        recovery_history = self._build_recovery_history(audit_events)

        case_facts = self._build_case_facts(case, run_context)
        checkout_facts = self._build_checkout_facts(conn, case, now)
        invoice_facts = self._build_invoice_facts(conn, case, run_context)
        promise_facts = self._build_promise_facts(conn, case)
        prior_checkouts = 0
        if case.lane == Lane.CHECKOUT_ABANDONMENT.value:
            prior_checkouts = count_prior_checkout_abandonments(
                conn, case.customer_id, exclude_case_id=case.case_id
            )

        cross_revenue = self._build_cross_revenue(conn, case)
        signals = self._derive_signals(
            case_facts,
            customer_snapshot,
            recovery_history,
            now,
            checkout=checkout_facts,
            invoice=invoice_facts,
            promise=promise_facts,
            prior_checkout_abandonments=prior_checkouts,
            cross_revenue=cross_revenue,
            run_context=run_context,
            conn=conn,
        )

        context = RecoveryContext(
            case=case_facts,
            customer=customer_snapshot,
            recovery_history=tuple(recovery_history),
            derived_signals=signals,
            built_at=utc_now_iso(),
            checkout=checkout_facts,
            cross_revenue=cross_revenue,
            invoice=invoice_facts,
            promise=promise_facts,
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

    def _build_checkout_facts(
        self,
        conn: sqlite3.Connection,
        case: RecoveryCaseRuntime,
        now: datetime,
    ) -> CheckoutSessionFacts | None:
        if case.lane != Lane.CHECKOUT_ABANDONMENT.value:
            return None

        session = load_checkout_session_by_case(conn, case.case_id)
        if session is None:
            return None

        abandoned = session.abandoned_at
        if abandoned.tzinfo is None:
            abandoned = abandoned.replace(tzinfo=timezone.utc)
        hours = max(0.0, (now - abandoned).total_seconds() / 3600.0)

        return CheckoutSessionFacts(
            session_id=session.session_id,
            cart_value=session.cart_value,
            currency=session.currency,
            stage=session.stage,
            intent_score=session.intent_score,
            abandoned_at=abandoned.isoformat(),
            items_count=session.items_count,
            hours_since_abandonment=round(hours, 2),
        )

    def _build_invoice_facts(
        self,
        conn: sqlite3.Connection,
        case: RecoveryCaseRuntime,
        run_context: CaseRunContext | None,
    ) -> InvoiceFacts | None:
        if case.lane != Lane.RECEIVABLE.value:
            return None
        invoice = load_invoice_by_case(conn, case.case_id)
        if invoice is None:
            remaining = (
                run_context.remaining_balance
                if run_context is not None and run_context.remaining_balance is not None
                else case.amount
            )
            return InvoiceFacts(
                invoice_id=case.source_ref_id,
                amount=case.amount,
                currency=case.currency,
                due_date=case.created_at.isoformat(),
                days_overdue=int(case.days_overdue or 0),
                status="overdue",
                invoice_type="b2b",
                remaining_balance=float(remaining),
            )
        remaining = (
            run_context.remaining_balance
            if run_context is not None and run_context.remaining_balance is not None
            else float(invoice.amount)
        )
        if run_context is not None:
            remaining = max(0.0, round(float(invoice.amount) - run_context.amount_paid, 2))
            run_context.remaining_balance = remaining
        return InvoiceFacts(
            invoice_id=invoice.invoice_id,
            amount=float(invoice.amount),
            currency=invoice.currency,
            due_date=invoice.due_date.isoformat(),
            days_overdue=int(invoice.days_overdue),
            status=invoice.status,
            invoice_type=invoice.invoice_type,
            remaining_balance=remaining,
        )

    def _build_promise_facts(
        self,
        conn: sqlite3.Connection,
        case: RecoveryCaseRuntime,
    ) -> PromiseFacts | None:
        if case.lane != Lane.RECEIVABLE.value:
            return None
        active = load_active_promise_by_case(conn, case.case_id)
        if active is not None:
            return PromiseFacts(
                promise_id=active.promise_id,
                promised_amount=float(active.promised_amount),
                promise_date=active.promise_date.isoformat(),
                status=active.status,
                created_at=active.created_at.isoformat(),
            )
        promises = load_promises_for_case(conn, case.case_id)
        if not promises:
            return None
        latest = promises[-1]
        return PromiseFacts(
            promise_id=latest.promise_id,
            promised_amount=float(latest.promised_amount),
            promise_date=latest.promise_date.isoformat(),
            status=latest.status,
            created_at=latest.created_at.isoformat(),
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

    def _build_cross_revenue(
        self,
        conn: sqlite3.Connection,
        case: RecoveryCaseRuntime,
    ) -> CrossRevenueFacts:
        rows = conn.execute(
            """
            SELECT case_id, lane, amount, workflow_state, status
            FROM recovery_cases
            WHERE customer_id = ? AND status = 'open'
            ORDER BY amount DESC, case_id
            """,
            (case.customer_id,),
        ).fetchall()
        siblings = tuple(
            SiblingCaseFacts(
                case_id=row["case_id"],
                lane=row["lane"],
                amount=float(row["amount"]),
                workflow_state=row["workflow_state"],
                status=row["status"],
            )
            for row in rows
            if row["case_id"] != case.case_id
        )
        all_cases = tuple(
            SiblingCaseFacts(
                case_id=row["case_id"],
                lane=row["lane"],
                amount=float(row["amount"]),
                workflow_state=row["workflow_state"],
                status=row["status"],
            )
            for row in rows
        )
        lanes = tuple(sorted({c.lane for c in all_cases}))
        total = round(sum(c.amount for c in all_cases), 2)
        return CrossRevenueFacts(
            total_amount_at_risk=total,
            active_lanes=lanes,
            sibling_cases=siblings,
            open_case_count=len(all_cases),
            multi_lane_active=len(lanes) > 1,
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
        *,
        checkout: CheckoutSessionFacts | None = None,
        invoice: InvoiceFacts | None = None,
        promise: PromiseFacts | None = None,
        prior_checkout_abandonments: int = 0,
        cross_revenue: CrossRevenueFacts | None = None,
        run_context: CaseRunContext | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> DerivedSignals:
        policy = load_policy_config()
        reason = case.failure_reason or ""

        first_failure = case.attempt_count == 0 and reason != "repeated_failure"
        repeated_failure = reason == "repeated_failure" or case.attempt_count >= 2
        prior_successful_payment = customer.total_successful_payments > 0
        retry_exhaustion_risk = case.attempt_count >= max(policy.max_retries - 1, 0)
        recent_contact = customer.prior_contacts_7d > 0 or any(
            e.event_type in ("ACTION_EXECUTED", "STATE_TRANSITION")
            and e.action
            in (
                "payment_method_update",
                "send_email",
                "send_whatsapp",
                "send_sms",
                "checkout_reminder",
                "payment_link",
                "checkout_assistance",
                *RECEIVABLE_CONTACT_ACTIONS,
            )
            for e in history
        )
        customer_non_response = customer.contacts_with_no_response > 0

        window_end = datetime.fromisoformat(case.recovery_window_end)
        if window_end.tzinfo is None:
            window_end = window_end.replace(tzinfo=timezone.utc)
        near_window_end = (window_end - now) <= timedelta(days=3)

        high_intent = False
        high_value_cart = False
        payment_stage_abandonment = False
        early_stage_abandonment = False
        recent_abandonment = False
        repeat_abandoner = False
        prior_successful_customer = prior_successful_payment
        recovery_attempted_before = (
            case.attempt_count > 0 or customer.prior_recovery_actions > 0 or len(history) > 0
        )

        if checkout is not None:
            intent = checkout.intent_score
            high_intent = intent is not None and intent >= HIGH_INTENT_THRESHOLD
            high_value_cart = checkout.cart_value >= HIGH_VALUE_CART_INR
            payment_stage_abandonment = checkout.stage in PAYMENT_STAGES
            early_stage_abandonment = checkout.stage in EARLY_STAGES
            recent_abandonment = checkout.hours_since_abandonment <= RECENT_ABANDONMENT_HOURS
            repeat_abandoner = prior_checkout_abandonments > 0
            if reason == "checkout_high_intent_drop":
                high_intent = True
            if reason == "checkout_payment_page_drop":
                payment_stage_abandonment = True
            if reason == "checkout_cart_abandon":
                early_stage_abandonment = True

        multi_lane = bool(cross_revenue and cross_revenue.multi_lane_active)
        has_siblings = bool(cross_revenue and cross_revenue.sibling_cases)

        days = case.days_overdue if case.days_overdue is not None else (
            invoice.days_overdue if invoice is not None else 0
        )
        active_promise = bool(promise is not None and promise.status == "active")
        if run_context is not None and run_context.active_promise_id:
            active_promise = True
        promise_broken_before = bool(
            (run_context is not None and run_context.promise_broken_before)
            or reason == "promise_missed"
            or (promise is not None and promise.status == "missed")
        )
        if conn is not None and case.lane == Lane.RECEIVABLE.value:
            prior_missed = load_promises_for_case(conn, case.case_id)
            if any(p.status == "missed" for p in prior_missed):
                promise_broken_before = True

        mildly_overdue = days <= 10
        aged_overdue = 10 < days < 45
        severely_overdue = days >= 45
        high_value_invoice = bool(
            (invoice is not None and invoice.amount >= HIGH_VALUE_INVOICE_INR)
            or case.amount >= HIGH_VALUE_INVOICE_INR
        )
        partial_payment_received = bool(
            run_context is not None
            and run_context.amount_paid > 0
            and (run_context.remaining_balance or 0) > 0
        )

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
            high_intent=high_intent,
            high_value_cart=high_value_cart,
            payment_stage_abandonment=payment_stage_abandonment,
            early_stage_abandonment=early_stage_abandonment,
            recent_abandonment=recent_abandonment,
            repeat_abandoner=repeat_abandoner,
            prior_successful_customer=prior_successful_customer,
            recovery_attempted_before=recovery_attempted_before,
            multi_lane_active=multi_lane,
            has_sibling_open_cases=has_siblings,
            active_promise=active_promise,
            promise_broken_before=promise_broken_before,
            mildly_overdue=mildly_overdue,
            aged_overdue=aged_overdue,
            severely_overdue=severely_overdue,
            high_value_invoice=high_value_invoice,
            partial_payment_received=partial_payment_received,
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
