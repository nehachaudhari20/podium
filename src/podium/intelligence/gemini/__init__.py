"""Gemini-backed intelligence (Phase 3C)."""

from podium.intelligence.gemini.client import GeminiStructuredClient
from podium.intelligence.gemini.reasoning import GeminiReasoningIntelligence
from podium.intelligence.gemini.strategy import GeminiStrategyIntelligence

__all__ = [
    "GeminiStructuredClient",
    "GeminiReasoningIntelligence",
    "GeminiStrategyIntelligence",
]
