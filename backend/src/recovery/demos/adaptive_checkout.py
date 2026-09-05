"""Run and validate adaptive checkout demonstration scenarios (Phase 4D)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from recovery.audit.trail import load_audit_trail
from recovery.demos.adaptive import AdaptiveDemoOutcome, AdaptiveDemoReport, prepare_demo_case
from recovery.paths import SCENARIOS_DIR
from recovery.pipeline.checkout_runner import run_checkout_case

DEFAULT_CHECKOUT_SCENARIO_FILE = SCENARIOS_DIR / "adaptive_checkout_demos.yaml"


@dataclass(frozen=True, slots=True)
class CheckoutScenarioExpectation:
    recovered: bool | None = None
    min_agent_steps: int = 1
    max_agent_steps: int | None = None
    min_replan_count: int = 0
    required_states: tuple[str, ...] = ()
    forbidden_states: tuple[str, ...] = ()
    terminal_states: tuple[str, ...] = ()
    required_actions: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CheckoutDemoScenario:
    id: str
    title: str
    narrative: str
    failure_reason: str | None = None
    case_id: str | None = None
    setup: dict[str, Any] = field(default_factory=dict)
    expectation: CheckoutScenarioExpectation = CheckoutScenarioExpectation()


def load_checkout_demo_scenarios(
    path: Path = DEFAULT_CHECKOUT_SCENARIO_FILE,
) -> list[CheckoutDemoScenario]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    scenarios: list[CheckoutDemoScenario] = []
    for raw in data.get("scenarios") or []:
        exp_raw = raw.get("expected") or {}
        expectation = CheckoutScenarioExpectation(
            recovered=exp_raw.get("recovered"),
            min_agent_steps=int(exp_raw.get("min_agent_steps", 1)),
            max_agent_steps=exp_raw.get("max_agent_steps"),
            min_replan_count=int(exp_raw.get("min_replan_count", 0)),
            required_states=tuple(exp_raw.get("required_states") or ()),
            forbidden_states=tuple(exp_raw.get("forbidden_states") or ()),
            terminal_states=tuple(exp_raw.get("terminal_states") or ()),
            required_actions=tuple(exp_raw.get("required_actions") or ()),
            forbidden_actions=tuple(exp_raw.get("forbidden_actions") or ()),
        )
        scenarios.append(
            CheckoutDemoScenario(
                id=str(raw["id"]),
                title=str(raw.get("title", raw["id"])),
                narrative=str(raw.get("narrative", "")).strip(),
                failure_reason=raw.get("failure_reason"),
                case_id=raw.get("case_id"),
                expectation=expectation,
                setup=dict(raw.get("setup") or {}),
            )
        )
    return scenarios


def resolve_checkout_case_id(conn: sqlite3.Connection, scenario: CheckoutDemoScenario) -> str:
    if scenario.case_id:
        row = conn.execute(
            "SELECT case_id FROM recovery_cases WHERE case_id = ?",
            (scenario.case_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Case not found: {scenario.case_id}")
        return scenario.case_id

    if not scenario.failure_reason:
        raise ValueError(f"Scenario {scenario.id} needs case_id or failure_reason")

    row = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'checkout_abandonment'
          AND failure_reason = ?
          AND case_id != 'case_hero_chk_001'
        ORDER BY case_id
        LIMIT 1
        """,
        (scenario.failure_reason,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No checkout case for failure_reason={scenario.failure_reason!r}")
    return row["case_id"]


def apply_scenario_setup(conn: sqlite3.Connection, case_id: str, setup: dict[str, Any]) -> None:
    """Apply optional demo context overrides (intent, cart, stage)."""
    if not setup:
        return

    case_updates: list[str] = []
    case_params: list[Any] = []
    if "recoverability_hint" in setup:
        case_updates.append("recoverability_hint = ?")
        case_params.append(setup["recoverability_hint"])
    if "cart_value" in setup:
        case_updates.append("amount = ?")
        case_params.append(float(setup["cart_value"]))
    if case_updates:
        case_params.append(case_id)
        conn.execute(
            f"UPDATE recovery_cases SET {', '.join(case_updates)} WHERE case_id = ?",
            case_params,
        )

    session_updates: list[str] = []
    session_params: list[Any] = []
    for key, column in (
        ("intent_score", "intent_score"),
        ("stage", "stage"),
        ("cart_value", "cart_value"),
    ):
        if key in setup:
            session_updates.append(f"{column} = ?")
            session_params.append(setup[key])
    if session_updates:
        session_params.append(case_id)
        conn.execute(
            f"UPDATE checkout_sessions SET {', '.join(session_updates)} WHERE case_id = ?",
            session_params,
        )
    conn.commit()


def evaluate_checkout_scenario(
    scenario: CheckoutDemoScenario,
    case_id: str,
    result,
    events,
) -> AdaptiveDemoOutcome:
    exp = scenario.expectation
    failures: list[str] = []
    history = result.state_history

    if exp.recovered is not None and result.recovered != exp.recovered:
        failures.append(f"expected recovered={exp.recovered}, got {result.recovered}")

    if result.agent_steps < exp.min_agent_steps:
        failures.append(f"expected agent_steps>={exp.min_agent_steps}, got {result.agent_steps}")

    if exp.max_agent_steps is not None and result.agent_steps > exp.max_agent_steps:
        failures.append(f"expected agent_steps<={exp.max_agent_steps}, got {result.agent_steps}")

    if result.replan_count < exp.min_replan_count:
        failures.append(f"expected replan_count>={exp.min_replan_count}, got {result.replan_count}")

    for state in exp.required_states:
        if state not in history:
            failures.append(f"missing required state '{state}' in {history}")

    for state in exp.forbidden_states:
        if state in history:
            failures.append(f"forbidden state '{state}' appeared in {history}")

    if exp.terminal_states and result.terminal_state not in exp.terminal_states:
        failures.append(
            f"expected terminal in {list(exp.terminal_states)}, got {result.terminal_state!r}"
        )

    action_sequence = [
        e.action for e in events if e.event_type == "ACTION_EXECUTED" and e.action
    ]

    for action in exp.required_actions:
        if action not in action_sequence:
            failures.append(f"missing required action '{action}' in {action_sequence}")

    for action in exp.forbidden_actions:
        if action in action_sequence:
            failures.append(f"forbidden action '{action}' appeared in {action_sequence}")

    return AdaptiveDemoOutcome(
        scenario=scenario,  # type: ignore[arg-type]
        case_id=case_id,
        result=result,
        passed=not failures,
        failures=failures,
        action_sequence=action_sequence,
    )


def run_adaptive_checkout_demos(
    conn: sqlite3.Connection,
    *,
    intelligence_mode: str = "deterministic",
    scenarios: list[CheckoutDemoScenario] | None = None,
) -> AdaptiveDemoReport:
    catalog = scenarios or load_checkout_demo_scenarios()
    outcomes: list[AdaptiveDemoOutcome] = []
    used_cases: set[str] = set()

    for scenario in catalog:
        case_id = _allocate_case(conn, scenario, used_cases)
        used_cases.add(case_id)
        prepare_demo_case(conn, case_id)
        apply_scenario_setup(conn, case_id, scenario.setup)
        result = run_checkout_case(conn, case_id, intelligence_mode=intelligence_mode)
        events = load_audit_trail(conn, case_id)
        outcomes.append(evaluate_checkout_scenario(scenario, case_id, result, events))

    return AdaptiveDemoReport(outcomes=outcomes, intelligence_mode=intelligence_mode)


def _allocate_case(
    conn: sqlite3.Connection,
    scenario: CheckoutDemoScenario,
    used: set[str],
) -> str:
    if scenario.case_id:
        return resolve_checkout_case_id(conn, scenario)

    if not scenario.failure_reason:
        raise ValueError(f"Scenario {scenario.id} needs case_id or failure_reason")

    rows = conn.execute(
        """
        SELECT case_id FROM recovery_cases
        WHERE lane = 'checkout_abandonment'
          AND failure_reason = ?
          AND case_id != 'case_hero_chk_001'
        ORDER BY case_id
        """,
        (scenario.failure_reason,),
    ).fetchall()
    for row in rows:
        if row["case_id"] not in used:
            return row["case_id"]
    raise ValueError(f"No unused checkout case for failure_reason={scenario.failure_reason!r}")


def format_checkout_demo_report(report: AdaptiveDemoReport) -> str:
    lines = [
        "=" * 72,
        "Podium Adaptive Checkout Demonstrations (Phase 4D)",
        f"Intelligence mode: {report.intelligence_mode}",
        "=" * 72,
    ]

    for outcome in report.outcomes:
        s = outcome.scenario
        r = outcome.result
        status = "PASS" if outcome.passed else "FAIL"
        lines.extend(
            [
                "",
                f"[{status}] {s.id} — {s.title}",
                f"Case: {outcome.case_id}",
                f"Narrative: {s.narrative}",
                f"Outcome: recovered={r.recovered}  terminal={r.terminal_state}",
                f"Diagnosis: {r.diagnosis.likely_cause} (source={r.decision_source})",
                f"Agent: steps={r.agent_steps}  replans={r.replan_count}",
                f"States: {' -> '.join(r.state_history)}",
                f"Actions: {' -> '.join(outcome.action_sequence) or '(none)'}",
            ]
        )
        if outcome.failures:
            lines.append("Failures:")
            lines.extend(f"  - {msg}" for msg in outcome.failures)

    lines.extend(
        [
            "",
            "=" * 72,
            f"Summary: {sum(1 for o in report.outcomes if o.passed)}/{len(report.outcomes)} scenarios passed",
            "=" * 72,
        ]
    )
    return "\n".join(lines)
