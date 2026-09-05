#!/usr/bin/env python3
"""Run cross-revenue coordination demos / hero scenario (Phase 6)."""

from __future__ import annotations

import argparse
from pathlib import Path

from recovery.db import connect, init_schema
from recovery.demos.coordination import (
    format_coordination_demo_report,
    format_customer_plan_report,
    run_coordination_demos,
    run_hero_coordination_demo,
)
from recovery.env_loader import load_project_env
from recovery.paths import DEFAULT_DB_PATH


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(description="Run Podium cross-revenue coordination demos")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--mode",
        choices=("hero", "scenarios", "both"),
        default="both",
    )
    parser.add_argument(
        "--intelligence",
        choices=("deterministic", "hybrid", "gemini"),
        default="deterministic",
    )
    args = parser.parse_args()

    conn = connect(args.db)
    init_schema(conn)
    try:
        exit_ok = True
        if args.mode in ("hero", "both"):
            view, coordinated, independent, report = run_hero_coordination_demo(
                conn, intelligence_mode=args.intelligence
            )
            print(report)
            print()
            print("INDEPENDENT BASELINE (no coordination)")
            print(format_customer_plan_report(view, independent, customer_label=view.customer_id))
            print()
        if args.mode in ("scenarios", "both"):
            demo_report = run_coordination_demos(conn)
            print(format_coordination_demo_report(demo_report))
            exit_ok = exit_ok and demo_report.passed
        raise SystemExit(0 if exit_ok else 1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
