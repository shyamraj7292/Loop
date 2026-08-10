"""Google Gemini backend for arc synthesis.

Talks to the Gemini REST API over httpx (already a dependency), so no extra SDK
and no image rebuild are needed. Uses Gemini's structured-output support
(`responseMimeType: application/json` + `responseSchema`) to get typed JSON, and
applies the same security posture as the Anthropic backend: article text is
delimited untrusted DATA, and any response that doesn't validate is discarded.

The API key is sent in the `x-goog-api-key` header, never in the URL (privacy:
no secrets in query strings).
"""

from __future__ import annotations

import json
import logging

import httpx

from loop.config import settings
from loop.llm.base import (
    SYSTEM_PROMPT,
    ArcDecision,
    ArticleSnippet,
    build_user_content,
)

logger = logging.getLogger(__name__)

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Gemini responseSchema uses an OpenAPI-3 subset with UPPERCASE Type enums and no
# `additionalProperties`. Only `change` is required so `no_change` needn't carry
# an event; the pipeline's grounding step is the real guard on event content.
_GEMINI_ARC_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "change": {"type": "STRING", "enum": ["no_change", "new_event"]},
        "state_summary": {"type": "STRING", "nullable": True},
        "event": {
            "type": "OBJECT",
            "nullable": True,
            "properties": {
                "summary": {"type": "STRING"},
                "novelty_score": {"type": "NUMBER"},
                "claims": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "text": {"type": "STRING"},
                            "source_article_ids": {
                                "type": "ARRAY",
                                "items": {"type": "INTEGER"},
                            },
                            "confidence": {"type": "NUMBER"},
                        },
                        "required": ["text", "source_article_ids", "confidence"],
                    },
                },
            },
            "required": ["summary", "claims", "novelty_score"],
        },
    },
    "required": ["change"],
}


class GeminiClient:
    def __init__(self) -> None:
        if not settings.gemini_api_key:
            logger.warning(
                "GEMINI_API_KEY is empty; synthesis calls will fail. "
                "Set it in .env or switch LLM_BACKEND=mock."
            )
        self._api_key = settings.gemini_api_key

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
            settings.gemini_model_large
            if use_large_model
            else settings.gemini_model_small
        )
        user_content = build_user_content(
            title, state_summary, existing_events, new_articles
        )

        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user_content}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _GEMINI_ARC_SCHEMA,
                "maxOutputTokens": 2048,
                "temperature": 0.2,
            },
        }

        try:
            resp = httpx.post(
                _ENDPOINT.format(model=model),
                headers={
                    "x-goog-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60.0,
            )
        except httpx.HTTPError:
            logger.exception("Gemini synthesis call failed for story %r", title)
            return ArcDecision(change="no_change")

        if resp.status_code >= 400:
            logger.warning(
                "Gemini HTTP %s for story %r: %s",
                resp.status_code,
                title,
                resp.text[:300],
            )
            return ArcDecision(change="no_change")

        text = self._extract_text(resp.json())
        if not text:
            return ArcDecision(change="no_change")

        try:
            return ArcDecision.model_validate(json.loads(text))
        except Exception:
            logger.exception("Discarding unparseable Gemini output: %s", text[:500])
            return ArcDecision(change="no_change")

    @staticmethod
    def _extract_text(data: dict) -> str | None:
        # Blocked prompt (safety) → no candidates.
        if data.get("promptFeedback", {}).get("blockReason"):
            logger.warning("Gemini blocked prompt: %s", data["promptFeedback"])
            return None
        candidates = data.get("candidates") or []
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts") or []
        texts = [p.get("text", "") for p in parts if "text" in p]
        return "".join(texts) or None
