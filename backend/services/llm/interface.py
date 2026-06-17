"""
LLMClient interface.

Two methods cover every call site in content_generator.py:

  - `complete(prompt, ...)`        → plain text
  - `complete_json(prompt, ...)`   → parsed dict (strips markdown fences)

Both are synchronous. FastAPI runs sync work in a thread pool when a coroutine
calls it; for now the simpler signatures win over an async-everywhere refactor.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Optional


class LLMClient(ABC):
    """Vendor-agnostic LLM façade."""

    # the model name being used — handy for logging and tests
    model: str = ""
    provider: str = ""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 2000,
        temperature: float = 0.4,
        system: Optional[str] = None,
    ) -> str:
        """Return raw model text."""

    def complete_json(
        self,
        prompt: str,
        *,
        max_tokens: int = 2500,
        temperature: float = 0.2,
        system: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Call `complete()` and parse JSON from the response. Tolerates the common
        ```json … ``` markdown fences both Anthropic and OpenAI sometimes emit.
        Returns {} on parse failure (callers log + degrade gracefully).
        """
        text = self.complete(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
        )
        try:
            return _parse_json_response(text)
        except Exception as e:
            # callers (content_generator) log + return empty defaults; we don't
            # want a bad-JSON response from the model to blow up a request
            return {"__llm_parse_error__": str(e), "__raw__": text[:500]}


def _parse_json_response(text: str) -> dict[str, Any]:
    """Strip optional ```json … ``` fences and parse."""
    s = text.strip()
    if "```json" in s:
        s = s.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in s:
        s = s.split("```", 1)[1].split("```", 1)[0]
    return json.loads(s)
