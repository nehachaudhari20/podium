"""Run and validate adaptive demonstration scenarios (Phase 3F)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

import yaml

from recovery.audit.trail import load_audit_trail
from recovery.paths import SCENARIOS_DIR
from recovery.pipeline.subscription_runner import RunCaseResult, run_subscription_case
from recovery.state.reset import reset_case_for_run

DEFAULT_SCENARIO_FILE = SCENARIOS_DIR / "adaptive_demos.yaml"


@dataclass(frozen=True, slots=True)
class ScenarioExpectation:
    recovered: bool | None = None
    min_agent_steps: int = 1
    max_agent_steps: int | None = None
    min_replan_count: int = 0
    required_states: tuple[str, ...] = ()
    forbidden_states: tuple[str, ...] = ()
    terminal_states: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AdaptiveDemoScenario:
    id: str
    title: str
    narrative: str
    failure_reason: str | None = None
    case_id: str | None = None
    expectation: ScenarioExpectation = ScenarioExpectation()


@dataclass
class AdaptiveDemoOutcome:
    scenario: AdaptiveDemoScenario
    case_id: str
    result: RunCaseResult
    passed: bool
    failures: list[str] = field(default_factory=list)
    action_sequence: list[str] = field(default_factory=list)


@dataclass
class AdaptiveDemoReport:
    outcomes: list[AdaptiveDemoOutcome]
    intelligence_mode: str

    @property
    def passed(self) -> bool:
        return all(o.passed for o in self.outcomes)


def load_adaptive_scenarios(path=DEFAULT_SCENARIO_FILE) -> list[AdaptiveDemoScenario]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    scenarios: list[AdaptiveDemoScenario] = []
    for raw in data.get("scenarios") or []:
        exp_raw = raw.get("expected") or {}
        expectation = ScenarioExpectation(
            recovered=exp_raw.get("recovered"),
            min_agent_steps=int(exp_raw.get("min_agent_steps", 1)),
            max_agent_steps=exp_raw.get("max_agent_steps"),
            min_replan_count=int(exp_raw.get("min_replan_count", 0)),
            required_states=tuple(exp_raw.get("required_states") or ()),
            forbidden_states=tuple(exp_raw.get("forbidden_states") or ()),
            terminal_states=tuple(exp_raw.get("terminal_states") or ()),
        )
        scenarios.append(
            AdaptiveDemoScenario(
                id=str(raw["id"]),
                title=str(raw.get("title", raw["id"])),
                narrative=str(raw.get("narrative", "")).strip(),
                failure_reason=raw.get("failure_reason"),
                case_id=raw.get("case_id"),
                expectation=expectation,
            )
        )
    return scenarios


def resolve_case_id(conn: sqlite3.Connection, scenario: AdaptiveDemoScenario) -> str:
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
        WHERE lane = 'subscription_payment' AND failure_reason = ?
        ORDER BY case_id
        LIMIT 1
        """,
        (scenario.failure_reason,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No case for failure_reason={scenario.failure_reason!r}")
    return row["case_id"]


def prepare_demo_case(conn: sqlite3.Connection, case_id: str) -> None:
    """Reset case and customer contact counters for a clean demo run."""
    reset_case_for_run(conn, case_id)
    # Isolate demos from cross-scenario learning contamination.
    from recovery.learning.store import ExperienceStore

    ExperienceStore(conn).clear()
    row = conn.execute(
        "SELECT customer_id FROM recovery_cases WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    conn.execute(
        "UPDATE customers SET opt_out = 0, prior_contacts_7d = 0 WHERE customer_id = ?",
        (row["customer_id"],),
    )
    conn.commit()


def evaluate_scenario(
    scenario: AdaptiveDemoScenario,
    case_id: str,
    result: RunCaseResult,
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

    return AdaptiveDemoOutcome(
        scenario=scenario,
        case_id=case_id,
        result=result,
        passed=not failures,
        failures=failures,
        action_sequence=action_sequence,
    )


def run_adaptive_demos(
    conn: sqlite3.Connection,
    *,
    intelligence_mode: str = "deterministic",
    scenarios: list[AdaptiveDemoScenario] | None = None,
) -> AdaptiveDemoReport:
    catalog = scenarios or load_adaptive_scenarios()
    outcomes: list[AdaptiveDemoOutcome] = []

    for scenario in catalog:
        case_id = resolve_case_id(conn, scenario)
        prepare_demo_case(conn, case_id)
        result = run_subscription_case(conn, case_id, intelligence_mode=intelligence_mode)
        events = load_audit_trail(conn, case_id)
        outcomes.append(evaluate_scenario(scenario, case_id, result, events))

    return AdaptiveDemoReport(outcomes=outcomes, intelligence_mode=intelligence_mode)


def format_demo_report(report: AdaptiveDemoReport) -> str:
    lines = [
        "=" * 72,
        "Podium Adaptive Recovery Demonstrations (Phase 3F)",
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
