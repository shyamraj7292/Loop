"""Shared FastAPI dependencies.

Auth is intentionally minimal for the v0.1 slice: the current user is taken from
the `X-User-Id` header, defaulting to user 1 (the dev user created by seeding).
Real auth (sessions / tokens) is a v0.2 item — the route contract doesn't change.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from loop.db import get_session
from loop.models import User


def db() -> Iterator[Session]:
    yield from get_session()


def current_user(
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    session: Session = Depends(db),
) -> User:
    user = session.get(User, x_user_id)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail=(
                f"Unknown user id {x_user_id}. Seed a dev user with "
                "`python -m loop.seed`, or set the X-User-Id header."
            ),
        )
    return user
