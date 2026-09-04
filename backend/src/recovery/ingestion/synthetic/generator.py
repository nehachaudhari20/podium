"""Synthetic dataset generator for Phase 1."""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from recovery.config import load_policy, load_recovery_budget
from recovery.db import connect, init_schema
from recovery.ingestion.synthetic.ground_truth import (
    PayAnywayFeatures,
    compute_p_pay_anyway,
    features_to_snapshot,
)
from recovery.ingestion.synthetic.hero_scenario import (
    hero_cases,
    hero_customer,
    hero_source_records,
)
from recovery.models.enums import Lane
from recovery.paths import DEFAULT_DB_PATH, GENERATED_DIR

LANE_TARGETS: dict[str, int] = {
    Lane.SUBSCRIPTION_PAYMENT.value: 150,
    Lane.CHECKOUT_ABANDONMENT.value: 100,
    Lane.RECEIVABLE.value: 50,
}

MULTI_CASE_CUSTOMER_COUNT = 18  # includes hero
MULTI_CASE_LANE_COMBOS: list[list[str]] = [
    [Lane.SUBSCRIPTION_PAYMENT.value, Lane.CHECKOUT_ABANDONMENT.value],
    [Lane.SUBSCRIPTION_PAYMENT.value, Lane.RECEIVABLE.value],
    [Lane.CHECKOUT_ABANDONMENT.value, Lane.RECEIVABLE.value],
    [
        Lane.SUBSCRIPTION_PAYMENT.value,
        Lane.CHECKOUT_ABANDONMENT.value,
        Lane.RECEIVABLE.value,
    ],
    [Lane.SUBSCRIPTION_PAYMENT.value, Lane.CHECKOUT_ABANDONMENT.value],
    [Lane.SUBSCRIPTION_PAYMENT.value, Lane.RECEIVABLE.value],
    [Lane.CHECKOUT_ABANDONMENT.value, Lane.RECEIVABLE.value],
    [Lane.SUBSCRIPTION_PAYMENT.value, Lane.CHECKOUT_ABANDONMENT.value, Lane.RECEIVABLE.value],
    [Lane.SUBSCRIPTION_PAYMENT.value, Lane.RECEIVABLE.value],
    [Lane.CHECKOUT_ABANDONMENT.value, Lane.RECEIVABLE.value],
    [Lane.SUBSCRIPTION_PAYMENT.value, Lane.CHECKOUT_ABANDONMENT.value],
    [Lane.SUBSCRIPTION_PAYMENT.value, Lane.CHECKOUT_ABANDONMENT.value, Lane.RECEIVABLE.value],
    [Lane.SUBSCRIPTION_PAYMENT.value, Lane.RECEIVABLE.value],
    [Lane.CHECKOUT_ABANDONMENT.value, Lane.RECEIVABLE.value],
    [Lane.SUBSCRIPTION_PAYMENT.value, Lane.CHECKOUT_ABANDONMENT.value],
    [Lane.SUBSCRIPTION_PAYMENT.value, Lane.CHECKOUT_ABANDONMENT.value, Lane.RECEIVABLE.value],
    [Lane.SUBSCRIPTION_PAYMENT.value, Lane.RECEIVABLE.value],
]

SUBSCRIPTION_FAILURES = [
    "transient_technical",
    "network_timeout",
    "issuer_timeout",
    "authentication_failure",
    "insufficient_funds",
    "expired_card",
    "invalid_card",
    "mandate_revoked",
    "repeated_failure",
]

CHECKOUT_FAILURES = [
    "checkout_payment_page_drop",
    "checkout_cart_abandon",
    "checkout_high_intent_drop",
]

RECEIVABLE_FAILURES = [
    "invoice_mild_overdue",
    "invoice_aged_overdue",
    "invoice_severely_overdue",
    "promise_missed",
]

