"""Environment configuration for Gemini integration."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str | None
    model: str
    max_tokens: int
    enabled: bool

    @classmethod
    def from_env(cls) -> GeminiConfig:
        from recovery.env_loader import load_project_env

        load_project_env()
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None
        if api_key:
            api_key = api_key.strip() or None
        enabled_raw = os.environ.get("LLM_ENABLED", "true").strip().lower()
        enabled = enabled_raw not in {"0", "false", "no", "off"}
        return cls(
            api_key=api_key,
            model=os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            max_tokens=int(os.environ.get("GEMINI_MAX_TOKENS", "1024")),
            enabled=enabled,
        )

    def is_available(self) -> bool:
        return self.enabled and bool(self.api_key)
