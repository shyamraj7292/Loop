"""Ranking: importance, personalisation, and the reading-time budget.

    importance = distinct_source_count x source_authority x velocity
    personal   = importance + lambda * affinity(user, story) - seen_penalty

distinct_source_count is the single strongest signal available (README > Rank):
thirty independent outlets covering something means it matters, regardless of
what any individual headline claims. The raw product is squashed into (0, 1) so
the IMPORTANCE_THRESHOLD_LARGE_MODEL gate is interpretable.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from loop.config import settings
from loop.models import Article, Source, Story, StoryArticle, User, UserTopic

logger = logging.getLogger(__name__)

# Squashes raw importance into (0, 1). Tuned so a story with ~5 distinct
# high-authority sources and modest velocity lands near the 0.7 large-model gate.
_IMPORTANCE_SCALE = 6.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _story_source_stats(session: Session, story_id: int) -> tuple[int, float]:
    """(distinct source count, mean authority weight) for a story."""
    rows = session.execute(
        select(Source.id, Source.authority_weight)
        .join(Article, Article.source_id == Source.id)
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .where(StoryArticle.story_id == story_id)
        .distinct()
    ).all()
    if not rows:
        return 0, 0.0
    weights = [float(w or 0.0) for _, w in rows]
    return len(rows), sum(weights) / len(weights)


def _velocity(session: Session, story_id: int) -> float:
    """Articles attached in the last 24h, floored at 1 so any live story counts."""
    cutoff = _utcnow() - timedelta(hours=24)
    count = session.execute(
        select(func.count())
        .select_from(StoryArticle)
        .join(Article, Article.id == StoryArticle.article_id)
        .where(StoryArticle.story_id == story_id, Article.fetched_at >= cutoff)
    ).scalar_one()
    return float(max(count, 1))


def compute_importance(session: Session, story: Story) -> float:
    distinct_sources, mean_authority = _story_source_stats(session, story.id)
    if distinct_sources == 0:
        return 0.0
    velocity = _velocity(session, story.id)
    raw = distinct_sources * mean_authority * velocity
    return 1.0 - math.exp(-raw / _IMPORTANCE_SCALE)


def rank_stories(session: Session) -> int:
    """Recompute and persist importance for every active story."""
    stories = list(
        session.execute(select(Story).where(Story.status == "active"))
        .scalars()
        .all()
    )
    for story in stories:
        story.importance = compute_importance(session, story)
    if stories:
        logger.info("Ranked %d active story(ies)", len(stories))
    return len(stories)


def topic_affinity(session: Session, user_id: int, story: Story) -> float:
    """Sum of the user's topic weights that match the story's tags, capped at 1."""
    if not story.topic_tags:
        return 0.0
    rows = session.execute(
        select(UserTopic.topic, UserTopic.weight).where(
            UserTopic.user_id == user_id, UserTopic.topic.in_(story.topic_tags)
        )
    ).all()
    return min(sum(float(w) for _, w in rows), 1.0)


def personal_score(
    session: Session, user: User, story: Story, *, seen_fraction: float
) -> float:
    """importance + lambda * affinity - seen_penalty * seen_fraction."""
    affinity = topic_affinity(session, user.id, story)
    return (
        story.importance
        + settings.personalization_lambda * affinity
        - settings.seen_penalty * seen_fraction
    )
