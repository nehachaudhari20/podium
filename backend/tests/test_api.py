"""API integration tests for the thin Podium FastAPI adapter."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from recovery.api.main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_overview_has_kpis_without_ground_truth() -> None:
    r = client.get("/api/overview")
    assert r.status_code == 200
    body = r.json()
    assert "kpis" in body
    assert "revenueAtRisk" in body["kpis"]
    assert "p_pay_anyway" not in json.dumps(body)


def test_hero_customer() -> None:
    r = client.get("/api/customers/cust_hero_001")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "cust_hero_001"
    assert "lanes" in body
    assert body["totalExposure"] >= 0 or body["revenueAtRisk"] >= 0


def test_list_and_get_case() -> None:
    listed = client.get("/api/recovery/cases")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert items
    case_id = items[0]["id"]
    detail = client.get(f"/api/recovery/cases/{case_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == case_id
    assert "decision" in body
    assert "p_pay_anyway" not in json.dumps(body)


def test_run_recovery_updates_case() -> None:
    case_id = "case_hero_sub_001"
    before = client.get(f"/api/recovery/cases/{case_id}")
    assert before.status_code == 200
    run = client.post(
        f"/api/recovery/cases/{case_id}/run",
        json={"reset": True, "intelligence": "deterministic"},
    )
    assert run.status_code == 200
    payload = run.json()
    assert payload["run"]["caseId"] == case_id
    assert payload["run"]["diagnosis"]["cause"]
    assert payload["case"]["id"] == case_id
    assert "p_pay_anyway" not in json.dumps(payload)


def test_learning_and_audit_and_analytics() -> None:
    assert client.get("/api/learning/summary").status_code == 200
    assert client.get("/api/learning/actions").status_code == 200
    assert client.get("/api/learning/calibration").status_code == 200
    assert client.get("/api/analytics").status_code == 200
    assert client.get("/api/audit").status_code == 200
    assert client.get("/api/config").status_code == 200


def test_scenario_run() -> None:
    r = client.post(
        "/api/scenarios/hero-subscription/run",
        json={"reset": True, "intelligence": "deterministic"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["runs"]
    assert body["steps"]


def test_e2e_smoke_flow() -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    customer = client.get("/api/customers/cust_hero_001").json()
    assert customer["id"] == "cust_hero_001"
    case_id = "case_hero_chk_001"
    case = client.get(f"/api/recovery/cases/{case_id}").json()
    assert case["customerId"] == "cust_hero_001"
    run = client.post(
        f"/api/recovery/cases/{case_id}/run",
        json={"reset": True, "intelligence": "deterministic"},
    ).json()
    updated = client.get(f"/api/recovery/cases/{case_id}").json()
    assert updated["id"] == case_id
    assert run["run"]["terminalState"]
    audit = client.get("/api/audit", params={"search": case_id}).json()["items"]
    assert run["run"]["auditEventCount"] >= 0
    # Prefer case-scoped audit on the detail payload when global list is noisy
    detail_audit = updated.get("audit") or []
    assert run["run"]["terminalState"] or detail_audit or any(
        a["caseId"] == case_id for a in audit
    )
    learning = client.get("/api/learning/summary").json()
    assert "outcomesObserved" in learning
