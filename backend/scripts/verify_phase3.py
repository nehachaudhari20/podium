#!/usr/bin/env python3
"""Verify Phase 3A–3E end-to-end, including live Gemini API when configured."""

from __future__ import annotations

import sys
import traceback

from recovery.db import connect
from recovery.env_loader import load_project_env
from recovery.evaluation.ground_truth import load_ground_truth
from recovery.intelligence.context_builder import build_recovery_context
from recovery.intelligence.deterministic.decision import propose_deterministic_decision
from recovery.intelligence.gemini.config import GeminiConfig
from recovery.intelligence.gemini.reasoning import GeminiReasoningIntelligence
from recovery.intelligence.gemini.strategy import GeminiStrategyIntelligence
from recovery.models.recovery_context import assert_no_forbidden_fields
from recovery.paths import DEFAULT_DB_PATH
from recovery.pipeline.subscription_runner import run_subscription_case
from recovery.audit.trail import load_audit_trail
from recovery.state.reset import reset_case_for_run


def _section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(title)
    print("=" * 60)


def main() -> int:
    load_project_env()
    case_id = sys.argv[1] if len(sys.argv) > 1 else "case_0012"

    _section("Phase 3A — RecoveryContext")
    conn = connect(DEFAULT_DB_PATH)
    try:
        context = build_recovery_context(conn, case_id)
        assert_no_forbidden_fields(context.to_dict())
        gt = load_ground_truth(conn, case_id)
        print(f"case_id:          {context.case.case_id}")
        print(f"lane:             {context.case.lane}")
        print(f"failure_reason:   {context.case.failure_reason}")
        print(f"derived_signals:  repeated={context.derived_signals.repeated_failure}, "
              f"transient={context.derived_signals.transient_failure}")
        print(f"history events:   {len(context.recovery_history)}")
        print(f"ground_truth:     loaded separately (p_pay_anyway={gt.p_pay_anyway:.3f}) — NOT in context")
        assert "p_pay_anyway" not in str(context.to_dict())
        print("PASS: context built without forbidden evaluator fields")

        _section("Phase 3B — Deterministic intelligence stack")
        decision = propose_deterministic_decision(context)
        decision.validate_no_forbidden_fields()
        print(f"reasoning source:   {decision.reasoning.source}")
        print(f"likely_cause:       {decision.reasoning.likely_cause}")
        print(f"recommended_action: {decision.recommended_action.action_id}")
        print(f"candidates:         {[a.action_id for a in decision.candidate_actions]}")
        print("PASS: deterministic DecisionProposal composed")

        _section("Phase 3C — Live Gemini API")
        config = GeminiConfig.from_env()
        print(f"model:       {config.model}")
        print(f"available:   {config.is_available()}")
        if not config.is_available():
            print("SKIP: GEMINI_API_KEY not set — live API test skipped")
            return 0

        reasoning = GeminiReasoningIntelligence().interpret(context)
        print(f"reasoning source: {reasoning.source}")
        print(f"summary:          {reasoning.summary}")
        print(f"likely_cause:     {reasoning.likely_cause}")
        print(f"confidence:       {reasoning.confidence}")
        print(f"key_factors:      {reasoning.key_factors}")

        if reasoning.source != "gemini":
            print("FAIL: expected source='gemini'")
            return 1

        from recovery.intelligence.deterministic.predictive import DeterministicPredictiveIntelligence

        predictive = DeterministicPredictiveIntelligence().score(context)
        strategies = GeminiStrategyIntelligence().propose_strategies(context, reasoning, predictive)
        print(f"strategy count:   {len(strategies)}")
        for s in strategies:
            print(f"  [{s.priority}] {s.action.action_id} (conf={s.confidence:.2f}) — {s.rationale[:60]}...")

        if not strategies or strategies[0].source != "gemini":
            print("FAIL: Gemini strategy proposals missing")
            return 1

        print("PASS: live Gemini reasoning + strategy succeeded")

        _section("Phase 3D — Pipeline + policy gate (hybrid mode)")
        reset_case_for_run(conn, case_id)
        conn.commit()
        result = run_subscription_case(conn, case_id, intelligence_mode="hybrid")
        print(f"decision_source:  {result.decision_source}")
        print(f"terminal_state:   {result.terminal_state}")
        print(f"recovered:        {result.recovered}")
        print(f"selected_action:  {result.selected_action.action_id if result.selected_action else None}")
        if result.decision_source not in {"gemini", "deterministic"}:
            print("FAIL: unexpected decision source")
            return 1
        print("PASS: hybrid pipeline run completed with policy-validated action")

        _section("Phase 3E — Agentic loop (observe → replan)")
        reset_case_for_run(conn, case_id)
        conn.commit()
        result = run_subscription_case(conn, case_id, intelligence_mode="deterministic")
        events = load_audit_trail(conn, case_id)
        event_types = {e.event_type for e in events}
        print(f"agent_steps:      {result.agent_steps}")
        print(f"replan_count:     {result.replan_count}")
        print(f"AGENT_OBSERVE:    {'AGENT_OBSERVE' in event_types}")
        print(f"AGENT_REPLAN:     {'AGENT_REPLAN' in event_types}")
        if result.agent_steps < 1 or "AGENT_OBSERVE" not in event_types:
            print("FAIL: agentic loop did not run")
            return 1
        print("PASS: agentic recovery loop with observe/replan audit trail")
        return 0
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
