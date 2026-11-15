# Architecture

## Three packages, one data core

```text
                 ┌──────────────────────┐
                 │        core/         │
                 │ models, Alembic,     │
                 │ NASA clients, grid,  │
                 │ world base, catalog  │
                 └──────────┬───────────┘
                            │
             ┌──────────────┴──────────────┐
             │                             │
      ┌──────▼──────┐               ┌──────▼──────┐
      │    api/     │               │ processor/  │
      │ FastAPI     │               │ ingest_*    │
      │ read paths  │               │ workers     │
      └─────────────┘               └─────────────┘
```

| Package | Responsibility | May import |
|---|---|---|
| `api/` | HTTP routes, Pydantic schemas, read-only region/world/event services | `core/` |
| `processor/` | POWER, EONET and GIBS ingestion, event-region assignment, backfills | `core/` |
| `core/` | SQLAlchemy models, Alembic migrations, NASA clients, hex grid, world base, catalog | standard library and its own subpackages |

### Import rules

- `api/` **must not** import `processor/`.
- `processor/` **must not** import `api/`.
- `core/` **must not** import `api/` or `processor/`.

`tests/test_boundaries.py` enforces these rules with `ast` parsing.

## Why one repository

The API and the workers share the database schema, the Alembic history, the
catalog and the NASA clients. A single repository keeps schema changes, workers
and API reads in the same commit. Splitting them into separate repositories
would duplicate `core/models.py` and `core/nasa_events/`, or require a shared
Python package, which adds release coordination to a hackathon deliverable.

The separation is therefore **by package and by process**, not by repository:

- `milanko-api-<env>` runs `uvicorn api.app:app`.
- `systemd` timers run one-off containers with `python -m processor.ingest_*`.

Neither process imports the other's code.

## Shared assets

- `core/static/world/` — ETDW world base (12 MB) used by the globe and by the
  POWER processor for region elevation.
- `data/catalog/` — master variable catalog and core selection used by the API
  and the ingestion seed.
- `core/migrations/` — Alembic history. The production databases are already at
  `c3d4e5f6a7b8`; do not reinitialize the history.

## Runtime processes

```text
nginx
  └── /api/v1/ ──► milanko-api-<env> (uvicorn api.app:app)
                         │
                         ▼
                  milanko-postgres

systemd timer
  └── docker run --rm milanko-api:<env> python -m processor.ingest_* 
                         │
                         ▼
                  milanko-postgres
```

The API containers publish only on `127.0.0.1`; PostgreSQL is only reachable on
the `milanko` Docker network. See [`server-processes.md`](server-processes.md)
for the server configuration and operational runbook.
