"""Arc synthesis — turning new articles into story events.

This is where the delta comes from (README > Story arc state). Each story holds
a rolling `state_summary` plus an ordered list of events. When new articles land,
the model receives the current state and the existing event list and must return
either `no_change` or exactly one new event.

Two gates protect the expensive model and the corroboration floor:
  * freshness gate  — suppress synthesis on very new stories
  * min-sources     — require independent coverage before synthesising
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from loop.config import settings
from loop.llm import get_llm
from loop.llm.base import ArticleSnippet
from loop.models import Article, Event, Source, Story, StoryArticle
from loop.pipeline.grounding import validate_claims
from loop.pipeline.rank import compute_importance

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stories_with_new_articles(session: Session) -> list[Story]:
    story_ids = session.execute(
        select(distinct(StoryArticle.story_id))
        .join(Article, Article.id == StoryArticle.article_id)
        .join(Story, Story.id == StoryArticle.story_id)
        .where(Article.synthesized_at.is_(None), Story.status == "active")
    ).scalars().all()
    if not story_ids:
        return []
    return list(
        session.execute(select(Story).where(Story.id.in_(story_ids)))
        .scalars()
        .all()
    )


def _new_articles_for(session: Session, story: Story) -> list[Article]:
    return list(
        session.execute(
            select(Article)
            .join(StoryArticle, StoryArticle.article_id == Article.id)
            .where(
                StoryArticle.story_id == story.id,
                Article.synthesized_at.is_(None),
            )
            .order_by(Article.published_at.asc().nullslast(), Article.id.asc())
        )
        .scalars()
        .all()
    )


def _distinct_source_count(session: Session, story_id: int) -> int:
    return session.execute(
        select(func.count(distinct(Article.source_id)))
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .where(StoryArticle.story_id == story_id)
    ).scalar_one()


def _all_article_ids(session: Session, story_id: int) -> set[int]:
    return set(
        session.execute(
            select(StoryArticle.article_id).where(StoryArticle.story_id == story_id)
        ).scalars().all()
    )


def _snippet(session: Session, article: Article) -> ArticleSnippet:
    source_name = session.get(Source, article.source_id)
    return ArticleSnippet(
        article_id=article.id,
        source=source_name.name if source_name else "unknown",
        title=article.title,
        published_at=article.published_at.isoformat() if article.published_at else None,
        body=article.body_text or article.title or "",
    )


def synthesize_story(session: Session, story: Story) -> Event | None:
    """Run one synthesis pass for a single story. Returns the new event, if any."""
    new_articles = _new_articles_for(session, story)
    if not new_articles:
        return None

    # Freshness gate: give a brand-new story a moment to accrue coverage before
    # we spend a model call on it.
    if _utcnow() - story.first_seen < timedelta(hours=settings.freshness_gate_hours):
        logger.debug("Story %s within freshness gate; deferring", story.id)
        return None

    # Corroboration floor.
    if _distinct_source_count(session, story.id) < settings.min_sources_for_synthesis:
        logger.debug("Story %s below source floor; deferring", story.id)
        return None

    # Cost control: only high-importance stories reach the strong model.
    importance = compute_importance(session, story)
    story.importance = importance
    use_large = importance >= settings.importance_threshold_large_model

    decision = get_llm().synthesize_arc(
        title=story.title,
        state_summary=story.state_summary,
        existing_events=[e.summary for e in story.events],
        new_articles=[_snippet(session, a) for a in new_articles],
        use_large_model=use_large,
    )

    now = _utcnow()
    event: Event | None = None

    if decision.change == "new_event" and decision.event is not None:
        allowed = _all_article_ids(session, story.id)
        grounded = validate_claims(decision.event.claims, allowed)
        if grounded:
            support_ids = sorted(
                {i for c in grounded for i in c.source_article_ids}
            )
            event = Event(
                story_id=story.id,
                occurred_at=now,
                summary=decision.event.summary,
                claims=[c.model_dump() for c in grounded],
                source_article_ids=support_ids,
                novelty_score=decision.event.novelty_score,
            )
            session.add(event)
            if decision.state_summary:
                story.state_summary = decision.state_summary
            if not story.title and decision.event.summary:
                story.title = decision.event.summary[:200]
            story.last_activity = now
            logger.info("Story %s gained an event (large=%s)", story.id, use_large)
        else:
            logger.info("Story %s event dropped: no grounded claims", story.id)

    # Mark processed regardless of outcome so a `no_change` (or a dropped event)
    # doesn't cause the same articles to be resynthesised every run.
    for article in new_articles:
        article.synthesized_at = now

    return event


def synthesize_stories(session: Session) -> int:
    """Synthesise every story that has unprocessed articles. Returns event count."""
    stories = _stories_with_new_articles(session)
    events = 0
    for story in stories:
        if synthesize_story(session, story) is not None:
            events += 1
        session.flush()
    if stories:
        logger.info(
            "Synthesis pass: %d story(ies), %d new event(s)", len(stories), events
        )
    return events
