"""Story routes: full arc, and the per-user unseen-events delta."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from loop.api.deps import current_user, db
from loop.models import Event, Story, User, UserReadState

router = APIRouter(prefix="/api", tags=["stories"])


def _event_dict(event: Event) -> dict:
    return {
        "id": event.id,
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        "summary": event.summary,
        "claims": event.claims,
        "source_article_ids": event.source_article_ids,
        "novelty_score": event.novelty_score,
    }


@router.get("/stories/{story_id}")
def get_story(story_id: int, session: Session = Depends(db)) -> dict:
    story = session.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    events = session.execute(
        select(Event).where(Event.story_id == story_id).order_by(Event.occurred_at)
    ).scalars().all()
    return {
        "id": story.id,
        "title": story.title,
        "slug": story.slug,
        "state_summary": story.state_summary,
        "status": story.status,
        "importance": round(story.importance, 3),
        "topic_tags": story.topic_tags,
        "first_seen": story.first_seen.isoformat() if story.first_seen else None,
        "last_activity": story.last_activity.isoformat()
        if story.last_activity
        else None,
        "events": [_event_dict(e) for e in events],
    }


@router.get("/stories/{story_id}/delta")
def get_story_delta(
    story_id: int,
    user: User = Depends(current_user),
    session: Session = Depends(db),
) -> dict:
    """Only the events in this story that the user hasn't seen yet."""
    story = session.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")

    seen = set(
        session.execute(
            select(UserReadState.event_id).where(UserReadState.user_id == user.id)
        ).scalars().all()
    )
    events = session.execute(
        select(Event).where(Event.story_id == story_id).order_by(Event.occurred_at)
    ).scalars().all()
    unseen = [e for e in events if e.id not in seen]
    return {
        "story_id": story_id,
        "unseen_event_count": len(unseen),
        "events": [_event_dict(e) for e in unseen],
    }
