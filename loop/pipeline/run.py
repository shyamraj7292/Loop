"""Pipeline orchestration.

Thin wrappers that sequence the stages in the right order and own their own
transaction. Both the CLI (`loop.cli`) and the scheduler
(`loop.workers.schedule`) call these so the ordering lives in exactly one place.

    Sources -> Ingest -> Cluster -> Synthesise -> Deliver
"""

from __future__ import annotations

import logging

from loop.db import session_scope
from loop.pipeline import cluster as cluster_mod
from loop.pipeline import embed as embed_mod
from loop.pipeline import rank as rank_mod
from loop.pipeline.arc import synthesize_stories
from loop.workers.extractor import expire_bodies, extract_pending
from loop.workers.fetcher import fetch_all

logger = logging.getLogger(__name__)


def run_ingest() -> dict[str, int]:
    """Fetch feeds, extract bodies, embed. Returns per-stage counts."""
    with session_scope() as session:
        fetched = fetch_all(session)
    with session_scope() as session:
        extracted = extract_pending(session)
    with session_scope() as session:
        embedded = embed_mod.embed_pending(session)
    return {"fetched": fetched, "extracted": extracted, "embedded": embedded}


def run_cluster() -> dict[str, int]:
    with session_scope() as session:
        clustered = cluster_mod.cluster_new_articles(session)
    with session_scope() as session:
        dormant = cluster_mod.mark_dormant(session)
    return {"clustered": clustered, "dormant": dormant}


def run_synthesise() -> dict[str, int]:
    with session_scope() as session:
        events = synthesize_stories(session)
    with session_scope() as session:
        ranked = rank_mod.rank_stories(session)
    return {"events": events, "ranked": ranked}


def run_maintenance() -> dict[str, int]:
    with session_scope() as session:
        expired = expire_bodies(session)
    return {"expired_bodies": expired}


def run_full() -> dict[str, dict[str, int]]:
    """One full turn of the crank: ingest -> cluster -> synthesise -> maintain."""
    logger.info("=== pipeline run: start ===")
    result = {
        "ingest": run_ingest(),
        "cluster": run_cluster(),
        "synthesise": run_synthesise(),
        "maintenance": run_maintenance(),
    }
    logger.info("=== pipeline run: done %s ===", result)
    return result
