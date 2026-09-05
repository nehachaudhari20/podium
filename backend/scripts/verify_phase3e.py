#!/usr/bin/env python3
"""Verify Phase 3E agentic loop on key scenarios."""

from __future__ import annotations

import sys

from recovery.audit.trail import load_audit_trail
from recovery.db import connect
from recovery.env_loader import load_project_env
from recovery.paths import DEFAULT_DB_PATH
from recovery.pipeline.subscription_runner import run_subscription_case
from recovery.state.reset import reset_case_for_run


def main() -> int:
    load_project_env()
    case_id = sys.argv[1] if len(sys.argv) > 1 else None
    scenarios = [
        ("case_0019", "network_timeout / transient"),
        ("case_0012", "insufficient_funds"),
        ("case_hero_sub_001", "expired_card / hero"),
    ]
    if case_id:
        scenarios = [(case_id, "custom")]

    conn = connect(DEFAULT_DB_PATH)
    try:
        all_pass = True
        for cid, label in scenarios:
            reset_case_for_run(conn, cid)
            conn.commit()
            result = run_subscription_case(conn, cid, intelligence_mode="deterministic")
            events = load_audit_trail(conn, cid)
            observe = sum(1 for e in events if e.event_type == "AGENT_OBSERVE")
            replan = sum(1 for e in events if e.event_type == "AGENT_REPLAN")
            proposed = sum(1 for e in events if e.event_type == "DECISION_PROPOSED")

            ok = (
                observe >= 1
                and result.agent_steps >= 1
                and result.replan_count >= 0
                and "AGENT_OBSERVE" in {e.event_type for e in events}
            )
            if not ok:
                all_pass = False

            status = "PASS" if ok else "FAIL"
            print(f"\n[{status}] {cid} ({label})")
            print(f"  recovered={result.recovered}  terminal={result.terminal_state}")
            print(f"  agent_steps={result.agent_steps}  replan_count={result.replan_count}")
            print(f"  audit: AGENT_OBSERVE={observe}  AGENT_REPLAN={replan}  DECISION_PROPOSED={proposed}")
            print(f"  states: {' -> '.join(result.state_history)}")

        print("\n" + ("All Phase 3E checks passed." if all_pass else "Some Phase 3E checks failed."))
        return 0 if all_pass else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
