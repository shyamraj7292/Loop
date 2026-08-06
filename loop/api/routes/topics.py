"""GET/PUT /api/topics — the user's interest weights."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from loop.api.deps import current_user, db
from loop.models import User, UserTopic

router = APIRouter(prefix="/api", tags=["topics"])


class TopicWeight(BaseModel):
    topic: str
    weight: float = 1.0


class TopicsUpdate(BaseModel):
    topics: list[TopicWeight]


@router.get("/topics")
def get_topics(
    user: User = Depends(current_user), session: Session = Depends(db)
) -> dict:
    rows = session.execute(
        select(UserTopic).where(UserTopic.user_id == user.id)
    ).scalars().all()
    return {"topics": [{"topic": r.topic, "weight": r.weight} for r in rows]}


@router.put("/topics")
def put_topics(
    payload: TopicsUpdate,
    user: User = Depends(current_user),
    session: Session = Depends(db),
) -> dict:
    # Full replacement of the user's interest vector.
    existing = {
        r.topic: r
        for r in session.execute(
            select(UserTopic).where(UserTopic.user_id == user.id)
        ).scalars().all()
    }
    incoming = {t.topic: t.weight for t in payload.topics}

    for topic, row in existing.items():
        if topic not in incoming:
            session.delete(row)
    for topic, weight in incoming.items():
        if topic in existing:
            existing[topic].weight = weight
        else:
            session.add(UserTopic(user_id=user.id, topic=topic, weight=weight))

    session.commit()
    return {"topics": [{"topic": t, "weight": w} for t, w in incoming.items()]}
