"""Anthropic adapter."""

from __future__ import annotations

from typing import Optional

import anthropic

from ...config import get_settings
from .interface import LLMClient


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, model: Optional[str] = None):
        settings = get_settings()
        self.model = model or settings.claude_model
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 2000,
        temperature: float = 0.4,
        system: Optional[str] = None,
    ) -> str:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        response = self._client.messages.create(**kwargs)
        return response.content[0].text
