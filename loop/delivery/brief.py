"""Brief assembly — the read-state-aware delta, grouped by category.

Open Loop after twelve days and it tells you "8 stories moved, 2 are new", then
shows only the developments that happened while you were gone (README > The
insight). The brief leads with a cross-category "Top Stories" rail (the
non-negotiable important_regardless section — README > Filter bubbles), then
splits the rest into named, collapsible category sections (World, Business,
Technology, Sports, ...).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from loop.models import (
    Article,
    Event,
    Source,
    Story,
    StoryArticle,
    User,
    UserReadState,
)
from loop.pipeline.rank import personal_score

# Reading-time budget -> (top-stories cap, per-category cap).
_LENGTH_BUDGET = {2: (3, 4), 5: (5, 8), 15: (8, 20)}

# A story is "top" (shown to everyone, cross-category) above this importance,
# or simply by being among the most important when few clear the bar.
_TOP_THRESHOLD = 0.55

# Display order + titles for category sections. Categories come from the
# source registry (sources.yaml); anything unmapped falls into "general".
_CATEGORY_ORDER = [
    "world",
    "india",
    "business",
    "technology",
    "science",
    "sports",
    "health",
    "entertainment",
    "general",
]
_CATEGORY_TITLES = {
    "world": "World",
    "india": "India",
    "business": "Business",
    "technology": "Technology",
    "science": "Science",
    "sports": "Sports",
    "health": "Health",
    "entertainment": "Entertainment",
    "general": "More",
}


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


def _story_category(session: Session, story_id: int) -> str:
    """Majority category among the story's articles' sources."""
    rows = session.execute(
        select(Source.category, func.count().label("n"))
        .join(Article, Article.source_id == Source.id)
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .where(StoryArticle.story_id == story_id, Source.category.is_not(None))
        .group_by(Source.category)
        .order_by(func.count().desc())
    ).all()
    return rows[0][0] if rows else "general"


def _story_card(
    session: Session, story: Story, *, new_event_count: int, category: str
) -> dict:
    return {
        "id": story.id,
        "title": story.title,
        "slug": story.slug,
        "state_summary": story.state_summary,
        "new_event_count": new_event_count,
        "distinct_sources": _distinct_sources(session, story.id),
        "importance": round(story.importance, 3),
        "category": category,
        "category_title": _CATEGORY_TITLES.get(category, category.title()),
        "last_activity": story.last_activity.isoformat()
        if story.last_activity
        else None,
    }


def build_brief(session: Session, user: User, *, length: int = 5) -> dict:
    """Assemble the brief payload: delta metadata + Top + category sections."""
    now = _utcnow()
    last_seen = _last_seen_at(session, user.id)
    days_away = (now - last_seen).days if last_seen else 0

    seen_ids = _seen_event_ids(session, user.id)
    top_cap, cat_cap = _LENGTH_BUDGET.get(length, (5, 8))

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
    cards: list[dict] = []  # story cards with unseen events

    for story in stories:
        event_rows = session.execute(
            select(Event.id).where(Event.story_id == story.id)
        ).scalars().all()
        total = len(event_rows)
        unseen = sum(1 for eid in event_rows if eid not in seen_ids)
        if unseen == 0:
            continue

        category = _story_category(session, story.id)
        card = _story_card(
            session, story, new_event_count=unseen, category=category
        )
        card["_importance_raw"] = story.importance
        cards.append(card)

        if last_seen is not None and story.first_seen > last_seen:
            stories_new += 1
        elif unseen == total:
            stories_new += 1
        else:
            stories_moved += 1

    # --- Top Stories: cross-category highlights (never disabled) ---
    by_importance = sorted(cards, key=lambda c: c["_importance_raw"], reverse=True)
    top = by_importance[:top_cap]

    sections = [
        {
            "label": "top",
            "title": "Top Stories",
            "collapsible": False,
            "open": True,
            "stories": top,
        }
    ]

    # --- Category sections (collapsible) ---
    by_category: dict[str, list[dict]] = {}
    for card in cards:
        by_category.setdefault(card["category"], []).append(card)

    for cat in _CATEGORY_ORDER:
        items = by_category.get(cat)
        if not items:
            continue
        items = sorted(items, key=lambda c: c["_importance_raw"], reverse=True)
        sections.append(
            {
                "label": cat,
                "title": _CATEGORY_TITLES.get(cat, cat.title()),
                "collapsible": True,
                "open": False,
                "stories": items[:cat_cap],
            }
        )

    # Any categories not in the fixed order (defensive).
    for cat, items in by_category.items():
        if cat not in _CATEGORY_ORDER:
            sections.append(
                {
                    "label": cat,
                    "title": cat.title(),
                    "collapsible": True,
                    "open": False,
                    "stories": sorted(
                        items, key=lambda c: c["_importance_raw"], reverse=True
                    )[:cat_cap],
                }
            )

    # Strip internal sort key from the payload.
    for section in sections:
        for card in section["stories"]:
            card.pop("_importance_raw", None)

    return {
        "generated_at": now.isoformat(),
        "days_away": days_away,
        "stories_moved": stories_moved,
        "stories_new": stories_new,
        "total_stories": len(cards),
        "sections": sections,
    }
