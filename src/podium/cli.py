"""CLI entry points for scripts (wired via pyproject.toml console scripts)."""


def generate_data() -> None:
    """Generate synthetic dataset — Phase 1."""
    raise NotImplementedError("Phase 1: synthetic data generator not yet implemented")


def run_case() -> None:
    """Run a single recovery case — Phase 2."""
    raise NotImplementedError("Phase 2: single-case runner not yet implemented")


def run_batch() -> None:
    """Run recovery batch — Phase 2+."""
    raise NotImplementedError("Batch runner not yet implemented")


def run_evaluation() -> None:
    """Run baseline / adaptive / full evaluation — Phase 8."""
    raise NotImplementedError("Batch evaluator not yet implemented")
