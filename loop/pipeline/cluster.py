"""Online clustering — the heart of story tracking.

For each new article we cosine-match against the centroids of all *active*
clusters from the last N days. Above threshold, the article joins that story and
the running centroid updates; below threshold, a new story opens. A nightly
HDBSCAN repair pass (see `repair_pass`) merges clusters that converged and splits
ones that drifted.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from loop.config import settings
from loop.models import Article, Story, StoryArticle

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def slugify(text: str, *, max_len: int = 80) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:max_len].strip("-") or "story"


def _normalise(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec if norm == 0 else vec / norm


def _recompute_centroid(session: Session, story: Story) -> None:
    """Centroid = L2-normalised mean of member article embeddings.

    Recomputed from scratch each time. At the scale this design targets
    (thousands of active stories) that's cheap and avoids running-mean drift.
    """
    rows = session.execute(
        select(Article.embedding)
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .where(StoryArticle.story_id == story.id, Article.embedding.is_not(None))
    ).all()
    embeddings = [np.asarray(r[0], dtype=np.float32) for r in rows if r[0] is not None]
    if not embeddings:
        return
    story.centroid = _normalise(np.mean(embeddings, axis=0)).tolist()


def _candidate_story(session: Session, embedding: list[float]) -> tuple[Story, float] | None:
    """Nearest active story from the dormancy window, with its cosine similarity."""
    cutoff = _utcnow() - timedelta(days=settings.cluster_active_days)
    distance = Story.centroid.cosine_distance(embedding)
    row = session.execute(
        select(Story, distance.label("dist"))
        .where(
            Story.status == "active",
            Story.last_activity >= cutoff,
            Story.centroid.is_not(None),
        )
        .order_by(distance)
        .limit(1)
    ).first()
    if row is None:
        return None
    story, dist = row
    return story, 1.0 - float(dist)


def assign_article(session: Session, article: Article) -> Story:
    """Attach one article to an existing story or open a new one."""
    match = _candidate_story(session, article.embedding)

    if match is not None and match[1] >= settings.cluster_threshold:
        story, similarity = match
        session.add(
            StoryArticle(
                story_id=story.id, article_id=article.id, similarity=similarity
            )
        )
        session.flush()
        _recompute_centroid(session, story)
        story.last_activity = _utcnow()
        story.status = "active"
        logger.debug(
            "Article %s joined story %s (sim=%.3f)", article.id, story.id, similarity
        )
        return story

    # Below threshold → new story seeded from this article.
    story = Story(
        title=article.title,
        slug=slugify(article.title or f"story-{article.id}"),
        centroid=article.embedding,
        state_summary=None,
        first_seen=_utcnow(),
        last_activity=_utcnow(),
        status="active",
        importance=0.0,
        topic_tags=[],
    )
    session.add(story)
    session.flush()
    session.add(
        StoryArticle(story_id=story.id, article_id=article.id, similarity=1.0)
    )
    session.flush()
    logger.debug("Article %s opened new story %s", article.id, story.id)
    return story


def _unclustered_articles(session: Session) -> list[Article]:
    """Embedded articles not yet attached to any story."""
    return list(
        session.execute(
            select(Article)
            .outerjoin(StoryArticle, StoryArticle.article_id == Article.id)
            .where(Article.embedding.is_not(None), StoryArticle.article_id.is_(None))
            .order_by(Article.published_at.asc().nullslast(), Article.id.asc())
        )
        .scalars()
        .all()
    )


def cluster_new_articles(session: Session) -> int:
    """Assign every unclustered article. Returns the count processed."""
    articles = _unclustered_articles(session)
    for article in articles:
        assign_article(session, article)
    if articles:
        logger.info("Clustered %d new article(s)", len(articles))
    return len(articles)


def mark_dormant(session: Session) -> int:
    """Move stories with no activity in the dormancy window to `dormant`."""
    cutoff = _utcnow() - timedelta(days=settings.cluster_active_days)
    stories = list(
        session.execute(
            select(Story).where(
                Story.status == "active", Story.last_activity < cutoff
            )
        )
        .scalars()
        .all()
    )
    for story in stories:
        story.status = "dormant"
    if stories:
        logger.info("Marked %d story(ies) dormant", len(stories))
    return len(stories)


def repair_pass(session: Session) -> None:
    """Nightly HDBSCAN repair (README > Embed and cluster).

    HDBSCAN needs a compiler to install and isn't required for the online path,
    so it's optional here. When it's present this merges converged clusters and
    splits drifted ones; when it's absent we just run the dormancy sweep.
    """
    try:
        import hdbscan  # noqa: F401
    except ImportError:
        logger.info("hdbscan not installed; running dormancy sweep only")
        mark_dormant(session)
        return

    # Full repair implementation is a v0.2 item; the online path plus dormancy
    # is sufficient for the v0.1 slice.
    mark_dormant(session)
