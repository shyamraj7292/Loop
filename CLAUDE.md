# CLAUDE.md — working notes for Loop

Loop is a story-tracking news aggregator. Read `README.md` for the product
vision; this file is the map of the actual code (built as the v0.1 vertical
slice).

## Pipeline (the crank)

`Sources → Ingest → Cluster → Synthesise → Deliver`, orchestrated in
`loop/pipeline/run.py`:

- **Ingest** — `loop/workers/fetcher.py` (feedparser + ETag/If-Modified-Since),
  `loop/workers/extractor.py` (trafilatura + retention expiry),
  `loop/pipeline/embed.py::embed_pending` (bge-small, lazy-loaded).
- **Cluster** — `loop/pipeline/cluster.py`: online centroid matching over pgvector,
  dormancy sweep, HDBSCAN repair hook.
- **Synthesise** — `loop/pipeline/arc.py`: freshness + min-source gates, LLM call
  (`loop/llm/*`), grounding (`loop/pipeline/grounding.py`), one event per pass.
- **Rank** — `loop/pipeline/rank.py`: importance (squashed to 0..1) + personal score.
- **Deliver** — `loop/delivery/brief.py` (the read-state-aware delta),
  `render.py` (text), `telegram.py`/`email.py` (v0.2 stubs), web reader in
  `loop/api` + `loop/templates`.

## Key conventions

- Config is centralised in `loop/config.py` (`settings`). Never read `os.environ`
  elsewhere.
- All DB access goes through `loop/db.py` (`session_scope` for workers,
  `get_session` dependency for the API).
- The schema is created by a hand-written Alembic migration
  (`migrations/versions/0001_initial.py`) so the pgvector extension and HNSW
  indexes are set up exactly. Models in `loop/models.py` mirror it.
- LLM backends are swappable via `LLM_BACKEND` (`anthropic` | `gemini`). The
  pipeline only ever talks to the `LLMClient` protocol in `loop/llm/base.py`.
- Two-tier LLM: `LLM_MODEL_SMALL` (haiku, extraction) vs `LLM_MODEL_LARGE`
  (sonnet, arc synthesis), gated by `IMPORTANCE_THRESHOLD_LARGE_MODEL`.
- Security: article bodies are passed as delimited untrusted DATA; synthesis uses
  structured outputs and discards anything that doesn't parse; every claim must be
  grounded in a supporting article or it is dropped.

## Common commands

```bash
# Full stack
docker compose up -d db redis
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m loop.seed --sources sources.yaml
docker compose up -d

# Trigger a pipeline run
docker compose exec api python -m loop.cli run
docker compose exec api python -m loop.cli brief --user 1 --dry-run

# Dev checks
ruff check . && ruff format --check .
pytest
python -m evals.clustering --quick
```

## Status vs README roadmap

v0.1 core pipeline is implemented and runnable. Not yet done: Telegram/email
delivery, onboarding UI, full HDBSCAN repair, wire-service attribution collapse,
semantic (vs lexical) story search, and the Tier-1+ advanced features.
