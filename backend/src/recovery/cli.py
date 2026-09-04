"""CLI entry points for scripts (wired via pyproject.toml console scripts)."""

from __future__ import annotations

import argparse
from pathlib import Path

from recovery.db import connect, init_schema
from recovery.ingestion.synthetic.generator import generate_and_persist
from recovery.paths import DEFAULT_DB_PATH
from recovery.pipeline.subscription_runner import format_run_summary, run_subscription_case
from recovery.state.reset import reset_case_for_run


def generate_data() -> None:
    """Generate synthetic dataset — Phase 1."""
    parser = argparse.ArgumentParser(description="Generate Podium synthetic recovery dataset")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite output path (default: data/podium.db)",
    )
    args = parser.parse_args()
    generate_and_persist(seed=args.seed, db_path=args.db)


def run_case() -> None:
    """Run a single subscription-payment recovery case — Phase 2."""
    parser = argparse.ArgumentParser(description="Run one subscription recovery case")
    parser.add_argument("--case-id", type=str, default=None, help="Recovery case ID")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite database path",
    )
    parser.add_argument(
        "--reset",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reset case to detected before running (default: true)",
    )
    args = parser.parse_args()

    conn = connect(args.db)
    init_schema(conn)

    case_id = args.case_id
    if case_id is None:
        row = conn.execute(
            """
            SELECT case_id FROM recovery_cases
            WHERE lane = 'subscription_payment'
            ORDER BY case_id
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            conn.close()
            raise SystemExit("No subscription_payment cases found. Run generate_data first.")
        case_id = row["case_id"]

    if args.reset:
        reset_case_for_run(conn, case_id)

    result = run_subscription_case(conn, case_id)
    conn.close()
    print(format_run_summary(result))


def run_batch() -> None:
    """Run recovery batch — Phase 2+."""
    raise NotImplementedError("Batch runner not yet implemented")


def run_evaluation() -> None:
    """Run baseline / adaptive / full evaluation — Phase 8."""
    raise NotImplementedError("Batch evaluator not yet implemented")
