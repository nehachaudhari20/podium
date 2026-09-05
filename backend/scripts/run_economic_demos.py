#!/usr/bin/env python3
"""Run economic decision demonstration scenarios (Phase 5)."""

from __future__ import annotations

from recovery.demos.economic import format_economic_demo_report, run_economic_demos
from recovery.env_loader import load_project_env


def main() -> None:
    load_project_env()
    report = run_economic_demos()
    print(format_economic_demo_report(report))
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
