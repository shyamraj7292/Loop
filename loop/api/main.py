"""Loop FastAPI app: JSON API + the HTMX/Jinja web reader.

  * API routes live under /api (see loop/api/routes/*).
  * The web reader is served at / and /story/{id}.
  * Interactive API docs at /docs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from loop import __version__
from loop.api.deps import db
from loop.api.routes import account, brief, read, search, story, topics
from loop.delivery.brief import build_brief
from loop.models import Story, User

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

app = FastAPI(
    title="Loop",
    version=__version__,
    description="Everything you missed, in five minutes.",
)

for module in (brief, story, read, search, topics, account):
    app.include_router(module.router)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(
    request: Request,
    length: int = 5,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    session: Session = Depends(db),
) -> HTMLResponse:
    user = session.get(User, x_user_id)
    if user is None:
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"user_id": x_user_id},
            status_code=200,
        )
    payload = build_brief(session, user, length=length)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"brief": payload, "user": user, "length": length},
    )


@app.get("/story/{story_id}", response_class=HTMLResponse, include_in_schema=False)
def story_page(
    request: Request, story_id: int, session: Session = Depends(db)
) -> HTMLResponse:
    s = session.get(Story, story_id)
    if s is None:
        return templates.TemplateResponse(
            request, "not_found.html", {"story_id": story_id}, status_code=404
        )
    events = sorted(s.events, key=lambda e: e.occurred_at or e.id)

    # The original reporting behind the story, so the reader can open the full
    # article ("read the entire news"). Loop links out, never republishes.
    from sqlalchemy import select

    from loop.models import Article, Source, StoryArticle

    source_rows = session.execute(
        select(Article.url_canonical, Article.title, Source.name, Article.published_at)
        .join(StoryArticle, StoryArticle.article_id == Article.id)
        .join(Source, Source.id == Article.source_id)
        .where(StoryArticle.story_id == story_id)
        .order_by(Article.published_at.desc().nullslast())
    ).all()
    sources = [
        {
            "url": r[0],
            "title": r[1],
            "source": r[2],
            "published_at": r[3],
        }
        for r in source_rows
    ]
    return templates.TemplateResponse(
        request, "story.html", {"story": s, "events": events, "sources": sources}
    )
