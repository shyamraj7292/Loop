"""Deterministic mock LLM.

Lets the whole pipeline run end-to-end with zero API cost or keys — useful for
local development and tests. It emits a single event per synthesis pass, grounded
in the supplied articles, so grounding and delta logic have real data to chew on.
"""

from __future__ import annotations

from loop.llm.base import ArcDecision, ArticleSnippet, Claim, NewEvent


class MockClient:
    def synthesize_arc(
        self,
        *,
        title: str | None,
        state_summary: str | None,
        existing_events: list[str],
        new_articles: list[ArticleSnippet],
        use_large_model: bool,
    ) -> ArcDecision:
        if not new_articles:
            return ArcDecision(change="no_change")

        lead = new_articles[0]
        headline = (lead.title or lead.body[:120] or "Development").strip()
        ids = [a.article_id for a in new_articles]

        event = NewEvent(
            summary=f"[mock] {headline}",
            claims=[
                Claim(
                    text=f"Reported by {lead.source}: {headline}",
                    source_article_ids=ids,
                    confidence=0.6,
                )
            ],
            novelty_score=0.5,
        )
        summary = (
            f"[mock state] {headline} "
            f"({len(existing_events) + 1} events tracked)."
        )
        return ArcDecision(change="new_event", event=event, state_summary=summary)
