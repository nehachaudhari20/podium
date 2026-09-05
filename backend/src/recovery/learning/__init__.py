"""Outcome-driven learning — Phase 8.

Learning supplies historical evidence and blended estimates.
Policy, economics calculation, and coordination remain authoritative.
Learning never accesses p_pay_anyway or mutates policy.
"""

from __future__ import annotations

from recovery.learning.blend import BlendedProbability, blend_from_store, blend_probability, clamp_probability
from recovery.learning.calibration import CalibrationReport, compute_calibration
from recovery.learning.config import LearningConfig, load_learning_config
from recovery.learning.effectiveness import (
    ActionEffectiveness,
    HistoricalEvidence,
    compute_action_effectiveness,
    confidence_for_count,
    get_historical_evidence,
)
from recovery.learning.records import DecisionOutcome, build_decision_outcome
from recovery.learning.signals import LearningSignal, generate_learning_signal
from recovery.learning.store import ExperienceQuery, ExperienceStore

__all__ = [
    "ActionEffectiveness",
    "BlendedProbability",
    "CalibrationReport",
    "DecisionOutcome",
    "ExperienceQuery",
    "ExperienceStore",
    "HistoricalEvidence",
    "LearningConfig",
    "LearningSignal",
    "blend_from_store",
    "blend_probability",
    "build_decision_outcome",
    "clamp_probability",
    "compute_action_effectiveness",
    "compute_calibration",
    "confidence_for_count",
    "generate_learning_signal",
    "get_historical_evidence",
    "load_learning_config",
]
