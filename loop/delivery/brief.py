"""Brief assembly — the read-state-aware delta.

Open Loop after twelve days and it tells you "8 stories moved, 2 are new", then
shows only the developments that happened while you were gone. That delta is the
entire product (README > The insight); everything else is plumbing that makes it
possible.

The `important_regardless` section is non-negotiable and cannot be disabled by
the user (README > Filter bubbles). Personalisation ranks the rest.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from loop.models import (
    Article,
    Event,
    Story,
    StoryArticle,
    User,
    UserReadState,
)
from loop.pipeline.rank import personal_score

# Reading-time budget -> number of stories to surface.
_LENGTH_BUDGET = {2: 4, 5: 8, 15: 20}

# A story is "important regardless" (shown to everyone) above this importance.
_IMPORTANT_THRESHOLD = 0.6


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _last_seen_at(session: Session, user_id: int) -> datetime | None:
    return session.execute(
        select(func.max(UserReadState.seen_at)).where(
            UserReadState.user_id == user_id
        )
    ).scalar_one_or_none()


def _seen_event_ids(session: Session, user_id: int) -> set[int]:
    return set(
        session.execute(
            select(UserReadState.event_id).where(UserReadState.user_id == user_id)
        ).scalars().all()
    )


def _distinct_sources(session: Session, story_id: int) -> int:
    return session.execute(
        select(func.count(func.distinct(Article.source_id)))
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .where(StoryArticle.story_id == story_id)
    ).scalar_one()


def _story_card(
    session: Session, story: Story, *, new_event_count: int
) -> dict:
    return {
        "id": story.id,
        "title": story.title,
        "slug": story.slug,
        "state_summary": story.state_summary,
        "new_event_count": new_event_count,
        "distinct_sources": _distinct_sources(session, story.id),
        "importance": round(story.importance, 3),
        "last_activity": story.last_activity.isoformat()
        if story.last_activity
        else None,
    }


def build_brief(session: Session, user: User, *, length: int = 5) -> dict:
    """Assemble the brief payload (matches README > API reference shape)."""
    now = _utcnow()
    last_seen = _last_seen_at(session, user.id)
    days_away = (now - last_seen).days if last_seen else 0

    seen_ids = _seen_event_ids(session, user.id)
    budget = _LENGTH_BUDGET.get(length, max(length, 3))

    # Candidate stories: active stories that carry at least one event.
    stories = list(
        session.execute(
            select(Story)
            .join(Event, Event.story_id == Story.id)
            .where(Story.status.in_(("active", "dormant")))
            .group_by(Story.id)
            .order_by(Story.importance.desc(), Story.last_activity.desc())
        )
        .scalars()
        .all()
    )

    stories_moved = 0
    stories_new = 0

    # Per-story: unseen event count and whether it counts as moved / new.
    enriched: list[tuple[Story, int, int]] = []  # (story, unseen, total)
    for story in stories:
        event_rows = session.execute(
            select(Event.id).where(Event.story_id == story.id)
        ).scalars().all()
        total = len(event_rows)
        unseen = sum(1 for eid in event_rows if eid not in seen_ids)
        if unseen == 0:
            continue
        enriched.append((story, unseen, total))
        # "New" if the user has never seen any of its events; "moved" otherwise.
        if last_seen is not None and story.first_seen > last_seen:
            stories_new += 1
        elif unseen == total:
            stories_new += 1
        else:
            stories_moved += 1

    # --- Section 1: important_regardless (never personalised, never disabled) ---
    important = [
        (s, unseen)
        for (s, unseen, _total) in enriched
        if s.importance >= _IMPORTANT_THRESHOLD
    ]
    important.sort(key=lambda t: t[0].importance, reverse=True)
    important = important[: max(budget // 2, 2)]
    important_ids = {s.id for s, _ in important}

    # --- Section 2: for_you (personalised ranking of the remainder) ---
    remainder = [
        (s, unseen, total)
        for (s, unseen, total) in enriched
        if s.id not in important_ids
    ]

    def _score(item: tuple[Story, int, int]) -> float:
        story, _unseen, total = item
        seen_fraction = 0.0 if total == 0 else (total - _unseen) / total
        return personal_score(session, user, story, seen_fraction=seen_fraction)

    remainder.sort(key=_score, reverse=True)
    for_you = remainder[: max(budget - len(important), 0)]

    sections = [
        {
            "label": "important_regardless",
            "stories": [
                _story_card(session, s, new_event_count=unseen)
                for s, unseen in important
            ],
        },
        {
            "label": "for_you",
            "stories": [
                _story_card(session, s, new_event_count=unseen)
                for s, unseen, _ in for_you
            ],
        },
    ]

    return {
        "generated_at": now.isoformat(),
        "days_away": days_away,
        "stories_moved": stories_moved,
        "stories_new": stories_new,
        "sections": sections,
    }
