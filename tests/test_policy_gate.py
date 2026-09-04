"""Phase 2 — policy gate unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from podium.ingestion.customer_loader import CustomerContext
from podium.models.case import RecoveryCaseRuntime
from podium.models.enums import Lane
from podium.models.recovery_types import RecoveryAction
from podium.policy.gate import check_policy, select_first_allowed_action


def _case(attempt_count: int = 0) -> RecoveryCaseRuntime:
    now = datetime(2026, 2, 1, 10, 0, 0)
    return RecoveryCaseRuntime(
        case_id="case_pol_001",
        customer_id="cust_pol_001",
        lane=Lane.SUBSCRIPTION_PAYMENT.value,
        amount=2499.0,
        currency="INR",
        status="open",
        workflow_state="diagnosed",
        created_at=now,
        recovery_window_end=now + timedelta(days=14),
        source_ref_id="sub_pol_001",
        failure_reason="insufficient_funds",
        recoverability_hint="medium",
        days_overdue=None,
        attempt_count=attempt_count,
        estimated_recovery_prob=None,
    )


def _customer(opt_out: bool = False, prior_contacts: int = 0) -> CustomerContext:
    return CustomerContext(
        customer_id="cust_pol_001",
        opt_out=opt_out,
        prior_contacts_7d=prior_contacts,
        segment="b2c",
    )


RETRY = RecoveryAction("retry_24h", "Retry", "system", is_retry=True, retry_delay_hours=24)
CONTACT = RecoveryAction("payment_method_update", "Update method", "email", is_contact=True)


def test_retry_allowed_under_limit():
    result = check_policy(_case(attempt_count=1), RETRY, _customer())
    assert result.allowed is True


def test_retry_blocked_at_max_retries():
    result = check_policy(_case(attempt_count=3), RETRY, _customer())
    assert result.allowed is False
    assert "Maximum retry count" in result.reason


def test_opt_out_blocks_contact():
    result = check_policy(_case(), CONTACT, _customer(opt_out=True))
    assert result.allowed is False
    assert "opted out" in result.reason.lower()


def test_opt_out_does_not_block_retry():
    result = check_policy(_case(), RETRY, _customer(opt_out=True))
    assert result.allowed is True


def test_contact_cap_blocks_outreach():
    result = check_policy(_case(), CONTACT, _customer(prior_contacts=3))
    assert result.allowed is False
    assert "contacts in 7 days" in result.reason


def test_cooldown_blocks_retry():
    now = datetime(2026, 2, 1, 10, 0, 0)
    last_retry = now - timedelta(hours=6)
    result = check_policy(_case(), RETRY, _customer(), last_retry_at=last_retry, now=now)
    assert result.allowed is False
    assert "cooldown" in result.reason.lower()


def test_select_first_allowed_skips_blocked():
    actions = [
        RecoveryAction("retry_24h", "Retry", "system", is_retry=True, retry_delay_hours=24),
        CONTACT,
    ]
    case = _case(attempt_count=3)
    selected, _, checks = select_first_allowed_action(case, actions, _customer())
    assert selected is not None
    assert selected.action_id == "payment_method_update"
    assert checks[0].allowed is False
    assert checks[1].allowed is True
