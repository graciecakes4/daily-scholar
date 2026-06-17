"""
Per-task LLM routing.

Each LLM call site (summary, review, quiz, evaluate) gets routed to a
provider+model independently. Defaults are tuned for cost: cheap models for
distillation / scoring, premium models for the things that need reasoning
(reviews, quizzes).

Supported providers:
  - anthropic    → Claude via the Anthropic SDK
  - gemini       → Google Gemini via the google-genai SDK
  - antigravity  → Google Antigravity agent harness via google-antigravity SDK
                   (uses Gemini under the hood; reach for it when you want
                   Antigravity's agent/tool features, not for raw throughput)

Override priority:
  1. LLM_TASK_<NAME> env var ("provider:model")
  2. The DEFAULT_TASK_ROUTING entry below
  3. The provider's default model (CLAUDE_MODEL / GEMINI_MODEL / ANTIGRAVITY_MODEL)
"""

from __future__ import annotations

from typing import Literal, Optional

from ...config import get_settings
from .interface import LLMClient

Task = Literal["summary", "review", "quiz", "evaluate", "default"]

# Edit here to change the baked-in defaults. The LLM_TASK_* env vars override
# these per-task without touching code.
DEFAULT_TASK_ROUTING: dict[str, str] = {
    "summary":  "anthropic:claude-haiku-4-5",   # cheap distillation
    "review":   "anthropic:claude-sonnet-4-5",  # needs teaching reasoning
    "quiz":     "anthropic:claude-sonnet-4-5",  # needs careful question construction
    "evaluate": "anthropic:claude-haiku-4-5",   # simple correctness check
    "default":  "anthropic:claude-sonnet-4-5",
}


def _resolve_routing(task: Task) -> tuple[str, Optional[str]]:
    """Return (provider, model_or_none) for a task, applying env overrides."""
    settings = get_settings()
    env_attr = f"llm_task_{task}"
    raw = (
        getattr(settings, env_attr, None)
        or DEFAULT_TASK_ROUTING.get(task)
        or DEFAULT_TASK_ROUTING["default"]
    )
    if ":" in raw:
        provider, model = raw.split(":", 1)
    else:
        # bare value treated as model name on the default provider
        provider = "anthropic"
        model = raw

    model_clean = model.strip() if model else None

    # Catch the common typo: model names should never contain a colon.
    # The :-separator goes between provider and model, ONCE. If a colon
    # leaks into the model side, the env var was written like
    # `anthropic:claude:sonnet-4-6` (two colons) instead of `anthropic:claude-sonnet-4-6`.
    if model_clean and ":" in model_clean:
        raise ValueError(
            f"LLM routing for task {task!r} has a colon inside the model name "
            f"({model_clean!r}). Format is 'provider:model' with exactly one colon, "
            f"and Anthropic model names use dashes throughout "
            f"(e.g. 'anthropic:claude-sonnet-4-6', not 'anthropic:claude:sonnet-4-6'). "
            f"Check your LLM_TASK_{task.upper()} env var."
        )

    return provider.strip().lower(), model_clean


def get_llm_client(task: Task = "default") -> LLMClient:
    """Return the LLMClient configured for `task`."""
    provider, model = _resolve_routing(task)

    if provider == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model=model)
    if provider == "gemini":
        from .gemini_client import GeminiClient
        return GeminiClient(model=model)
    if provider == "antigravity":
        from .antigravity_client import AntigravityClient
        return AntigravityClient(model=model)
    raise ValueError(
        f"Unknown LLM provider {provider!r} for task {task!r}. "
        f"Supported: anthropic, gemini, antigravity. "
        f"Set LLM_TASK_{task.upper()} to '<provider>:<model>'."
    )
