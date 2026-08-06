"""In-process scheduler.

Runs the full pipeline on a cadence. APScheduler in-process is a legitimate
substitute for Celery up to a few thousand users (README > Architecture); swap
for `celery -A loop.workers.celery_app worker` when you outgrow it.

    python -m loop.workers.schedule
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from loop.config import settings
from loop.pipeline.run import run_full

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    interval = settings.fetch_interval_minutes
    logger.info("Starting Loop scheduler (every %d min)", interval)

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_full,
        "interval",
        minutes=interval,
        id="pipeline",
        max_instances=1,
        coalesce=True,
        next_run_time=None,  # first run happens immediately below
    )

    # Kick off one run at startup so the reader has data without waiting.
    try:
        run_full()
    except Exception:
        logger.exception("Initial pipeline run failed; scheduler will retry")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
