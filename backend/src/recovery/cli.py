"""CLI entry points for scripts (wired via pyproject.toml console scripts)."""

from __future__ import annotations

import argparse
from pathlib import Path

from recovery.db import connect, init_schema
from recovery.ingestion.synthetic.generator import generate_and_persist
from recovery.models.enums import Lane
from recovery.paths import DEFAULT_DB_PATH
from recovery.pipeline.checkout_runner import run_checkout_case
from recovery.pipeline.receivables_runner import run_receivable_case
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
    """Run a single recovery case (subscription, checkout, or receivable)."""
    parser = argparse.ArgumentParser(description="Run one recovery case by lane")
    parser.add_argument("--case-id", type=str, default=None, help="Recovery case ID")
    parser.add_argument(
        "--lane",
        choices=(
            "subscription_payment",
            "checkout_abandonment",
            "receivable",
        ),
        default=None,
        help="Lane filter when selecting a default case (optional)",
    )
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
        lane = args.lane or Lane.SUBSCRIPTION_PAYMENT.value
        row = conn.execute(
            """
            SELECT case_id FROM recovery_cases
            WHERE lane = ?
            ORDER BY case_id
            LIMIT 1
            """,
            (lane,),
        ).fetchone()
        if row is None:
            conn.close()
            raise SystemExit(f"No {lane} cases found. Run generate_data first.")
        case_id = row["case_id"]

    row = conn.execute(
        "SELECT lane FROM recovery_cases WHERE case_id = ?", (case_id,)
    ).fetchone()
    if row is None:
        conn.close()
        raise SystemExit(f"Case not found: {case_id}")
    lane = row["lane"]

    if args.lane is not None and args.lane != lane:
        conn.close()
        raise SystemExit(f"Case {case_id} is lane '{lane}', not '{args.lane}'.")

    if args.reset:
        reset_case_for_run(conn, case_id)

    if lane == Lane.CHECKOUT_ABANDONMENT.value:
        result = run_checkout_case(conn, case_id, intelligence_mode=args.intelligence)
    elif lane == Lane.SUBSCRIPTION_PAYMENT.value:
        result = run_subscription_case(conn, case_id, intelligence_mode=args.intelligence)
    elif lane == Lane.RECEIVABLE.value:
        result = run_receivable_case(conn, case_id, intelligence_mode=args.intelligence)
    else:
        conn.close()
        raise SystemExit(f"Unsupported lane for run_case: {lane}")

    conn.close()
    print(format_run_summary(result))


def run_batch() -> None:
    """Run recovery batch — Phase 2+."""
    raise NotImplementedError("Batch runner not yet implemented")


def run_evaluation() -> None:
    """Run Phase 3/4 intelligence evaluation by lane."""
    import json

    from recovery.db import connect, init_schema
    from recovery.env_loader import load_project_env
    from recovery.models.enums import Lane
    from recovery.paths import DEFAULT_DB_PATH

    load_project_env()
    parser = argparse.ArgumentParser(description="Run Podium recovery evaluation")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path")
    parser.add_argument(
        "--lane",
        choices=(
            Lane.SUBSCRIPTION_PAYMENT.value,
            Lane.CHECKOUT_ABANDONMENT.value,
            Lane.RECEIVABLE.value,
            "economics",
            "coordination",
        ),
        default=Lane.SUBSCRIPTION_PAYMENT.value,
        help="Evaluation lane (use economics / coordination / receivable for Phase 5/6/7)",
    )
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
        help="Limit number of cases (default: all)",
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
        if args.lane == "coordination":
            from recovery.evaluation.phase6_runner import (
                default_phase6_export_path,
                export_phase6_evaluation_json,
                format_phase6_evaluation_report,
                run_phase6_evaluation,
            )

            summary = run_phase6_evaluation(conn)
            print(format_phase6_evaluation_report(summary))
            if args.export_json:
                export_phase6_evaluation_json(summary, default_phase6_export_path())
                print(f"Exported: {default_phase6_export_path()}")
        elif args.lane == Lane.RECEIVABLE.value:
            from recovery.evaluation.phase7_runner import (
                default_phase7_export_path,
                export_phase7_evaluation_json,
                format_phase7_evaluation_report,
                run_phase7_evaluation,
            )

            summary = run_phase7_evaluation(
                conn, intelligence_mode=args.intelligence, limit=args.limit or 25
            )
            print(format_phase7_evaluation_report(summary))
            if args.export_json:
                export_phase7_evaluation_json(summary, default_phase7_export_path())
                print(f"Exported: {default_phase7_export_path()}")
        elif args.lane == "economics":
            from recovery.evaluation.phase5_runner import (
                default_phase5_export_path,
                export_phase5_evaluation_json,
                run_phase5_demo_evaluation,
                run_phase5_pipeline_evaluation,
            )
            from recovery.evaluation.phase5_metrics import format_economic_evaluation_report

            demo_summary = run_phase5_demo_evaluation()
            print(demo_summary.extra.get("report", ""))
            print(format_economic_evaluation_report(demo_summary))
            if args.export_json:
                export_phase5_evaluation_json(demo_summary, default_phase5_export_path("demos"))
                print(f"Exported: {default_phase5_export_path('demos')}")
            pipe = run_phase5_pipeline_evaluation(
                conn, intelligence_mode=args.intelligence, limit=args.limit or 30
            )
            print(format_economic_evaluation_report(pipe))
            if args.export_json:
                export_phase5_evaluation_json(pipe, default_phase5_export_path("pipeline"))
                print(f"Exported: {default_phase5_export_path('pipeline')}")
        elif args.lane == Lane.CHECKOUT_ABANDONMENT.value:
            from recovery.evaluation.phase4_runner import (
                compare_checkout_modes,
                default_checkout_export_path,
                export_checkout_evaluation_json,
                format_evaluation_report,
                run_phase4_evaluation,
            )

            compare_fn = compare_checkout_modes
            run_fn = run_phase4_evaluation
            export_fn = export_checkout_evaluation_json
            export_path_fn = default_checkout_export_path
            compare_name = "phase4_checkout_evaluation_compare.json"
        else:
            from recovery.evaluation.phase3_metrics import format_evaluation_report
            from recovery.evaluation.phase3_runner import (
                compare_modes,
                default_export_path,
                export_evaluation_json,
                run_phase3_evaluation,
            )

            compare_fn = compare_modes
            run_fn = run_phase3_evaluation
            export_fn = export_evaluation_json
            export_path_fn = default_export_path
            compare_name = "phase3_evaluation_compare.json"

        if args.lane not in {"economics", "coordination", Lane.RECEIVABLE.value}:
            if args.compare:
                summaries = compare_fn(conn, limit=args.limit)
                for mode, summary in summaries.items():
                    print(format_evaluation_report(summary))
                    print()
                    if args.export_json:
                        export_fn(summary, export_path_fn(mode))
                if args.export_json:
                    combined = {mode: s.to_dict() for mode, s in summaries.items()}
                    path = DEFAULT_DB_PATH.parent / "generated" / compare_name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
                    print(f"Comparison exported: {path}")
            else:
                summary = run_fn(conn, intelligence_mode=args.intelligence, limit=args.limit)
                print(format_evaluation_report(summary))
                if args.export_json:
                    path = export_path_fn(args.intelligence)
                    export_fn(summary, path)
                    print(f"Exported: {path}")
    finally:
        conn.close()
