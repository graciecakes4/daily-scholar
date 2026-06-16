"""
Multi-provider LLM abstraction.

Use `get_llm_client(task="summary"|"review"|"quiz"|"evaluate")` from
content_generator (or anywhere else) instead of importing a vendor SDK
directly. The factory picks provider + model based on env-var overrides
or the DEFAULT_TASK_ROUTING below.
"""

from .interface import LLMClient
from .factory import get_llm_client, DEFAULT_TASK_ROUTING

__all__ = ["LLMClient", "get_llm_client", "DEFAULT_TASK_ROUTING"]
