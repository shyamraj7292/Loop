"""GET /api/brief — the current brief for the authenticated user, with delta."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from loop.api.deps import current_user, db
from loop.delivery.brief import build_brief
from loop.models import User

router = APIRouter(prefix="/api", tags=["brief"])


@router.get("/brief")
def get_brief(
    length: int = Query(default=5, description="Reading-time budget: 2, 5, or 15."),
    user: User = Depends(current_user),
    session: Session = Depends(db),
) -> dict:
    return build_brief(session, user, length=length)
