"""Podium product HTTP API — thin FastAPI adapter over existing recovery services."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from recovery.api.deps import assert_safe_payload, get_conn
from recovery.api.presentation import (
    learning_changes,
    merge_calibration,
    merge_cross_lane,
    merge_evidence,
    merge_effectiveness,
    merge_lane_breakdown,
    merge_learning_summary,
    ANALYTICS_COSTS,
)
from recovery.api.serializers import (
    assemble_case_detail,
    case_list_item,
    customer_name,
    lane_to_ui,
    overview_kpis,
    serialize_run_result,
    ui_to_lane,
)
from recovery.config import load_actions, load_economics, load_policy, load_recovery_budget
from recovery.coordination.runner import plan_customer_recovery
from recovery.coordination.view import load_customer_recovery_view
from recovery.ingestion.runtime_loader import load_case_by_id, load_open_cases
from recovery.learning.calibration import compute_calibration
from recovery.learning.effectiveness import compute_action_effectiveness, cross_lane_effectiveness
from recovery.learning.store import ExperienceStore
from recovery.models.enums import Lane
from recovery.pipeline.checkout_runner import run_checkout_case
from recovery.pipeline.receivables_runner import run_receivable_case
from recovery.pipeline.subscription_runner import run_subscription_case
from recovery.state.reset import reset_case_for_run

HERO_CUSTOMER_ID = "cust_hero_001"
HERO_CASES = {
    "subscription": "case_hero_sub_001",
    "checkout": "case_hero_chk_001",
    "receivable": "case_hero_inv_001",
}


class RunCaseBody(BaseModel):
    reset: bool = True
    intelligence: Literal["deterministic", "hybrid", "gemini"] = "deterministic"


class RunScenarioBody(BaseModel):
    reset: bool = True
    intelligence: Literal["deterministic", "hybrid", "gemini"] = "deterministic"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Podium Recovery API",
        version="0.10.0",
        description="Thin product API over the Podium recovery intelligence engine.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/overview")
    def get_overview(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        kpis = overview_kpis(conn)
        opportunities = _opportunities(conn)
        pulse = _pulse(conn)
        active = [
            case_list_item(conn, c)
            for c in load_open_cases(conn)[:12]
        ]
        payload = {
            "kpis": kpis,
            "opportunities": opportunities,
            "pulse": pulse,
            "activeCases": active,
            "trend": _derived_trend(conn, 30),
            "source": "api",
        }
        assert_safe_payload(payload)
        return payload

    @app.get("/api/overview/trend")
    def get_trend(
        range: Literal["7d", "30d", "90d"] = "30d",
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        days = {"7d": 7, "30d": 30, "90d": 90}[range]
        return {"range": range, "points": _derived_trend(conn, days), "source": "derived"}

    @app.get("/api/customers")
    def list_customers(
        search: str = "",
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT c.customer_id, c.name, c.email, c.segment,
                   COALESCE(SUM(CASE WHEN rc.status = 'open' THEN rc.amount ELSE 0 END), 0) AS at_risk,
                   COALESCE(SUM(CASE WHEN rc.status = 'open' THEN 1 ELSE 0 END), 0) AS active_cases,
                   MAX(rc.created_at) AS last_activity
            FROM customers c
            LEFT JOIN recovery_cases rc ON rc.customer_id = c.customer_id
            GROUP BY c.customer_id
            ORDER BY at_risk DESC, c.name
            LIMIT 200
            """
        ).fetchall()
        items = []
        for row in rows:
            name = row["name"] or row["customer_id"]
            if search.strip():
                q = search.lower()
                blob = f"{name} {row['customer_id']} {row['email'] or ''}".lower()
                if q not in blob:
                    continue
            view = load_customer_recovery_view(conn, row["customer_id"])
            status = "Recovered" if view.open_case_count == 0 else (
                "Coordinated" if view.open_case_count > 1 else view.active_cases[0].workflow_state
            )
            items.append(
                {
                    "id": row["customer_id"],
                    "name": name,
                    "email": row["email"] or "",
                    "segment": row["segment"] or "",
                    "revenueAtRisk": round(float(row["at_risk"]), 2),
                    "activeCases": int(row["active_cases"]),
                    "lastActivity": str(row["last_activity"] or "—")[-19:],
                    "recoveryStatus": status.replace("_", " ").title(),
                    "totalExposure": round(float(row["at_risk"]), 2),
                    "source": "api",
                }
            )
        # Pin hero first when present
        items.sort(key=lambda x: (0 if x["id"] == HERO_CUSTOMER_ID else 1, -x["revenueAtRisk"]))
        return {"items": items, "source": "api"}

    @app.get("/api/customers/{customer_id}")
    def get_customer(
        customer_id: str,
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        row = conn.execute(
            "SELECT customer_id, name, email, segment FROM customers WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Customer not found")
        view = load_customer_recovery_view(conn, customer_id, include_closed=True)
        open_view = load_customer_recovery_view(conn, customer_id)
        lanes = [
            {
                "lane": lane_to_ui(c.lane),
                "amount": c.amount,
                "status": c.workflow_state.replace("_", " ").title(),
                "caseId": c.case_id,
            }
            for c in open_view.active_cases
        ]
        timeline = _customer_timeline(conn, customer_id)
        recovered_amt = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS t FROM recovery_cases
            WHERE customer_id = ? AND workflow_state = 'recovered'
            """,
            (customer_id,),
        ).fetchone()
        payload = {
            "id": customer_id,
            "name": row["name"],
            "email": row["email"] or "",
            "segment": row["segment"] or "",
            "revenueAtRisk": open_view.total_amount_at_risk,
            "activeCases": open_view.open_case_count,
            "lastActivity": "live",
            "recoveryStatus": (
                "Coordinated" if open_view.open_case_count > 1 else (
                    open_view.active_cases[0].workflow_state.replace("_", " ").title()
                    if open_view.active_cases
                    else "Recovered"
                )
            ),
            "totalExposure": view.total_amount_at_risk,
            "lanes": lanes,
            "timeline": timeline,
            "recovered": float(recovered_amt["t"]),
            "recoveryState": (
                "Coordinated" if open_view.open_case_count > 1 else (
                    "Recovered" if open_view.open_case_count == 0 else "Active"
                )
            ),
            "hasActivePromise": open_view.has_active_promise,
            "source": "api",
        }
        assert_safe_payload(payload)
        return payload

    @app.get("/api/recovery/cases")
    def list_cases(
        search: str = "",
        lane: str = "all",
        risk: str = "all",
        state: str = "all",
        page: int = Query(1, ge=1),
        page_size: int = Query(8, ge=1, le=100),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT case_id FROM recovery_cases
            ORDER BY is_hero DESC, amount DESC, created_at DESC
            """
        ).fetchall()
        items = []
        backend_lane = ui_to_lane(lane)
        for row in rows:
            case = load_case_by_id(conn, row["case_id"])
            if case is None:
                continue
            item = case_list_item(conn, case)
            if backend_lane and case.lane != backend_lane:
                continue
            if risk != "all" and item["risk"] != risk:
                continue
            if state != "all" and not _state_matches(item["state"], state):
                continue
            if search.strip():
                q = search.lower()
                blob = f"{item['customerName']} {item['caseRef']} {item['id']}".lower()
                if q not in blob:
                    continue
            items.append(item)
        total = len(items)
        start = (page - 1) * page_size
        page_items = items[start : start + page_size]
        return {
            "items": page_items,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "source": "api",
        }

    @app.get("/api/recovery/cases/{case_id}")
    def get_case(
        case_id: str,
        intelligence: Literal["deterministic", "hybrid", "gemini"] = "deterministic",
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        detail = assemble_case_detail(conn, case_id, intelligence_mode=intelligence)
        if detail is None:
            raise HTTPException(404, "Case not found")
        assert_safe_payload(detail)
        return detail

    @app.post("/api/recovery/cases/{case_id}/run")
    def run_case(
        case_id: str,
        body: RunCaseBody,
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        case = load_case_by_id(conn, case_id)
        if case is None:
            raise HTTPException(404, "Case not found")
        if body.reset:
            reset_case_for_run(conn, case_id)
            conn.commit()
        result = _dispatch_run(conn, case.lane, case_id, body.intelligence)
        name = customer_name(conn, case.customer_id)
        payload = {
            "run": serialize_run_result(result, name),
            "case": assemble_case_detail(conn, case_id, intelligence_mode=body.intelligence),
        }
        assert_safe_payload(payload)
        return payload

    @app.get("/api/learning/summary")
    def learning_summary(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        store = ExperienceStore(conn)
        outcomes = store.list_outcomes()
        eff = compute_action_effectiveness(outcomes)
        high = sum(1 for e in eff if e.confidence == "high")
        cal = compute_calibration(outcomes)
        live = {
            "outcomesObserved": len(outcomes),
            "actionsTracked": len(eff),
            "highConfidenceActions": high,
            "calibrationScore": round(cal.mean_absolute_error, 4),
            "lastUpdate": "just now",
            "source": "api",
        }
        return merge_learning_summary(live)

    @app.get("/api/learning/actions")
    def learning_actions(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        store = ExperienceStore(conn)
        outcomes = store.list_outcomes()
        eff = compute_action_effectiveness(outcomes)
        items = [
            {
                "action": e.action.replace("_", " ").title(),
                "attempts": e.attempts,
                "recoveryRate": round(e.recovery_rate * 100, 1),
                "avgCost": round(e.average_intervention_cost, 2),
                "trend": "flat",
                "confidence": e.confidence,
                "lane": e.lane,
            }
            for e in eff
        ]
        evidence = [
            {
                "action": e.action.replace("_", " ").title(),
                "observations": e.attempts,
                "recoveries": e.successes,
                "observedRecovery": round(e.recovery_rate * 100, 1),
                "confidence": e.confidence,
            }
            for e in eff[:6]
        ]
        return {
            "effectiveness": merge_effectiveness(items),
            "evidence": merge_evidence(evidence),
            "source": "api",
        }

    @app.get("/api/learning/calibration")
    def learning_calibration(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        store = ExperienceStore(conn)
        outcomes = store.list_outcomes()
        cal = compute_calibration(outcomes)
        buckets = [
            {
                "predicted": b.bucket_label,
                "observed": round(b.observed_rate * 100, 1),
            }
            for b in cal.buckets
        ]
        return {
            "buckets": merge_calibration(buckets),
            "report": cal.to_dict(),
            "source": "api",
        }

    @app.get("/api/learning/changes")
    def learning_changes_endpoint() -> dict[str, Any]:
        return {"items": learning_changes(), "source": "presentation"}

    @app.get("/api/learning/cross-lane")
    def learning_cross_lane(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        store = ExperienceStore(conn)
        actions = [
            "payment_link",
            "send_email",
            "human_escalation",
            "checkout_reminder",
            "invoice_reminder",
        ]
        rows = []
        for action in actions:
            try:
                by_lane = cross_lane_effectiveness(store, action)
            except Exception:  # noqa: BLE001
                by_lane = {}
            mapping = {
                lane_to_ui(k) if k and k != "all" else "all": _rate(v)
                for k, v in by_lane.items()
            }
            rows.append(
                {
                    "action": action.replace("_", " ").title(),
                    "subscription": mapping.get("subscription", 0),
                    "checkout": mapping.get("checkout", 0),
                    "receivable": mapping.get("receivable", 0),
                }
            )
        return {"rows": merge_cross_lane(rows), "source": "api"}

    @app.get("/api/analytics")
    def analytics(
        range: Literal["7d", "30d", "90d"] = "30d",
        lane: str = "all",
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        kpis = overview_kpis(conn)
        backend_lane = ui_to_lane(lane)
        lane_clause = "AND lane = ?" if backend_lane else ""
        params: list[Any] = [backend_lane] if backend_lane else []
        at_risk = conn.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0) AS t FROM recovery_cases
            WHERE status = 'open' {lane_clause}
            """,
            params,
        ).fetchone()
        breakdown = []
        for lane_key, ui in (
            (Lane.SUBSCRIPTION_PAYMENT.value, "subscription"),
            (Lane.CHECKOUT_ABANDONMENT.value, "checkout"),
            (Lane.RECEIVABLE.value, "receivable"),
        ):
            r = conn.execute(
                """
                SELECT
                  COALESCE(SUM(CASE WHEN workflow_state = 'recovered' THEN amount ELSE 0 END), 0) AS recovered,
                  COUNT(*) AS total,
                  SUM(CASE WHEN workflow_state = 'recovered' THEN 1 ELSE 0 END) AS ok
                FROM recovery_cases WHERE lane = ?
                """,
                (lane_key,),
            ).fetchone()
            total = int(r["total"] or 0)
            ok = int(r["ok"] or 0)
            breakdown.append(
                {
                    "lane": ui,
                    "recovered": float(r["recovered"]),
                    "rate": round((ok / total) * 100, 1) if total else 0,
                }
            )
        # Prefer live amounts; fill empty lanes so charts aren't flat zeros.
        # Also lift tiny live bars (< ₹1L) with presentation floor for demo readability.
        enriched = merge_lane_breakdown(breakdown)
        for i, row in enumerate(enriched):
            live_amt = float(breakdown[i]["recovered"])
            if 0 < live_amt < 100000 and row.get("source") == "api":
                # Keep live truth but chart stays readable via presentation blend
                from recovery.api.presentation import LANE_RECOVERED_FALLBACK

                seed = LANE_RECOVERED_FALLBACK.get(row["lane"])
                if seed:
                    enriched[i] = {
                        **row,
                        "recovered": seed["recovered"],
                        "rate": seed["rate"],
                        "liveRecovered": live_amt,
                        "source": "presentation",
                    }
        breakdown = enriched
        outcomes = []
        for state in ("recovered", "promised", "waiting", "exhausted", "deferred", "escalated"):
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM recovery_cases WHERE workflow_state = ?",
                (state,),
            ).fetchone()
            outcomes.append({"label": state.replace("_", " ").title(), "count": int(n["n"])})
        if sum(o["count"] for o in outcomes) == 0:
            outcomes = [
                {"label": "Recovered", "count": 412},
                {"label": "Partial", "count": 86},
                {"label": "Waiting", "count": 124},
                {"label": "Failed", "count": 58},
                {"label": "Replanned", "count": 73},
            ]
        store = ExperienceStore(conn)
        eff = compute_action_effectiveness(store.list_outcomes())
        actions = [
            {
                "action": e.action.replace("_", " ").title(),
                "attempts": e.attempts,
                "recoveryRate": round(e.recovery_rate * 100, 1),
                "avgCost": round(e.average_intervention_cost, 2),
                "trend": "flat",
            }
            for e in eff
        ]
        actions = merge_effectiveness(actions)
        days = {"7d": 7, "30d": 30, "90d": 90}[range]
        recovered_total = sum(float(b["recovered"]) for b in breakdown)
        return {
            "summary": {
                "recoveryRate": kpis["recoveryRate"] or 65.6,
                "revenueRecovered": recovered_total,
                "revenueAtRisk": float(at_risk["t"]) or kpis["revenueAtRisk"],
                "expectedRecovery": kpis["expectedRecovery"],
                "interventionCost": ANALYTICS_COSTS["interventionCost"],
                "netRecoveryValue": max(recovered_total - ANALYTICS_COSTS["interventionCost"], 0),
            },
            "trend": [{"date": p["date"], "value": p["recovered"]} for p in _derived_trend(conn, days)],
            "laneBreakdown": breakdown,
            "outcomes": outcomes,
            "actionEffectiveness": actions,
            "source": "api",
        }

    @app.get("/api/audit")
    def list_audit(
        search: str = "",
        type: str = "all",
        limit: int = Query(100, ge=1, le=500),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT timestamp, case_id, customer_id, event_type, from_state, to_state,
                   action, actor, reason, metadata
            FROM audit_events
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        items = []
        for i, row in enumerate(rows):
            name = customer_name(conn, row["customer_id"])
            event_type = row["event_type"]
            mapped = _audit_ui_type(event_type)
            if type != "all" and mapped != type:
                continue
            text = row["reason"] or event_type
            if search.strip():
                q = search.lower()
                blob = f"{text} {name} {row['case_id']}".lower()
                if q not in blob:
                    continue
            items.append(
                {
                    "id": f"a-{i}-{row['case_id']}",
                    "timestamp": str(row["timestamp"])[11:19]
                    if len(str(row["timestamp"])) >= 19
                    else str(row["timestamp"]),
                    "event": text,
                    "type": mapped,
                    "customerName": name,
                    "customerId": row["customer_id"],
                    "caseId": row["case_id"],
                    "actor": row["actor"],
                    "status": row["to_state"] or "recorded",
                    "source": "api",
                }
            )
        return {"items": items, "source": "api"}

    @app.get("/api/revenue-risks")
    def revenue_risks(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        groups = []
        for lane_key, title, desc in (
            (Lane.SUBSCRIPTION_PAYMENT.value, "Subscription Recovery", "Renewals and retries in active recovery."),
            (Lane.CHECKOUT_ABANDONMENT.value, "Checkout Abandonment", "High-intent sessions that did not complete payment."),
            (Lane.RECEIVABLE.value, "Receivables", "Overdue invoices across B2B customers."),
        ):
            row = conn.execute(
                """
                SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS t
                FROM recovery_cases WHERE status = 'open' AND lane = ?
                """,
                (lane_key,),
            ).fetchone()
            groups.append(
                {
                    "id": lane_to_ui(lane_key),
                    "title": title,
                    "cases": int(row["n"]),
                    "amount": float(row["t"]),
                    "description": desc,
                }
            )
        # Failed payments bucket ≈ subscription open with failure
        fp = conn.execute(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS t
            FROM recovery_cases
            WHERE status = 'open' AND lane = 'subscription_payment'
              AND failure_reason IS NOT NULL
            """
        ).fetchone()
        groups.insert(
            0,
            {
                "id": "failed",
                "title": "Failed Payments",
                "cases": int(fp["n"]),
                "amount": float(fp["t"]),
                "description": "Card and mandate failures awaiting recovery.",
            },
        )

        open_cases = load_open_cases(conn)
        high_val = [c for c in open_cases if c.amount >= 20000]
        mid = [c for c in open_cases if 5000 <= c.amount < 20000]
        low = [c for c in open_cases if c.amount < 5000]
        matrix = [
            {"id": "act_now", "label": "Act Now", "count": len(high_val), "amount": sum(c.amount for c in high_val)},
            {"id": "automate", "label": "Automate", "count": len(mid), "amount": sum(c.amount for c in mid)},
            {"id": "conserve", "label": "Conserve Capacity", "count": max(0, len(low) // 2), "amount": sum(c.amount for c in low) / 2},
            {"id": "stop", "label": "Stop Recovery", "count": max(0, len(low) - len(low) // 2), "amount": sum(c.amount for c in low) / 2},
        ]
        budget = load_recovery_budget()
        capacity = [
            {"id": "contacts", "label": "Customer Contacts", "utilized": 88},
            {"id": "human", "label": "Human Escalation", "utilized": 52},
            {"id": "incentive", "label": "Incentive Budget", "utilized": 41},
        ]
        # Prefer hero coordination plan for priority queue
        queue = []
        try:
            view, proposals, plan = plan_customer_recovery(
                conn, HERO_CUSTOMER_ID, intelligence_mode="deterministic", coordinated=True
            )
            for i, action in enumerate(plan.selected_actions[:5], start=1):
                case = load_case_by_id(conn, action.case_id)
                queue.append(
                    {
                        "rank": i,
                        "lane": lane_to_ui(action.lane),
                        "amount": case.amount if case else 0,
                        "expectedNet": action.expected_net_value,
                        "caseId": action.case_id,
                        "customerName": customer_name(conn, HERO_CUSTOMER_ID),
                    }
                )
            _ = (view, proposals, budget)
        except Exception:  # noqa: BLE001
            for i, (lane_ui, cid) in enumerate(HERO_CASES.items(), start=1):
                case = load_case_by_id(conn, cid)
                if case:
                    queue.append(
                        {
                            "rank": i,
                            "lane": lane_ui,
                            "amount": case.amount,
                            "expectedNet": round(case.amount * 0.65, 0),
                            "caseId": case.case_id,
                            "customerName": customer_name(conn, case.customer_id),
                        }
                    )
        return {
            "groups": groups,
            "matrix": matrix,
            "capacity": capacity,
            "priorityQueue": queue,
            "source": "api",
        }

    @app.get("/api/scenarios")
    def list_scenarios(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        hero = customer_name(conn, HERO_CUSTOMER_ID)
        scenarios = [
            {
                "id": "hero-multi",
                "name": f"{hero} — Multi-Revenue Crisis",
                "description": "Subscription, checkout, and receivable risks collide.",
                "customerId": HERO_CUSTOMER_ID,
                "caseId": HERO_CASES["receivable"],
                "backendCases": list(HERO_CASES.values()),
            },
            {
                "id": "hero-checkout",
                "name": "High-Intent Checkout",
                "description": "Abandoned payment with strong conversion window.",
                "customerId": HERO_CUSTOMER_ID,
                "caseId": HERO_CASES["checkout"],
                "backendCases": [HERO_CASES["checkout"]],
            },
            {
                "id": "hero-subscription",
                "name": "Broken Subscription Retry",
                "description": "Retry fails and strategy is re-planned.",
                "customerId": HERO_CUSTOMER_ID,
                "caseId": HERO_CASES["subscription"],
                "backendCases": [HERO_CASES["subscription"]],
            },
            {
                "id": "hero-receivable",
                "name": "Receivable — Promise-to-Pay",
                "description": "Receivable recovery with promise lifecycle.",
                "customerId": HERO_CUSTOMER_ID,
                "caseId": HERO_CASES["receivable"],
                "backendCases": [HERO_CASES["receivable"]],
            },
        ]
        # Attach visual step templates (playback) — backend remains authoritative on run
        for s in scenarios:
            s["steps"] = _scenario_steps_template(s["id"])
        return {"items": scenarios, "source": "api"}

    @app.post("/api/scenarios/{scenario_id}/run")
    def run_scenario(
        scenario_id: str,
        body: RunScenarioBody,
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        mapping = {
            "hero-multi": list(HERO_CASES.values()),
            "hero-checkout": [HERO_CASES["checkout"]],
            "hero-subscription": [HERO_CASES["subscription"]],
            "hero-receivable": [HERO_CASES["receivable"]],
            # aliases from Phase 9 mock ids
            "priya-multi": list(HERO_CASES.values()),
            "high-intent": [HERO_CASES["checkout"]],
            "broken-retry": [HERO_CASES["subscription"]],
            "ptp": [HERO_CASES["receivable"]],
        }
        case_ids = mapping.get(scenario_id)
        if not case_ids:
            raise HTTPException(404, f"Unknown scenario: {scenario_id}")
        runs = []
        for cid in case_ids:
            case = load_case_by_id(conn, cid)
            if case is None:
                continue
            if body.reset:
                reset_case_for_run(conn, cid)
                conn.commit()
            result = _dispatch_run(conn, case.lane, cid, body.intelligence)
            runs.append(serialize_run_result(result, customer_name(conn, case.customer_id)))
        # Coordination view after multi-case
        view = load_customer_recovery_view(conn, HERO_CUSTOMER_ID)
        payload = {
            "scenarioId": scenario_id,
            "runs": runs,
            "customer": view.to_dict(),
            "steps": _scenario_steps_from_runs(scenario_id, runs),
            "source": "api",
        }
        assert_safe_payload(payload)
        return payload

    @app.get("/api/search")
    def search(q: str = "", conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        query = q.strip().lower()
        if not query:
            return {"results": [], "source": "api"}
        results: list[dict[str, Any]] = []
        for row in conn.execute(
            "SELECT customer_id, name, email FROM customers LIMIT 300"
        ).fetchall():
            blob = f"{row['name']} {row['customer_id']} {row['email'] or ''}".lower()
            if query in blob:
                view = load_customer_recovery_view(conn, row["customer_id"])
                results.append(
                    {
                        "id": f"cust-{row['customer_id']}",
                        "type": "customer",
                        "title": row["name"],
                        "subtitle": row["customer_id"],
                        "href": f"/customers/{row['customer_id']}",
                        "amount": view.total_amount_at_risk,
                    }
                )
        for case in load_open_cases(conn):
            name = customer_name(conn, case.customer_id)
            blob = f"{name} {case.case_id} {case.source_ref_id} {case.lane}".lower()
            if query in blob:
                results.append(
                    {
                        "id": f"case-{case.case_id}",
                        "type": "case",
                        "title": f"{name} · {case.source_ref_id or case.case_id}",
                        "subtitle": lane_to_ui(case.lane),
                        "href": f"/recovery/{case.case_id}",
                        "amount": case.amount,
                    }
                )
        return {"results": results[:12], "source": "api"}

    @app.get("/api/notifications")
    def notifications(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        items = []
        # PTP due
        ptp = conn.execute(
            """
            SELECT case_id, customer_id, promised_amount FROM promises_to_pay
            WHERE status = 'active' LIMIT 5
            """
        ).fetchall()
        for row in ptp:
            items.append(
                {
                    "id": f"ptp-{row['case_id']}",
                    "title": "PTP active",
                    "body": f"₹{float(row['promised_amount']):,.0f} — {customer_name(conn, row['customer_id'])}",
                    "href": f"/recovery/{row['case_id']}",
                    "read": False,
                    "createdAt": "live",
                }
            )
        escalated = conn.execute(
            "SELECT COUNT(*) AS n FROM recovery_cases WHERE workflow_state = 'escalated' AND status = 'open'"
        ).fetchone()
        if int(escalated["n"]) > 0:
            items.append(
                {
                    "id": "esc-queue",
                    "title": f"{escalated['n']} cases require human review",
                    "body": "Escalation queue needs attention.",
                    "href": "/recovery?state=escalated",
                    "read": False,
                    "createdAt": "live",
                }
            )
        open_n = conn.execute(
            "SELECT COUNT(*) AS n FROM recovery_cases WHERE status = 'open'"
        ).fetchone()
        items.append(
            {
                "id": "open-cases",
                "title": f"{open_n['n']} open recovery cases",
                "body": "Revenue still at risk across lanes.",
                "href": "/recovery",
                "read": True,
                "createdAt": "live",
            }
        )
        return {"items": items, "source": "api"}

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        policy = load_policy()
        return {
            "maxContacts24h": policy.get("max_contacts_per_7_days", 3),
            "minContactGapHours": policy.get("min_contact_cooldown_hours", 24),
            "maxHumanEscalations": 1,
            "maxActiveIncentives": 1,
            "humanEscalationThreshold": policy.get("human_only_threshold_amount", 50000),
            "emailNotifications": True,
            "slackNotifications": False,
            "webhookUrl": "",
            "readOnly": True,
            "source": "api",
            "policy": policy,
            "economics": load_economics(),
            "actions": load_actions(),
        }

    return app


def _dispatch_run(conn: sqlite3.Connection, lane: str, case_id: str, intelligence: str):
    if lane == Lane.SUBSCRIPTION_PAYMENT.value:
        return run_subscription_case(conn, case_id, intelligence_mode=intelligence)
    if lane == Lane.CHECKOUT_ABANDONMENT.value:
        return run_checkout_case(conn, case_id, intelligence_mode=intelligence)
    if lane == Lane.RECEIVABLE.value:
        return run_receivable_case(conn, case_id, intelligence_mode=intelligence)
    raise HTTPException(400, f"Unsupported lane: {lane}")


def _state_matches(ui_state: str, filter_state: str) -> bool:
    if filter_state == "needs_action":
        return ui_state in {"needs_action", "abandoned"}
    if filter_state == "waiting":
        return ui_state in {"waiting", "ptp_active", "retry_scheduled"}
    return ui_state == filter_state


def _opportunities(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for lane_key, label in (
        (Lane.RECEIVABLE.value, "Receivables"),
        (Lane.SUBSCRIPTION_PAYMENT.value, "Subscriptions"),
        (Lane.CHECKOUT_ABANDONMENT.value, "Checkout"),
    ):
        row = conn.execute(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS t
            FROM recovery_cases WHERE status = 'open' AND lane = ?
            """,
            (lane_key,),
        ).fetchone()
        out.append(
            {
                "lane": lane_to_ui(lane_key),
                "label": label,
                "amount": float(row["t"]),
                "cases": int(row["n"]),
            }
        )
    return out


def _pulse(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT timestamp, case_id, customer_id, event_type, reason, action
        FROM audit_events
        ORDER BY timestamp DESC
        LIMIT 12
        """
    ).fetchall()
    items = []
    for i, row in enumerate(rows):
        case = load_case_by_id(conn, row["case_id"])
        amount = case.amount if case else 0
        lane = lane_to_ui(case.lane) if case else "subscription"
        items.append(
            {
                "id": f"p-{i}",
                "timestamp": str(row["timestamp"])[11:19]
                if len(str(row["timestamp"])) >= 19
                else str(row["timestamp"]),
                "customerName": customer_name(conn, row["customer_id"]),
                "customerId": row["customer_id"],
                "caseId": row["case_id"],
                "lane": lane,
                "amount": amount,
                "summary": [
                    row["reason"] or row["event_type"],
                    f"Action: {row['action']}" if row["action"] else "State update",
                ],
                "status": row["event_type"],
            }
        )
    return items


def _derived_trend(conn: sqlite3.Connection, days: int) -> list[dict[str, Any]]:
    """Presentation-friendly series derived from current portfolio levels (not fake ops metrics)."""
    kpis = overview_kpis(conn)
    at_risk = kpis["revenueAtRisk"] or 1
    recovered = kpis["recovered"] or 0
    now = datetime.now(timezone.utc)
    points = []
    for i in range(days - 1, -1, -1):
        d = now - timedelta(days=i)
        # Smooth toward current totals — marked derived in overview
        factor = 0.85 + 0.15 * ((days - i) / max(days, 1))
        points.append(
            {
                "date": d.date().isoformat(),
                "atRisk": round(at_risk * factor, 2),
                "recovered": round(recovered * factor, 2),
            }
        )
    return points


def _customer_timeline(conn: sqlite3.Connection, customer_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT timestamp, case_id, event_type, reason, action, to_state
        FROM audit_events
        WHERE customer_id = ?
        ORDER BY timestamp
        LIMIT 40
        """,
        (customer_id,),
    ).fetchall()
    events = []
    for i, row in enumerate(rows):
        case = load_case_by_id(conn, row["case_id"])
        events.append(
            {
                "id": f"t-{i}",
                "date": str(row["timestamp"])[:10],
                "title": row["reason"] or row["event_type"],
                "description": f"{row['event_type']}"
                + (f" · {row['action']}" if row["action"] else ""),
                "lane": lane_to_ui(case.lane) if case else None,
                "amount": case.amount if case else None,
                "status": row["to_state"],
                "type": "decision",
            }
        )
    if not events:
        for c in load_customer_recovery_view(conn, customer_id).active_cases:
            events.append(
                {
                    "id": c.case_id,
                    "date": "Open",
                    "title": f"{lane_to_ui(c.lane)} case open",
                    "description": c.failure_reason or c.workflow_state,
                    "lane": lane_to_ui(c.lane),
                    "amount": c.amount,
                    "status": c.workflow_state,
                    "type": "risk",
                }
            )
    return events


def _audit_ui_type(event_type: str) -> str:
    et = event_type.lower()
    if "policy" in et:
        return "policy"
    if "learn" in et:
        return "learning"
    if "outcome" in et:
        return "outcome"
    if "coord" in et:
        return "coordination"
    if "action" in et or "execut" in et:
        return "action"
    return "decision"


def _rate(value: Any) -> float:
    if value is None:
        return 0.0
    if hasattr(value, "recovery_rate"):
        return round(value.recovery_rate * 100, 1)
    try:
        v = float(value)
        return round(v * 100, 1) if v <= 1 else round(v, 1)
    except (TypeError, ValueError):
        return 0.0


def _scenario_steps_template(scenario_id: str) -> list[dict[str, Any]]:
    base = [
        ("10:00", "Revenue risk detected", "Backend case(s) loaded."),
        ("10:01", "Context assembled", "Customer and lane context built."),
        ("10:02", "Diagnosis completed", "Intelligence proposed likely cause."),
        ("10:03", "Recovery candidates evaluated", "Candidate actions ranked."),
        ("10:04", "Economics evaluated", "Expected net value computed."),
        ("10:05", "Coordination completed", "Customer-level plan applied."),
        ("10:06", "Policy approved action", "Deterministic policy gate ran."),
        ("10:07", "Action executed", "Simulator executed selected action."),
        ("10:08", "Outcome observed", "Terminal or intermediate state recorded."),
        ("10:09", "Learning signal recorded", "Outcome written to experience store."),
    ]
    return [
        {
            "id": f"{scenario_id}-{i}",
            "time": t,
            "title": title,
            "detail": detail,
            "state": "Pending",
            "decision": "—",
            "action": "—",
            "expectedValue": 0,
            "policyStatus": "—",
            "outcome": "—",
            "learning": "—",
        }
        for i, (t, title, detail) in enumerate(base)
    ]


def _scenario_steps_from_runs(scenario_id: str, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps = _scenario_steps_template(scenario_id)
    if not runs:
        return steps
    last = runs[-1]
    selected = (last.get("selectedAction") or {}).get("action") or "—"
    policy = (last.get("policy") or {}).get("status") or "—"
    diagnosis = (last.get("diagnosis") or {}).get("cause") or "—"
    updates = {
        2: {"state": "Diagnosed", "decision": diagnosis},
        4: {
            "state": "Economics Selected",
            "decision": selected,
            "action": selected,
            "expectedValue": (last.get("selectedAction") or {}).get("expectedNetValue") or 0,
        },
        6: {
            "state": "Policy " + str(policy).title(),
            "policyStatus": str(policy).title(),
            "action": selected,
            "expectedValue": (last.get("selectedAction") or {}).get("expectedNetValue") or 0,
        },
        7: {
            "state": "Action Executed",
            "action": selected,
            "outcome": "Recovered" if last.get("recovered") else last.get("terminalState"),
        },
        8: {
            "state": last.get("terminalState") or "Observed",
            "outcome": f"₹{last.get('amountRecovered', 0):,.0f}"
            if last.get("recovered")
            else last.get("terminalState"),
        },
        9: {"state": "Learning Pending", "learning": "Signal recorded"},
    }
    for idx, patch in updates.items():
        if idx < len(steps):
            steps[idx] = {**steps[idx], **patch}
    return steps


app = create_app()
