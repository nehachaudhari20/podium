"""Learning configuration — Phase 8."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from recovery.config import load_yaml


@dataclass(frozen=True, slots=True)
class LearningConfig:
    enabled: bool
    alpha: float
    min_observations_for_blend: int
    low_max: int
    medium_max: int
    smoothing_successes: float
    smoothing_failures: float
    min_probability: float
    max_probability: float


def load_learning_config(config_dir: Path | None = None) -> LearningConfig:
    raw = load_yaml("learning.yaml", config_dir)
    conf = raw.get("confidence") or {}
    return LearningConfig(
        enabled=bool(raw.get("enabled", True)),
        alpha=float(raw.get("alpha", 0.65)),
        min_observations_for_blend=int(raw.get("min_observations_for_blend", 3)),
        low_max=int(conf.get("low_max", 4)),
        medium_max=int(conf.get("medium_max", 19)),
        smoothing_successes=float(raw.get("smoothing_successes", 1)),
        smoothing_failures=float(raw.get("smoothing_failures", 1)),
        min_probability=float(raw.get("min_probability", 0.01)),
        max_probability=float(raw.get("max_probability", 0.99)),
    )
