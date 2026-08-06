"""GET /api/search — story-level search (not article-level).

The v0.1 slice is a lexical search over story titles and state summaries. The
embeddings and pgvector index are already in place, so a semantic upgrade is a
query change, not a schema change.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from loop.api.deps import db
from loop.models import Story

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, le=100),
    session: Session = Depends(db),
) -> dict:
    like = f"%{q}%"
    stories = session.execute(
        select(Story)
        .where(or_(Story.title.ilike(like), Story.state_summary.ilike(like)))
        .order_by(Story.importance.desc(), Story.last_activity.desc())
        .limit(limit)
    ).scalars().all()
    return {
        "query": q,
        "results": [
            {
                "id": s.id,
                "title": s.title,
                "slug": s.slug,
                "state_summary": s.state_summary,
                "importance": round(s.importance, 3),
            }
            for s in stories
        ],
    }
