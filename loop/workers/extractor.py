"""Article body extraction + retention enforcement.

`trafilatura` pulls the main article text out of the page HTML. Bodies are
stored only long enough to embed and summarise, then expired
(BODY_RETENTION_HOURS) — Loop paraphrases and links out, it never redistributes
full text (README > Legal and ethical constraints).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
import trafilatura
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from loop.config import settings
from loop.models import Article

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _pending(session: Session, limit: int) -> list[Article]:
    """Articles that still need a body pulled, that haven't already expired."""
    now = _utcnow()
    return list(
        session.execute(
            select(Article)
            .where(
                Article.body_text.is_(None),
                (Article.body_retention_expires_at.is_(None))
                | (Article.body_retention_expires_at > now),
            )
            .order_by(Article.id.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def extract_pending(session: Session, *, limit: int = 200) -> int:
    """Fetch + extract bodies for pending articles. Returns count extracted."""
    articles = _pending(session, limit)
    if not articles:
        return 0

    extracted = 0
    headers = {"User-Agent": settings.user_agent}
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        for article in articles:
            try:
                resp = client.get(article.url_canonical)
            except httpx.HTTPError as exc:
                logger.debug("Body fetch failed for %s: %s", article.url_canonical, exc)
                continue
            if resp.status_code >= 400:
                continue

            body = trafilatura.extract(
                resp.text,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
            if not body:
                continue

            article.body_text = body
            extracted += 1
            session.flush()

    if extracted:
        logger.info("Extracted %d article body(ies)", extracted)
    return extracted


def expire_bodies(session: Session) -> int:
    """Null out body text past its retention window. Returns rows affected."""
    now = _utcnow()
    result = session.execute(
        update(Article)
        .where(
            Article.body_text.is_not(None),
            Article.body_retention_expires_at.is_not(None),
            Article.body_retention_expires_at <= now,
        )
        .values(body_text=None)
    )
    count = result.rowcount or 0
    if count:
        logger.info("Expired %d article body(ies) past retention", count)
    return count
