"""LLM contract shared by every backend.

The synthesis step is the heart of the product (README > Story arc state): given
the current state and the existing event list, the model must return either
`no_change` or *exactly one* new event. Forcing that binary is what keeps arcs
from bloating and is what gives the "what's new" delta for free.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ArticleSnippet(BaseModel):
    """A single new article handed to the model as delimited, untrusted data."""

    article_id: int
    source: str
    title: str | None = None
    published_at: str | None = None
    body: str


class Claim(BaseModel):
    """A factual claim with the article IDs that support it.

    Grounding rule (README > Security model): a claim with an empty support
    array never reaches a user. The validator enforces the shape; the pipeline
    (loop.pipeline.grounding) enforces the drop.
    """

    text: str
    source_article_ids: list[int] = Field(default_factory=list)
    confidence: float = 0.5


class NewEvent(BaseModel):
    summary: str
    claims: list[Claim] = Field(default_factory=list)
    novelty_score: float = 0.5


class ArcDecision(BaseModel):
    """The model's typed verdict for one synthesis pass."""

    change: Literal["no_change", "new_event"]
    # Present only when change == "new_event".
    event: NewEvent | None = None
    # An updated rolling state summary (present when the arc moved).
    state_summary: str | None = None


# JSON Schema handed to the Anthropic structured-output API. Kept in lockstep
# with ArcDecision above. Structured outputs require additionalProperties:false
# and explicit `required` on every object.
ARC_DECISION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "change": {"type": "string", "enum": ["no_change", "new_event"]},
        "state_summary": {"type": ["string", "null"]},
        "event": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "novelty_score": {"type": "number"},
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "text": {"type": "string"},
                            "source_article_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                            "confidence": {"type": "number"},
                        },
                        "required": ["text", "source_article_ids", "confidence"],
                    },
                },
                "required": ["summary", "claims", "novelty_score"],
            },
        },
    },
    "required": ["change", "event", "state_summary"],
}


@runtime_checkable
class LLMClient(Protocol):
    def synthesize_arc(
        self,
        *,
        title: str | None,
        state_summary: str | None,
        existing_events: list[str],
        new_articles: list[ArticleSnippet],
        use_large_model: bool,
    ) -> ArcDecision:
        """Decide whether new articles move the story, and if so, how."""
        ...
