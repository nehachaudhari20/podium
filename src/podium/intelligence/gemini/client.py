"""Google Gemini client wrapper with structured JSON parsing."""

from __future__ import annotations

from typing import Any, Protocol

from podium.intelligence.gemini.config import GeminiConfig
from podium.intelligence.llm.schemas import parse_json_response


class ModelsAPI(Protocol):
    def generate_content(
        self,
        *,
        model: str,
        contents: str,
        config: dict[str, Any],
    ) -> Any: ...


class GeminiClient(Protocol):
    models: ModelsAPI


class GeminiStructuredClient:
    """Thin wrapper around the Google GenAI SDK for JSON responses."""

    def __init__(
        self,
        config: GeminiConfig | None = None,
        *,
        client: GeminiClient | None = None,
    ) -> None:
        self._config = config or GeminiConfig.from_env()
        self._client = client

    @property
    def config(self) -> GeminiConfig:
        return self._config

    def _get_client(self) -> GeminiClient:
        if self._client is not None:
            return self._client
        if not self._config.is_available():
            raise RuntimeError(
                "Gemini is not available: set GEMINI_API_KEY and LLM_ENABLED=true"
            )
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "google-genai package not installed; pip install 'podium[gemini]'"
            ) from exc
        self._client = genai.Client(api_key=self._config.api_key)
        return self._client

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        client = self._get_client()
        response = client.models.generate_content(
            model=self._config.model,
            contents=user,
            config={
                "system_instruction": system,
                "max_output_tokens": self._config.max_tokens,
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        )
        text = _extract_text(response)
        return parse_json_response(text)


def _extract_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text)
    raise ValueError("Gemini response contained no text")
