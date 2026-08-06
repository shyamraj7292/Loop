"""Loop command-line interface.

    python -m loop.cli ingest --once
    python -m loop.cli cluster --once
    python -m loop.cli synthesise --once
    python -m loop.cli brief --user 1 --dry-run
    python -m loop.cli run          # one full pipeline turn

Trigger the first pipeline run without waiting for the scheduler.
"""

from __future__ import annotations

import logging

import typer

from loop.config import settings

app = typer.Typer(add_completion=False, help="Loop pipeline CLI.")


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


@app.callback()
def _main() -> None:
    _setup_logging()


@app.command()
def ingest(once: bool = typer.Option(True, help="Run a single pass.")) -> None:
    """Fetch feeds, extract bodies, embed articles."""
    from loop.pipeline.run import run_ingest

    result = run_ingest()
    typer.echo(f"ingest: {result}")


@app.command()
def cluster(once: bool = typer.Option(True, help="Run a single pass.")) -> None:
    """Assign new articles to stories (online clustering)."""
    from loop.pipeline.run import run_cluster

    result = run_cluster()
    typer.echo(f"cluster: {result}")


@app.command()
def synthesise(once: bool = typer.Option(True, help="Run a single pass.")) -> None:
    """Synthesise arc events for stories with new articles, then rank."""
    from loop.pipeline.run import run_synthesise

    result = run_synthesise()
    typer.echo(f"synthesise: {result}")


@app.command()
def run() -> None:
    """Run one full pipeline turn: ingest -> cluster -> synthesise -> maintain."""
    from loop.pipeline.run import run_full

    result = run_full()
    typer.echo(f"run: {result}")


@app.command()
def brief(
    user: int = typer.Option(..., help="User id."),
    length: int = typer.Option(5, help="Reading-time budget in minutes (2/5/15)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print, don't deliver."),
) -> None:
    """Generate a user's brief."""
    from loop.db import session_scope
    from loop.delivery.brief import build_brief
    from loop.delivery.render import render_brief_text
    from loop.models import User

    with session_scope() as session:
        u = session.get(User, user)
        if u is None:
            typer.echo(f"No user with id={user}. Run `python -m loop.seed` first.")
            raise typer.Exit(code=1)
        payload = build_brief(session, u, length=length)

    typer.echo(render_brief_text(payload))
    if not dry_run:
        typer.echo(
            "\n[delivery channels are v0.2; use --dry-run or the web reader at "
            "http://localhost:8000]"
        )


if __name__ == "__main__":
    app()
