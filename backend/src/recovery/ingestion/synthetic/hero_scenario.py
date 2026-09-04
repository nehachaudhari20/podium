"""Hand-crafted hero multi-lane customer scenario for demos."""

from __future__ import annotations

from datetime import datetime, timedelta

from recovery.models.enums import Lane

HERO_CUSTOMER_ID = "cust_hero_001"
HERO_ANCHOR = datetime(2026, 2, 15, 10, 0, 0)


def hero_customer() -> dict:
    return {
        "customer_id": HERO_CUSTOMER_ID,
        "name": "NovaTech Solutions Pvt Ltd",
        "email": "finance@novatech-demo.in",
        "phone": "+919876543210",
        "segment": "b2b_smb",
        "opt_out": 0,
        "prior_contacts_7d": 1,
        "lifetime_value": 420000.0,
        "created_at": (HERO_ANCHOR - timedelta(days=800)).isoformat(),
    }


def hero_cases() -> list[dict]:
    window = HERO_ANCHOR + timedelta(days=14)
    return [
        {
            "case_id": "case_hero_sub_001",
            "customer_id": HERO_CUSTOMER_ID,
            "lane": Lane.SUBSCRIPTION_PAYMENT.value,
            "amount": 5000.0,
            "currency": "INR",
            "status": "open",
            "workflow_state": "detected",
            "created_at": HERO_ANCHOR.isoformat(),
            "recovery_window_end": window.isoformat(),
            "source_ref_id": "sub_hero_001",
            "failure_reason": "expired_card",
            "recoverability_hint": "medium",
            "days_overdue": None,
            "attempt_count": 2,
            "estimated_recovery_prob": None,
            "is_hero": 1,
        },
        {
            "case_id": "case_hero_chk_001",
            "customer_id": HERO_CUSTOMER_ID,
            "lane": Lane.CHECKOUT_ABANDONMENT.value,
            "amount": 20000.0,
            "currency": "INR",
            "status": "open",
            "workflow_state": "detected",
            "created_at": (HERO_ANCHOR - timedelta(hours=6)).isoformat(),
            "recovery_window_end": window.isoformat(),
            "source_ref_id": "chk_hero_001",
            "failure_reason": "checkout_high_intent_drop",
            "recoverability_hint": "high",
            "days_overdue": None,
            "attempt_count": 0,
            "estimated_recovery_prob": None,
            "is_hero": 1,
        },
        {
            "case_id": "case_hero_inv_001",
            "customer_id": HERO_CUSTOMER_ID,
            "lane": Lane.RECEIVABLE.value,
            "amount": 80000.0,
            "currency": "INR",
            "status": "open",
            "workflow_state": "detected",
            "created_at": (HERO_ANCHOR - timedelta(days=38)).isoformat(),
            "recovery_window_end": (HERO_ANCHOR + timedelta(days=30)).isoformat(),
            "source_ref_id": "inv_hero_001",
            "failure_reason": "invoice_aged_overdue",
            "recoverability_hint": "low",
            "days_overdue": 38,
            "attempt_count": 1,
            "estimated_recovery_prob": None,
            "is_hero": 1,
        },
    ]


def hero_source_records() -> dict:
    """Related entity rows for the hero customer."""
    return {
        "subscriptions": [
            {
                "subscription_id": "sub_hero_001",
                "customer_id": HERO_CUSTOMER_ID,
                "case_id": "case_hero_sub_001",
                "plan_name": "Pro Monthly",
                "amount": 5000.0,
                "currency": "INR",
                "billing_cycle": "monthly",
                "mandate_status": "failed",
                "failed_at": HERO_ANCHOR.isoformat(),
            }
        ],
        "checkout_sessions": [
            {
                "session_id": "chk_hero_001",
                "customer_id": HERO_CUSTOMER_ID,
                "case_id": "case_hero_chk_001",
                "cart_value": 20000.0,
                "currency": "INR",
                "stage": "payment_page",
                "intent_score": 0.82,
                "abandoned_at": (HERO_ANCHOR - timedelta(hours=6)).isoformat(),
                "items_count": 3,
            }
        ],
        "invoices": [
            {
                "invoice_id": "inv_hero_001",
                "customer_id": HERO_CUSTOMER_ID,
                "case_id": "case_hero_inv_001",
                "amount": 80000.0,
                "currency": "INR",
                "due_date": (HERO_ANCHOR - timedelta(days=38)).isoformat(),
                "days_overdue": 38,
                "status": "overdue",
                "invoice_type": "b2b",
            }
        ],
        "contact_history": [
            {
                "contact_id": "contact_hero_001",
                "customer_id": HERO_CUSTOMER_ID,
                "case_id": "case_hero_inv_001",
                "channel": "email",
                "direction": "outbound",
                "outcome": "no_response",
                "contacted_at": (HERO_ANCHOR - timedelta(days=10)).isoformat(),
            }
        ],
    }
