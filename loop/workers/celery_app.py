"""Celery app (optional, for scaling beyond the in-process scheduler).

The v0.1 slice runs on APScheduler (loop.workers.schedule). This module wires up
Celery + Redis with a beat schedule for when you want distributed workers:

    celery -A loop.workers.celery_app worker --loglevel=info
    celery -A loop.workers.celery_app beat --loglevel=info
"""

from __future__ import annotations

from celery import Celery

from loop.config import settings

celery_app = Celery("loop", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.beat_schedule = {
    "pipeline-run": {
        "task": "loop.pipeline.run_full",
        "schedule": settings.fetch_interval_minutes * 60.0,
    }
}
celery_app.conf.timezone = "UTC"


@celery_app.task(name="loop.pipeline.run_full")
def run_full_task() -> dict:
    from loop.pipeline.run import run_full

    return run_full()
