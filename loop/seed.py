"""Seed the database from sources.yaml.

    python -m loop.seed --sources sources.yaml

Upserts sources by feed_url (idempotent) and ensures a dev user exists so the
quickstart's `brief --user 1` works out of the box.
"""

from __future__ import annotations

import argparse
import logging

import yaml
from sqlalchemy import select

from loop.db import session_scope
from loop.models import Source, User

logger = logging.getLogger(__name__)


def seed_sources(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    entries = data.get("sources", []) if isinstance(data, dict) else data
    upserted = 0
    with session_scope() as session:
        for entry in entries:
            existing = session.execute(
                select(Source).where(Source.feed_url == entry["feed_url"])
            ).scalar_one_or_none()
            if existing:
                existing.name = entry["name"]
                existing.homepage = entry.get("homepage")
                existing.country = entry.get("country")
                existing.lang = entry.get("lang")
                existing.authority_weight = float(entry.get("authority_weight", 0.0))
            else:
                session.add(
                    Source(
                        name=entry["name"],
                        feed_url=entry["feed_url"],
                        homepage=entry.get("homepage"),
                        country=entry.get("country"),
                        lang=entry.get("lang"),
                        authority_weight=float(entry.get("authority_weight", 0.0)),
                        active=True,
                    )
                )
            upserted += 1
    logger.info("Seeded %d source(s) from %s", upserted, path)
    return upserted


def ensure_dev_user(email: str = "dev@loop.local") -> int:
    with session_scope() as session:
        existing = session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if existing:
            return existing.id
        user = User(email=email, channels=["web"], brief_length=5)
        session.add(user)
        session.flush()
        logger.info("Created dev user id=%s (%s)", user.id, email)
        return user.id


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Seed Loop's database.")
    parser.add_argument("--sources", default="sources.yaml")
    parser.add_argument("--dev-user-email", default="dev@loop.local")
    args = parser.parse_args()

    seed_sources(args.sources)
    ensure_dev_user(args.dev_user_email)


if __name__ == "__main__":
    main()
