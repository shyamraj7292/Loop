"""Anthropic backend for arc synthesis.

Security posture (README > Threat 1 — Prompt injection via article body):
  * Article text is passed as clearly delimited DATA, never as instruction.
  * The system prompt states explicitly that fetched content is untrusted.
  * Structured output only — a response that does not parse against the schema
    is discarded, not repaired.
"""

from __future__ import annotations

import json
import logging

from loop.config import settings
from loop.llm.base import (
    ARC_DECISION_SCHEMA,
    SYSTEM_PROMPT,
    ArcDecision,
    ArticleSnippet,
    build_user_content,
)

logger = logging.getLogger(__name__)


class AnthropicClient:
    def __init__(self) -> None:
        # Imported lazily so the rest of the app doesn't require the SDK.
        import anthropic

        if not settings.anthropic_api_key:
            logger.warning(
                "ANTHROPIC_API_KEY is empty; synthesis calls will fail. "
                "Set it in .env or switch LLM_BACKEND=mock."
            )
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    def synthesize_arc(
        self,
        *,
        title: str | None,
        state_summary: str | None,
        existing_events: list[str],
        new_articles: list[ArticleSnippet],
        use_large_model: bool,
    ) -> ArcDecision:
        model = (
            settings.llm_model_large
            if use_large_model
            else settings.llm_model_small
        )
        user_content = build_user_content(
            title, state_summary, existing_events, new_articles
        )

        try:
            resp = self._client.messages.create(
                model=model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": ARC_DECISION_SCHEMA,
                    }
                },
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception:  # network / API error — transient, retry next pass
            logger.exception("Anthropic synthesis call failed for story %r", title)
            return ArcDecision(change="no_change", deferred=True)

        if resp.stop_reason == "refusal":
            logger.warning("Synthesis refused for story %r", title)
            return ArcDecision(change="no_change")

        text = next((b.text for b in resp.content if b.type == "text"), None)
        if not text:
            return ArcDecision(change="no_change")

        # Structured output guarantees JSON; validate against our model and
        # discard (never repair) anything that doesn't fit.
        try:
            return ArcDecision.model_validate(json.loads(text))
        except Exception:
            logger.exception("Discarding unparseable synthesis output: %s", text[:500])
            return ArcDecision(change="no_change")
