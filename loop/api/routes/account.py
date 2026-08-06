"""DELETE /api/account — full, cascading account deletion.

DPDP-aligned (README > Privacy): the deletion path must genuinely cascade. The
FKs on user_topics and user_read_state are ON DELETE CASCADE, so removing the
user row removes all derived personal data with it. Story/event data is not
personal and is retained.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from loop.api.deps import current_user, db
from loop.models import User

router = APIRouter(prefix="/api", tags=["account"])


@router.delete("/account")
def delete_account(
    user: User = Depends(current_user), session: Session = Depends(db)
) -> dict:
    user_id = user.id
    session.delete(user)  # cascades to user_topics + user_read_state
    session.commit()
    return {"deleted": True, "user_id": user_id}
