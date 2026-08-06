"""Sentence-transformer embeddings.

`bge-small-en-v1.5` (384 dims) runs fine on CPU at zero API cost (README > Embed
and cluster). The model is heavy to import (pulls torch), so it is loaded lazily
and cached — nothing that merely imports this module pays that cost.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from loop.config import settings

logger = logging.getLogger(__name__)

# bge models want a short instruction prefix on the *query* side; for symmetric
# clustering of documents we embed raw text on both sides, which is fine.


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    logger.info("Loading embedding model %s", settings.embed_model)
    return SentenceTransformer(settings.embed_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts, L2-normalised so cosine == dot product."""
    if not texts:
        return []
    vectors = _model().encode(
        texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vectors]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def article_embedding_text(title: str | None, body: str | None) -> str:
    """The text we actually embed for an article: title carries a lot of the
    clustering signal, so it leads, followed by a bounded slice of the body."""
    title = (title or "").strip()
    body = (body or "").strip()
    if not body:
        return title
    return f"{title}\n\n{body[:1000]}"


def embed_pending(session, *, batch_size: int = 64) -> int:
    """Embed (and simhash) articles that have text but no vector yet.

    Kept here rather than in a worker so the heavy model import stays in one
    place. Returns the number of articles embedded.
    """
    # Local imports to avoid a circular import at module load.
    from sqlalchemy import or_, select

    from loop.models import Article
    from loop.pipeline.dedup import simhash

    articles = list(
        session.execute(
            select(Article)
            .where(
                Article.embedding.is_(None),
                or_(Article.title.is_not(None), Article.body_text.is_not(None)),
            )
            .order_by(Article.id.asc())
            .limit(batch_size)
        )
        .scalars()
        .all()
    )
    if not articles:
        return 0

    texts = [article_embedding_text(a.title, a.body_text) for a in articles]
    vectors = embed_texts(texts)
    for article, vector, text in zip(articles, vectors, texts):
        article.embedding = vector
        if article.simhash is None:
            article.simhash = simhash(text)
    logger.info("Embedded %d article(s)", len(articles))
    return len(articles)
