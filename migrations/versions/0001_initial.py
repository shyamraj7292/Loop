"""initial schema

Creates the pgvector extension, all tables from the README data model, and the
indexes that matter (HNSW on the vector columns, plus the read-state and
story-activity indexes).

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-05
"""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

EMBED_DIM = 384  # bge-small-en-v1.5


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.execute(
        """
        CREATE TABLE sources (
            id               SERIAL PRIMARY KEY,
            name             VARCHAR(256) NOT NULL,
            feed_url         VARCHAR(1024) NOT NULL UNIQUE,
            homepage         VARCHAR(1024),
            country          VARCHAR(8),
            lang             VARCHAR(8),
            authority_weight DOUBLE PRECISION NOT NULL DEFAULT 0,
            etag             VARCHAR(512),
            last_modified    VARCHAR(256),
            last_fetched     TIMESTAMPTZ,
            active           BOOLEAN NOT NULL DEFAULT TRUE
        );
        """
    )

    op.execute(
        f"""
        CREATE TABLE articles (
            id                        SERIAL PRIMARY KEY,
            source_id                 INTEGER NOT NULL
                                          REFERENCES sources(id) ON DELETE CASCADE,
            url_canonical             VARCHAR(2048) NOT NULL UNIQUE,
            title                     TEXT,
            author                    VARCHAR(512),
            published_at              TIMESTAMPTZ,
            fetched_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
            simhash                   BIGINT,
            lang                      VARCHAR(8),
            embedding                 vector({EMBED_DIM}),
            body_text                 TEXT,
            body_retention_expires_at TIMESTAMPTZ,
            synthesized_at            TIMESTAMPTZ
        );
        """
    )
    op.execute("CREATE INDEX ix_articles_source_id ON articles(source_id);")
    op.execute("CREATE INDEX ix_articles_simhash ON articles(simhash);")

    op.execute(
        f"""
        CREATE TABLE stories (
            id            SERIAL PRIMARY KEY,
            title         TEXT,
            slug          VARCHAR(512),
            centroid      vector({EMBED_DIM}),
            state_summary TEXT,
            first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_activity TIMESTAMPTZ NOT NULL DEFAULT now(),
            status        VARCHAR(16) NOT NULL DEFAULT 'active',
            importance    DOUBLE PRECISION NOT NULL DEFAULT 0,
            topic_tags    VARCHAR[] NOT NULL DEFAULT '{{}}'
        );
        """
    )
    op.execute("CREATE INDEX ix_stories_slug ON stories(slug);")
    op.execute(
        "CREATE INDEX ix_stories_status_last_activity "
        "ON stories(status, last_activity DESC);"
    )

    op.execute(
        """
        CREATE TABLE story_articles (
            story_id   INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
            article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            similarity DOUBLE PRECISION,
            PRIMARY KEY (story_id, article_id)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE events (
            id                 SERIAL PRIMARY KEY,
            story_id           INTEGER NOT NULL
                                   REFERENCES stories(id) ON DELETE CASCADE,
            occurred_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            summary            TEXT NOT NULL,
            claims             JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_article_ids INTEGER[] NOT NULL DEFAULT '{}',
            novelty_score      DOUBLE PRECISION
        );
        """
    )
    op.execute("CREATE INDEX ix_events_story_id ON events(story_id);")

    op.execute(
        """
        CREATE TABLE users (
            id           SERIAL PRIMARY KEY,
            email        VARCHAR(320) NOT NULL UNIQUE,
            tz           VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata',
            digest_time  VARCHAR(8) NOT NULL DEFAULT '06:00',
            brief_length INTEGER NOT NULL DEFAULT 5,
            channels     VARCHAR[] NOT NULL DEFAULT '{}',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE user_topics (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            topic   VARCHAR(128) NOT NULL,
            weight  DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            PRIMARY KEY (user_id, topic)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE user_read_state (
            user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, event_id)
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_user_read_state_user_seen "
        "ON user_read_state(user_id, seen_at DESC);"
    )

    # Vector indexes (HNSW, cosine). Built last so table creation is cheap.
    op.execute(
        "CREATE INDEX ix_articles_embedding_hnsw "
        "ON articles USING hnsw (embedding vector_cosine_ops);"
    )
    op.execute(
        "CREATE INDEX ix_stories_centroid_hnsw "
        "ON stories USING hnsw (centroid vector_cosine_ops);"
    )


def downgrade() -> None:
    for table in (
        "user_read_state",
        "user_topics",
        "users",
        "events",
        "story_articles",
        "stories",
        "articles",
        "sources",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
