"""Anthropic adapter."""

from __future__ import annotations

from typing import Optional

import anthropic

from ...config import get_settings
from .interface import LLMClient


# Models that reject the `temperature` parameter outright. Anthropic deprecated
# `temperature` on certain newer / extended-thinking models — passing it
# returns a 400 invalid_request_error. We drop the parameter for these
# matches (prefix-match against the model string).
_NO_TEMPERATURE_MODEL_PREFIXES: tuple[str, ...] = (
    "claude-opus-4-8",
    "claude-opus-4-1",
    "claude-opus-4-0",
    "claude-sonnet-4-6",
)


def _accepts_temperature(model: str) -> bool:
    return not any(model.startswith(p) for p in _NO_TEMPERATURE_MODEL_PREFIXES)


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
            "messages": [{"role": "user", "content": prompt}],
        }
        # only attach temperature for models that still accept it
        if _accepts_temperature(self.model):
            kwargs["temperature"] = temperature
        if system:
            kwargs["system"] = system
        response = self._client.messages.create(**kwargs)
        return response.content[0].text
