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
    parser.add_argument(
        "--intelligence",
        choices=("deterministic", "hybrid", "gemini"),
        default=None,
        help="Intelligence mode (default: INTELLIGENCE_MODE env or hybrid)",
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

    result = run_subscription_case(conn, case_id, intelligence_mode=args.intelligence)
    conn.close()
    print(format_run_summary(result))


def run_batch() -> None:
    """Run recovery batch — Phase 2+."""
    raise NotImplementedError("Batch runner not yet implemented")


def run_evaluation() -> None:
    """Run Phase 3 intelligence evaluation on subscription cases."""
    import json

    from recovery.db import connect, init_schema
    from recovery.env_loader import load_project_env
    from recovery.evaluation.phase3_runner import (
        compare_modes,
        default_export_path,
        export_evaluation_json,
        run_phase3_evaluation,
    )
    from recovery.evaluation.phase3_metrics import format_evaluation_report
    from recovery.paths import DEFAULT_DB_PATH

    load_project_env()
    parser = argparse.ArgumentParser(description="Run Phase 3 intelligence evaluation")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path")
    parser.add_argument(
        "--intelligence",
        choices=("deterministic", "hybrid", "gemini"),
        default="deterministic",
        help="Intelligence mode to evaluate",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare deterministic vs hybrid modes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of subscription cases (default: all)",
    )
    parser.add_argument(
        "--export-json",
        action="store_true",
        help="Write JSON report to data/generated/",
    )
    args = parser.parse_args()

    conn = connect(args.db)
    init_schema(conn)
    try:
        if args.compare:
            summaries = compare_modes(conn, limit=args.limit)
            for mode, summary in summaries.items():
                print(format_evaluation_report(summary))
                print()
                if args.export_json:
                    export_evaluation_json(summary, default_export_path(mode))
            if args.export_json:
                combined = {mode: s.to_dict() for mode, s in summaries.items()}
                path = DEFAULT_DB_PATH.parent / "generated" / "phase3_evaluation_compare.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
                print(f"Comparison exported: {path}")
        else:
            summary = run_phase3_evaluation(
                conn, intelligence_mode=args.intelligence, limit=args.limit
            )
            print(format_evaluation_report(summary))
            if args.export_json:
                path = default_export_path(args.intelligence)
                export_evaluation_json(summary, path)
                print(f"Exported: {path}")
    finally:
        conn.close()
