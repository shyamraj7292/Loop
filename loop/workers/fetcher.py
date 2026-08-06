"""Feed polling.

Feeds are polled with `ETag` / `If-Modified-Since` so we don't re-download
unchanged feeds (README > Ingest). New entries become `articles` rows with a
canonical URL; body text is filled in later by the extractor.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from time import struct_time

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from loop.config import settings
from loop.models import Article, Source
from loop.pipeline.dedup import canonical_url

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_datetime(parsed: struct_time | None) -> datetime | None:
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _existing_urls(session: Session, urls: list[str]) -> set[str]:
    if not urls:
        return set()
    return set(
        session.execute(
            select(Article.url_canonical).where(Article.url_canonical.in_(urls))
        ).scalars().all()
    )


def fetch_source(session: Session, source: Source, client: httpx.Client) -> int:
    """Poll one feed, insert new articles. Returns the number inserted."""
    headers = {"User-Agent": settings.user_agent}
    if source.etag:
        headers["If-None-Match"] = source.etag
    if source.last_modified:
        headers["If-Modified-Since"] = source.last_modified

    try:
        resp = client.get(source.feed_url, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("Feed fetch failed for %s: %s", source.name, exc)
        return 0

    source.last_fetched = _utcnow()

    if resp.status_code == 304:
        logger.debug("%s unchanged (304)", source.name)
        return 0
    if resp.status_code >= 400:
        logger.warning("%s returned HTTP %s", source.name, resp.status_code)
        return 0

    source.etag = resp.headers.get("ETag", source.etag)
    source.last_modified = resp.headers.get("Last-Modified", source.last_modified)

    feed = feedparser.parse(resp.content)

    # Build candidate rows first so we can do one existence check.
    candidates: list[dict] = []
    for entry in feed.entries:
        link = entry.get("link")
        if not link:
            continue
        candidates.append(
            {
                "url": canonical_url(link),
                "title": entry.get("title"),
                "author": entry.get("author"),
                "published_at": _to_datetime(
                    entry.get("published_parsed") or entry.get("updated_parsed")
                ),
            }
        )

    urls = [c["url"] for c in candidates]
    already = _existing_urls(session, urls)
    retention = timedelta(hours=settings.body_retention_hours)

    inserted = 0
    seen_this_batch: set[str] = set()
    for c in candidates:
        if c["url"] in already or c["url"] in seen_this_batch:
            continue
        seen_this_batch.add(c["url"])
        session.add(
            Article(
                source_id=source.id,
                url_canonical=c["url"],
                title=c["title"],
                author=c["author"],
                published_at=c["published_at"],
                fetched_at=_utcnow(),
                lang=source.lang,
                body_retention_expires_at=_utcnow() + retention,
            )
        )
        inserted += 1

    if inserted:
        logger.info("%s: +%d article(s)", source.name, inserted)
    return inserted


def fetch_all(session: Session) -> int:
    """Poll every active source. Returns total articles inserted."""
    sources = list(
        session.execute(select(Source).where(Source.active.is_(True)))
        .scalars()
        .all()
    )
    total = 0
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        for source in sources:
            total += fetch_source(session, source, client)
            session.flush()
    logger.info("Fetch complete: %d new article(s) across %d source(s)", total, len(sources))
    return total
