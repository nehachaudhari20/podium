"""CLI entry points for scripts (wired via pyproject.toml console scripts)."""

from __future__ import annotations

import argparse
from pathlib import Path

from podium.ingestion.synthetic.generator import generate_and_persist


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
    """Run a single recovery case — Phase 2."""
    raise NotImplementedError("Phase 2: single-case runner not yet implemented")


def run_batch() -> None:
    """Run recovery batch — Phase 2+."""
    raise NotImplementedError("Batch runner not yet implemented")


def run_evaluation() -> None:
    """Run baseline / adaptive / full evaluation — Phase 8."""
    raise NotImplementedError("Batch evaluator not yet implemented")
