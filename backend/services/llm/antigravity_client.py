"""
Google Antigravity adapter (via the google-antigravity SDK).

Antigravity is Google's agent-native platform — stateful sessions, tool use,
managed execution. For Daily Scholar's single-turn summary/quiz/review
prompts we use the simplest local-agent form, treating each call as a fresh
one-shot chat. (If we ever want tool use or persistent context, we can extend
this adapter rather than touching callers.)

Heads-up: Antigravity uses Gemini under the hood, so each Antigravity call
costs roughly the same as a Gemini call plus agent-setup overhead. Reach for
this provider when you want Antigravity's agent harness (e.g., to add tool
calls later), not for raw throughput.

The SDK is async-first. We expose the sync LLMClient interface by bridging
through a fresh event loop in a worker thread when called from within an
existing async context (FastAPI's request handlers).
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Optional, TypeVar

from ...config import get_settings
from .interface import LLMClient


T = TypeVar("T")


def _run_async(coro: Awaitable[T]) -> T:
    """
    Run an awaitable to completion from a sync caller, even if there's already
    an event loop running on this thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — easy path
        return asyncio.run(coro)  # type: ignore[arg-type]

    # We're inside an event loop (FastAPI handler). Spawn a worker thread with
    # its own loop so we don't deadlock the outer one.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()  # type: ignore[arg-type]


class AntigravityClient(LLMClient):
    provider = "antigravity"

    def __init__(self, model: Optional[str] = None):
        settings = get_settings()
        if not settings.gemini_api_key:
            # Antigravity SDK reads GEMINI_API_KEY from env
            raise RuntimeError(
                "GEMINI_API_KEY not set — required when an LLM task routes to "
                "Antigravity (the SDK uses Gemini under the hood)."
            )
        # eager check that the SDK is installed, but defer the actual import
        # to call time so import errors surface only when this provider is used
        try:
            import google.antigravity  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "google-antigravity not installed. Run `pip install google-antigravity`."
            ) from e

        self.model = model or settings.antigravity_model or ""

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 2000,
        temperature: float = 0.4,
        system: Optional[str] = None,
    ) -> str:
        async def _go() -> str:
            from google.antigravity import Agent, LocalAgentConfig

            # build the agent config; pass model only if we have one to avoid
            # forcing SDK defaults
            config_kwargs: dict[str, Any] = {}
            if self.model:
                config_kwargs["model"] = self.model
            if system:
                # Antigravity calls these "system prompts" or "instructions" depending
                # on SDK version; pass through if supported, ignore if not.
                config_kwargs.setdefault("system_instruction", system)

            config = LocalAgentConfig(**config_kwargs) if config_kwargs else LocalAgentConfig()
            async with Agent(config) as agent:
                response = await agent.chat(prompt)
                text = await response.text()
                return (text or "").strip()

        return _run_async(_go())
