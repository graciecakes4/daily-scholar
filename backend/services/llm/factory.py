"""
Per-task LLM routing.

Each LLM call site (summary, review, quiz, evaluate) gets routed to a
provider+model independently. Defaults are tuned for cost: cheap models for
distillation / scoring, premium models for the things that need reasoning
(reviews, quizzes).

Override priority:
  1. LLM_TASK_<NAME> env var ("openai:gpt-4o-mini" or "anthropic:claude-haiku-4-5")
  2. The DEFAULT_TASK_ROUTING entry below
  3. The provider's default model (CLAUDE_MODEL / OPENAI_MODEL settings)
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
    raw = getattr(settings, env_attr, None) or DEFAULT_TASK_ROUTING.get(task) \
        or DEFAULT_TASK_ROUTING["default"]
    if ":" in raw:
        provider, model = raw.split(":", 1)
    else:
        # bare value treated as model name on the default provider
        provider = "anthropic"
        model = raw
    return provider.strip().lower(), (model.strip() or None)


def get_llm_client(task: Task = "default") -> LLMClient:
    """Return the LLMClient configured for `task`."""
    provider, model = _resolve_routing(task)

    if provider == "anthropic":
        # lazy import so installing only one SDK still works
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model=model)
    if provider == "openai":
        from .openai_client import OpenAIClient
        return OpenAIClient(model=model)
    raise ValueError(
        f"Unknown LLM provider {provider!r} for task {task!r}. "
        f"Set LLM_TASK_{task.upper()} to 'anthropic:<model>' or 'openai:<model>'."
    )
