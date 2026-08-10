"""LLM adapters.

The pipeline talks to `LLMClient` (a Protocol), never to a vendor SDK directly,
so the backend is swappable via the LLM_BACKEND setting.
"""

from __future__ import annotations

from functools import lru_cache

from loop.config import settings
from loop.llm.base import ArcDecision, ArticleSnippet, LLMClient

__all__ = ["ArcDecision", "ArticleSnippet", "LLMClient", "get_llm"]


@lru_cache
def get_llm() -> LLMClient:
    backend = settings.llm_backend.lower()
    if backend == "anthropic":
        from loop.llm.anthropic_client import AnthropicClient

        return AnthropicClient()
    if backend == "gemini":
        from loop.llm.gemini_client import GeminiClient

        return GeminiClient()
    # ollama / openai are declared in the README roadmap but not implemented yet;
    # fail loudly rather than silently mis-synthesising.
    raise ValueError(
        f"Unsupported LLM_BACKEND={backend!r}. Implemented backends: anthropic, gemini."
    )
