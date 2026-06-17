"""Google Gemini adapter (via the google-genai SDK)."""

from __future__ import annotations

from typing import Optional

from ...config import get_settings
from .interface import LLMClient


class GeminiClient(LLMClient):
    provider = "gemini"

    def __init__(self, model: Optional[str] = None):
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set — required when an LLM task routes to Gemini."
            )
        # lazy import so the google-genai package is only required when actually used
        from google import genai

        self.model = model or settings.gemini_model
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 2000,
        temperature: float = 0.4,
        system: Optional[str] = None,
    ) -> str:
        # google-genai accepts either a plain string or a list of contents;
        # `system_instruction` and generation_config go through a config object.
        from google.genai import types as genai_types

        config = genai_types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system,
        )
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return (response.text or "").strip()
