"""Configuration for hybrid decisioning (Phase 3D)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from recovery.env_loader import load_project_env
from recovery.intelligence.gemini.config import GeminiConfig


@dataclass(frozen=True)
class DecisionConfig:
    mode: str
    min_reasoning_confidence: float
    min_strategy_confidence: float

    @classmethod
    def from_env(cls) -> DecisionConfig:
        load_project_env()
        mode = os.environ.get("INTELLIGENCE_MODE", "hybrid").strip().lower()
        return cls(
            mode=mode,
            min_reasoning_confidence=float(os.environ.get("MIN_REASONING_CONFIDENCE", "0.4")),
            min_strategy_confidence=float(os.environ.get("MIN_STRATEGY_CONFIDENCE", "0.3")),
        )

    def use_gemini(self) -> bool:
        return self.mode in {"gemini", "hybrid"}

    def allow_fallback(self) -> bool:
        return self.mode == "hybrid"

    def gemini_available(self) -> bool:
        return GeminiConfig.from_env().is_available()
