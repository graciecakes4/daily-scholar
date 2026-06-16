"""OpenAI adapter."""

from __future__ import annotations

from typing import Optional

from ...config import get_settings
from .interface import LLMClient


class OpenAIClient(LLMClient):
    provider = "openai"

    def __init__(self, model: Optional[str] = None):
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set — required when an LLM task routes to OpenAI."
            )
        # lazy import so the openai package is only required when a task actually uses it
        from openai import OpenAI

        self.model = model or settings.openai_model
        self._client = OpenAI(api_key=settings.openai_api_key)

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 2000,
        temperature: float = 0.4,
        system: Optional[str] = None,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""