SEGMENTS = ["b2c", "b2b_smb", "b2b_enterprise"]
SEGMENT_WEIGHTS = [0.55, 0.30, 0.15]


@dataclass
class GeneratedDataset:
    customers: list[dict[str, Any]] = field(default_factory=list)
    cases: list[dict[str, Any]] = field(default_factory=list)
    ground_truth: list[dict[str, Any]] = field(default_factory=list)
    payments: list[dict[str, Any]] = field(default_factory=list)
    subscriptions: list[dict[str, Any]] = field(default_factory=list)
    checkout_sessions: list[dict[str, Any]] = field(default_factory=list)
    invoices: list[dict[str, Any]] = field(default_factory=list)
    promises: list[dict[str, Any]] = field(default_factory=list)
    contacts: list[dict[str, Any]] = field(default_factory=list)
    action_log: list[dict[str, Any]] = field(default_factory=list)
    seed: int = 42

    @property
    def case_count(self) -> int:
        return len(self.cases)

    def lane_counts(self) -> Counter[str]:
        return Counter(case["lane"] for case in self.cases)


class SyntheticDataGenerator:
    def __init__(self, seed: int = 42, anchor: datetime | None = None) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.anchor = anchor or datetime(2026, 2, 1, 9, 0, 0)
        self._case_seq = 0
        self._cust_seq = 0
        self._payment_seq = 0
        self._sub_seq = 0
        self._chk_seq = 0
        self._inv_seq = 0
        self._promise_seq = 0
        self._contact_seq = 0
        self._action_seq = 0

    def generate(self) -> GeneratedDataset:
        dataset = GeneratedDataset(seed=self.seed)
        lane_counts: Counter[str] = Counter()

        # Hero scenario (counts toward multi-case and lane targets)
        dataset.customers.append(hero_customer())
        for case in hero_cases():
            dataset.cases.append(case)
            lane_counts[case["lane"]] += 1
        hero_sources = hero_source_records()
        dataset.subscriptions.extend(hero_sources["subscriptions"])
        dataset.checkout_sessions.extend(hero_sources["checkout_sessions"])
        dataset.invoices.extend(hero_sources["invoices"])
        dataset.contacts.extend(hero_sources["contact_history"])

        # Additional multi-case customers (17 beyond hero)
        for combo in MULTI_CASE_LANE_COMBOS:
            customer = self._make_customer()
            dataset.customers.append(customer)
            for lane in combo:
                case = self._make_case(customer, lane)
                dataset.cases.append(case)
                lane_counts[lane] += 1
                self._attach_source(dataset, customer, case)

        # Fill remaining lane quotas with single-case customers
        for lane, target in LANE_TARGETS.items():
            while lane_counts[lane] < target:
                customer = self._make_customer()
                dataset.customers.append(customer)
                case = self._make_case(customer, lane)
                dataset.cases.append(case)
                lane_counts[lane] += 1
                self._attach_source(dataset, customer, case)

        self._assign_ground_truth(dataset)
        return dataset

    def _next_case_id(self) -> str:
        self._case_seq += 1
        return f"case_{self._case_seq:04d}"

    def _next_customer_id(self) -> str:
        self._cust_seq += 1
        return f"cust_{self._cust_seq:04d}"

    def _make_customer(self) -> dict[str, Any]:
        segment = self.rng.choices(SEGMENTS, weights=SEGMENT_WEIGHTS, k=1)[0]
        opt_out = 1 if self.rng.random() < 0.04 else 0
        return {
            "customer_id": self._next_customer_id(),
            "name": f"Customer {self._cust_seq}",
            "email": f"customer{self._cust_seq}@demo.podium.in",
            "phone": f"+919{self.rng.randint(100000000, 999999999)}",
            "segment": segment,
            "opt_out": opt_out,
            "prior_contacts_7d": self.rng.randint(0, 4) if not opt_out else 0,
            "lifetime_value": round(self.rng.uniform(5000, 500000), 2),
            "created_at": (self.anchor - timedelta(days=self.rng.randint(30, 900))).isoformat(),
        }

    def _make_case(self, customer: dict[str, Any], lane: str) -> dict[str, Any]:
        created = self.anchor - timedelta(hours=self.rng.randint(1, 720))
        window_days = 14 if lane != Lane.RECEIVABLE.value else 30
        failure_reason, recoverability, days_overdue, intent_score = self._lane_features(lane)

        return {
            "case_id": self._next_case_id(),
            "customer_id": customer["customer_id"],
            "lane": lane,
            "amount": self._lane_amount(lane),
            "currency": "INR",
            "status": "open",
            "workflow_state": "detected",
            "created_at": created.isoformat(),
            "recovery_window_end": (created + timedelta(days=window_days)).isoformat(),
            "source_ref_id": f"{lane[:3]}_{self._case_seq:04d}",
            "failure_reason": failure_reason,
            "recoverability_hint": recoverability,
            "days_overdue": days_overdue,
            "attempt_count": self.rng.randint(0, 3),
            "estimated_recovery_prob": None,
            "is_hero": 0,
            "_intent_score": intent_score,
        }

    def _lane_features(
        self, lane: str
    ) -> tuple[str, str, int | None, float | None]:
        if lane == Lane.SUBSCRIPTION_PAYMENT.value:
            reason = self.rng.choice(SUBSCRIPTION_FAILURES)
            hint = {"transient_technical": "high", "network_timeout": "high"}.get(reason, "medium")
            if reason in {"mandate_revoked", "repeated_failure", "invalid_card"}:
                hint = "low"
            return reason, hint, None, None

        if lane == Lane.CHECKOUT_ABANDONMENT.value:
            reason = self.rng.choice(CHECKOUT_FAILURES)
            intent = self.rng.uniform(0.2, 0.95)
            hint = "high" if intent > 0.7 else "medium" if intent > 0.45 else "low"
            return reason, hint, None, intent

        reason = self.rng.choice(RECEIVABLE_FAILURES)
        if reason == "invoice_mild_overdue":
            days = self.rng.randint(1, 14)
        elif reason == "invoice_aged_overdue":
            days = self.rng.randint(15, 45)
        elif reason == "invoice_severely_overdue":
            days = self.rng.randint(46, 120)
        else:
            days = self.rng.randint(20, 60)
        hint = "low" if days > 30 else "medium"
        return reason, hint, days, None

    def _lane_amount(self, lane: str) -> float:
        if lane == Lane.SUBSCRIPTION_PAYMENT.value:
            return float(self.rng.choice([499, 999, 1499, 2999, 4999, 9999]))
        if lane == Lane.CHECKOUT_ABANDONMENT.value:
            return round(self.rng.uniform(800, 45000), 2)
        return round(self.rng.uniform(5000, 250000), 2)

    def _attach_source(
        self, dataset: GeneratedDataset, customer: dict[str, Any], case: dict[str, Any]
    ) -> None:
        lane = case["lane"]
        if lane == Lane.SUBSCRIPTION_PAYMENT.value:
            sub_id = f"sub_{self._sub_seq + 1:05d}"
            self._sub_seq += 1
            dataset.subscriptions.append(
                {
                    "subscription_id": sub_id,
                    "customer_id": customer["customer_id"],
                    "case_id": case["case_id"],
                    "plan_name": self.rng.choice(["Basic", "Pro", "Enterprise"]),
                    "amount": case["amount"],
                    "currency": "INR",
                    "billing_cycle": self.rng.choice(["monthly", "yearly"]),
                    "mandate_status": "failed",
                    "failed_at": case["created_at"],
                }
            )
            case["source_ref_id"] = sub_id
            self._payment_seq += 1
            dataset.payments.append(
                {
                    "payment_id": f"pay_{self._payment_seq:05d}",
                    "customer_id": customer["customer_id"],
                    "case_id": case["case_id"],
                    "amount": case["amount"],
                    "currency": "INR",
                    "status": "failed",
                    "failure_reason": case["failure_reason"],
                    "payment_method": self.rng.choice(["card", "upi", "netbanking"]),
                    "attempted_at": case["created_at"],
                }
            )
        elif lane == Lane.CHECKOUT_ABANDONMENT.value:
            session_id = f"chk_{self._chk_seq + 1:05d}"
            self._chk_seq += 1
            intent = case.pop("_intent_score", self.rng.uniform(0.2, 0.95))
            dataset.checkout_sessions.append(
                {
                    "session_id": session_id,
                    "customer_id": customer["customer_id"],
                    "case_id": case["case_id"],
                    "cart_value": case["amount"],
                    "currency": "INR",
                    "stage": self.rng.choice(["cart", "shipping", "payment_page"]),
                    "intent_score": round(intent, 3),
                    "abandoned_at": case["created_at"],
                    "items_count": self.rng.randint(1, 6),
                }
            )
            case["source_ref_id"] = session_id
        else:
            inv_id = f"inv_{self._inv_seq + 1:05d}"
            self._inv_seq += 1
            due = datetime.fromisoformat(case["created_at"]) - timedelta(days=case["days_overdue"] or 0)
            dataset.invoices.append(
                {
                    "invoice_id": inv_id,
                    "customer_id": customer["customer_id"],
                    "case_id": case["case_id"],
                    "amount": case["amount"],
                    "currency": "INR",
                    "due_date": due.date().isoformat(),
                    "days_overdue": case["days_overdue"] or 0,
                    "status": "overdue",
                    "invoice_type": "b2b" if customer["segment"] != "b2c" else "b2c",
                }
            )
            case["source_ref_id"] = inv_id
            if case["failure_reason"] == "promise_missed":
                self._promise_seq += 1
                promised = round(case["amount"] * self.rng.uniform(0.5, 1.0), 2)
                dataset.promises.append(
                    {
                        "promise_id": f"promise_{self._promise_seq:05d}",
                        "case_id": case["case_id"],
                        "customer_id": customer["customer_id"],
                        "promised_amount": promised,
                        "promise_date": (due + timedelta(days=5)).isoformat(),
                        "due_date": (due + timedelta(days=12)).isoformat(),
                        "status": "missed",
                        "created_at": (due + timedelta(days=5)).isoformat(),
                    }
                )
            if self.rng.random() < 0.35:
                self._contact_seq += 1
                dataset.contacts.append(
                    {
                        "contact_id": f"contact_{self._contact_seq:05d}",
                        "customer_id": customer["customer_id"],
                        "case_id": case["case_id"],
                        "channel": self.rng.choice(["email", "whatsapp", "sms"]),
                        "direction": "outbound",
                        "outcome": self.rng.choice(["no_response", "opened", "replied"]),
                        "contacted_at": (
                            datetime.fromisoformat(case["created_at"]) + timedelta(days=2)
                        ).isoformat(),
                    }
                )

        case.pop("_intent_score", None)

        if self.rng.random() < 0.15:
            self._action_seq += 1
            dataset.action_log.append(
                {
                    "action_id": f"action_{self._action_seq:05d}",
                    "case_id": case["case_id"],
                    "action_type": self.rng.choice(["retry_payment", "send_email", "wait_and_retry"]),
                    "channel": "system",
                    "cost": float(self.rng.choice([1, 2, 5])),
                    "outcome": self.rng.choice(["failed", "pending", "no_response"]),
                    "executed_at": case["created_at"],
                }
            )

    def _assign_ground_truth(self, dataset: GeneratedDataset) -> None:
        customers_by_id = {c["customer_id"]: c for c in dataset.customers}
        intent_by_case: dict[str, float] = {
            row["case_id"]: row["intent_score"]
            for row in dataset.checkout_sessions
            if row.get("case_id")
        }

        for case in dataset.cases:
            customer = customers_by_id[case["customer_id"]]
            features = PayAnywayFeatures(
                lane=case["lane"],
                failure_reason=case["failure_reason"],
                recoverability_hint=case["recoverability_hint"],
                days_overdue=case["days_overdue"],
                attempt_count=int(case["attempt_count"]),
                opt_out=bool(customer["opt_out"]),
                prior_contacts_7d=int(customer["prior_contacts_7d"]),
                intent_score=intent_by_case.get(case["case_id"]),
                segment=customer["segment"],
                promise_missed=case["failure_reason"] == "promise_missed",
            )
            case_seed = int(hashlib.md5(case["case_id"].encode()).hexdigest()[:8], 16) ^ self.seed
            case_rng = random.Random(case_seed)
            p_pay = compute_p_pay_anyway(features, case_rng)
            dataset.ground_truth.append(
                {
                    "case_id": case["case_id"],
                    "p_pay_anyway": p_pay,
                    "generation_seed": self.seed,
                    "feature_snapshot": features_to_snapshot(features),
                }
            )


