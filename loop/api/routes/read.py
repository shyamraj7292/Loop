"""POST /api/read — mark events as seen for the current user."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from loop.api.deps import current_user, db
from loop.models import Event, User, UserReadState

router = APIRouter(prefix="/api", tags=["read-state"])


class ReadRequest(BaseModel):
    event_ids: list[int]


@router.post("/read")
def mark_read(
    payload: ReadRequest,
    user: User = Depends(current_user),
    session: Session = Depends(db),
) -> dict:
    # Only accept ids that exist and aren't already recorded.
    valid = set(
        session.execute(
            select(Event.id).where(Event.id.in_(payload.event_ids))
        ).scalars().all()
    )
    already = set(
        session.execute(
            select(UserReadState.event_id).where(
                UserReadState.user_id == user.id,
                UserReadState.event_id.in_(valid),
            )
        ).scalars().all()
    )
    now = datetime.now(timezone.utc)
    to_add = valid - already
    for event_id in to_add:
        session.add(
            UserReadState(user_id=user.id, event_id=event_id, seen_at=now)
        )
    session.commit()
    return {"marked": len(to_add), "already_seen": len(already)}
