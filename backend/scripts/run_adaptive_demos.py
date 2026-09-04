#!/usr/bin/env python3
"""Run adaptive recovery demonstration scenarios (Phase 3F)."""

from __future__ import annotations

import argparse
from pathlib import Path

from recovery.db import connect
from recovery.demos.adaptive import format_demo_report, run_adaptive_demos
from recovery.env_loader import load_project_env
from recovery.paths import DEFAULT_DB_PATH


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(description="Run Podium adaptive demo scenarios")
    parser.add_argument(
        "--intelligence",
        choices=("deterministic", "hybrid", "gemini"),
        default="deterministic",
        help="Intelligence mode for demo runs",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite database path",
    )
    args = parser.parse_args()

    conn = connect(args.db)
    try:
        report = run_adaptive_demos(conn, intelligence_mode=args.intelligence)
        print(format_demo_report(report))
        raise SystemExit(0 if report.passed else 1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