def persist_dataset(
    dataset: GeneratedDataset,
    db_path: Path | None = None,
    export_json: bool = True,
) -> Path:
    path = db_path or DEFAULT_DB_PATH
    conn = connect(path)
    init_schema(conn)

    conn.execute("DELETE FROM recovery_action_log")
    conn.execute("DELETE FROM contact_history")
    conn.execute("DELETE FROM promises_to_pay")
    conn.execute("DELETE FROM invoices")
    conn.execute("DELETE FROM checkout_sessions")
    conn.execute("DELETE FROM subscriptions")
    conn.execute("DELETE FROM payments")
    conn.execute("DELETE FROM case_ground_truth")
    conn.execute("DELETE FROM recovery_cases")
    conn.execute("DELETE FROM customers")
    conn.execute("DELETE FROM merchant_budgets")

    _insert_many(conn, "customers", dataset.customers)
    _insert_many(conn, "recovery_cases", [_case_row(c) for c in dataset.cases])
    _insert_many(
        conn,
        "case_ground_truth",
        [
            {
                **gt,
                "feature_snapshot": json.dumps(gt["feature_snapshot"]),
            }
            for gt in dataset.ground_truth
        ],
    )
    _insert_many(conn, "payments", dataset.payments)
    _insert_many(conn, "subscriptions", dataset.subscriptions)
    _insert_many(conn, "checkout_sessions", dataset.checkout_sessions)
    _insert_many(conn, "invoices", dataset.invoices)
    _insert_many(conn, "promises_to_pay", dataset.promises)
    _insert_many(conn, "contact_history", dataset.contacts)
    _insert_many(conn, "recovery_action_log", dataset.action_log)

    budget = load_recovery_budget()
    conn.execute(
        """
        INSERT INTO merchant_budgets (
            budget_id, contact_capacity_per_day, voice_call_slots_per_day,
            human_escalation_hours_per_day, discount_budget_total,
            retry_attempts_pool, effective_from
        ) VALUES (1, ?, ?, ?, ?, ?, ?)
        """,
        (
            budget["contact_capacity_per_day"],
            budget["voice_call_slots_per_day"],
            budget["human_escalation_hours_per_day"],
            budget["discount_budget_total"],
            budget["retry_attempts_pool"],
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    if export_json:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        summary_path = GENERATED_DIR / "dataset_summary.json"
        summary_path.write_text(
            json.dumps(build_summary(dataset), indent=2),
            encoding="utf-8",
        )

    return path


def _case_row(case: dict[str, Any]) -> dict[str, Any]:
    row = dict(case)
    row.pop("_intent_score", None)
    return row


def _insert_many(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in columns)
    col_sql = ", ".join(columns)
    sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
    conn.executemany(sql, [tuple(row[col] for col in columns) for row in rows])


def build_summary(dataset: GeneratedDataset) -> dict[str, Any]:
    lane_counts = dataset.lane_counts()
    total_at_risk = sum(c["amount"] for c in dataset.cases)
    p_values = [g["p_pay_anyway"] for g in dataset.ground_truth]

    cases_by_customer: dict[str, list[str]] = defaultdict(list)
    for case in dataset.cases:
        cases_by_customer[case["customer_id"]].append(case["case_id"])

    multi_case_customers = {
        cid: case_ids for cid, case_ids in cases_by_customer.items() if len(case_ids) >= 2
    }

    by_lane_p: dict[str, list[float]] = defaultdict(list)
    gt_by_case = {g["case_id"]: g["p_pay_anyway"] for g in dataset.ground_truth}
    for case in dataset.cases:
        by_lane_p[case["lane"]].append(gt_by_case[case["case_id"]])

    return {
        "seed": dataset.seed,
        "total_cases": dataset.case_count,
        "lane_counts": dict(lane_counts),
        "lane_targets": LANE_TARGETS,
        "total_customers": len(dataset.customers),
        "multi_case_customers": len(multi_case_customers),
        "multi_case_customer_ids": list(multi_case_customers.keys())[:5],
        "hero_case_ids": [c["case_id"] for c in dataset.cases if c.get("is_hero")],
        "total_revenue_at_risk_inr": round(total_at_risk, 2),
        "p_pay_anyway": {
            "mean": round(sum(p_values) / len(p_values), 4),
            "min": round(min(p_values), 4),
            "max": round(max(p_values), 4),
            "by_lane_mean": {
                lane: round(sum(vals) / len(vals), 4) for lane, vals in by_lane_p.items()
            },
        },
        "entity_counts": {
            "payments": len(dataset.payments),
            "subscriptions": len(dataset.subscriptions),
            "checkout_sessions": len(dataset.checkout_sessions),
            "invoices": len(dataset.invoices),
            "promises_to_pay": len(dataset.promises),
            "contacts": len(dataset.contacts),
            "recovery_actions": len(dataset.action_log),
        },
    }


def print_summary(dataset: GeneratedDataset, db_path: Path) -> None:
    summary = build_summary(dataset)
    policy = load_policy()

    print("=" * 60)
    print("Podium — Phase 1 Synthetic Dataset Summary")
    print("=" * 60)
    print(f"Seed:              {summary['seed']}")
    print(f"Database:          {db_path}")
    print(f"Total cases:       {summary['total_cases']}")
    print(f"  subscription:    {summary['lane_counts'].get('subscription_payment', 0)} (target 150)")
    print(f"  checkout:        {summary['lane_counts'].get('checkout_abandonment', 0)} (target 100)")
    print(f"  receivable:      {summary['lane_counts'].get('receivable', 0)} (target 50)")
    print(f"Customers:         {summary['total_customers']}")
    print(f"Multi-case (2+):   {summary['multi_case_customers']} customers")
    print(f"Revenue at risk:   INR {summary['total_revenue_at_risk_inr']:,.2f}")
    print(f"p_pay_anyway mean: {summary['p_pay_anyway']['mean']:.3f} (evaluator-only)")
    print(f"  by lane:         {summary['p_pay_anyway']['by_lane_mean']}")
    print(f"Hero cases:        {', '.join(summary['hero_case_ids'])}")
    print(f"Policy loaded:     max_retries={policy['max_retries']}, "
          f"discount_ceiling={policy['discount_ceiling_pct']}%")
    print("=" * 60)


def generate_and_persist(seed: int = 42, db_path: Path | None = None) -> GeneratedDataset:
    generator = SyntheticDataGenerator(seed=seed)
    dataset = generator.generate()
    path = persist_dataset(dataset, db_path=db_path)
    print_summary(dataset, path)
    return dataset
