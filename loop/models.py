"""SQLAlchemy models — the data model from the README, one-to-one.

A *story* is the central object: a persistent thing with a current state
(`state_summary`) and an ordered event timeline (`events`). Per-user read state
lives at the *event* level, which is what makes the "what's new since you were
gone" delta possible.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from loop.config import settings
from loop.db import Base

EMBED_DIM = settings.embed_dim


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    feed_url: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    homepage: Mapped[str | None] = mapped_column(String(1024))
    country: Mapped[str | None] = mapped_column(String(8))
    lang: Mapped[str | None] = mapped_column(String(8))
    # Topical bucket (world, business, technology, sports, ...). Used to group
    # the brief into named, collapsible sections.
    category: Mapped[str | None] = mapped_column(String(32))
    # Hand-assigned 0..1 authority score used in ranking.
    authority_weight: Mapped[float] = mapped_column(Float, default=0.0)

    # Conditional-GET bookkeeping so we don't re-download unchanged feeds.
    etag: Mapped[str | None] = mapped_column(String(512))
    last_modified: Mapped[str | None] = mapped_column(String(256))
    last_fetched: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    active: Mapped[bool] = mapped_column(Boolean, default=True)

    articles: Mapped[list[Article]] = relationship(back_populates="source")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    url_canonical: Mapped[str] = mapped_column(
        String(2048), unique=True, nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(512))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # 64-bit simhash stored as signed BIGINT (see loop.pipeline.dedup).
    simhash: Mapped[int | None] = mapped_column(BigInteger, index=True)
    lang: Mapped[str | None] = mapped_column(String(8))

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))

    # Body text is transient — expired after BODY_RETENTION_HOURS to respect
    # publisher copyright. We keep the embedding and the summary, not the text.
    body_text: Mapped[str | None] = mapped_column(Text)
    body_retention_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Set once the article has been through arc synthesis, so a "no_change"
    # verdict doesn't cause the same article to be reprocessed forever.
    synthesized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    source: Mapped[Source] = relationship(back_populates="articles")


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str | None] = mapped_column(Text)
    slug: Mapped[str | None] = mapped_column(String(512), index=True)

    centroid: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    state_summary: Mapped[str | None] = mapped_column(Text)

    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    # active | dormant | merged
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    importance: Mapped[float] = mapped_column(Float, default=0.0)
    topic_tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    events: Mapped[list[Event]] = relationship(
        back_populates="story", order_by="Event.occurred_at"
    )


class StoryArticle(Base):
    __tablename__ = "story_articles"

    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True
    )
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    similarity: Mapped[float | None] = mapped_column(Float)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # [{text, source_article_ids[], confidence}] — grounding lives here.
    # A claim with an empty support array never reaches a user.
    claims: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    source_article_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    novelty_score: Mapped[float | None] = mapped_column(Float)

    story: Mapped[Story] = relationship(back_populates="events")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    tz: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    digest_time: Mapped[str] = mapped_column(String(8), default="06:00")
    brief_length: Mapped[int] = mapped_column(Integer, default=5)  # minutes
    channels: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class UserTopic(Base):
    __tablename__ = "user_topics"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    topic: Mapped[str] = mapped_column(String(128), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)


class UserReadState(Base):
    __tablename__ = "user_read_state"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_user_read_state"),
    )
