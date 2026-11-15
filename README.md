# Milanko Backend

Backend for the **Milanko** public deliverable (NASA Space Challenge): a FastAPI
service, the NASA ingestion workers and the shared data core.

## Repository layout

```text
milanko-backend/
├── api/                 # FastAPI routes, schemas and read services
├── processor/           # NASA POWER/EONET/GIBS ingestion workers and event-region jobs
├── core/                # SQLAlchemy models, Alembic migrations, NASA clients, world base
├── data/catalog/        # Master variable catalog
├── ops/                 # systemd timers and VPS/nginx helpers
├── tests/               # Unit and API tests
└── docs/                # Pipeline, infrastructure, data seed, API keys and architecture
```

The three Python packages have strict boundaries:

- `api/` may import `core/`, never `processor/`.
- `processor/` may import `core/`, never `api/`.
- `core/` imports neither `api/` nor `processor/`.

The API runs in its own container. The ingestion workers run as one-off
containers from the same image through `systemd` timers. See
[`docs/architecture.md`](docs/architecture.md).

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api.app:app --reload --port 8000
```

Open <http://127.0.0.1:8000/docs>.

## API key

The public edge validates the `X-API-Key` header for every data endpoint. The
following routes are public:

- `/api/v1/health`
- `/api/v1/docs`
- `/api/v1/redoc`
- `/api/v1/openapi.json`

The key is enforced by nginx, not by FastAPI. See
[`docs/api-keys.md`](docs/api-keys.md).

## Environments

| Environment | Branch | URL | Database |
|---|---|---|---|
| develop | `develop` | `https://dev-milanko.hexalis.org` | `milanko_develop` |
| qa | `qa` | `https://qa-milanko.hexalis.org` | `milanko_qa` |
| production | `main` | `https://milanko.hexalis.org` | `milanko_production` |

Promotion is `develop` → `qa` → `main` by fast-forward. Production deploys after
approval of the `production` GitHub Environment.

## Pipelines

The CI/CD workflow is **self-contained** in this repository
(`.github/workflows/pipeline.yml`); it does not call `hexalis/github-workflows`.
This is the only exception to the organization's centralized workflow policy
because the public deliverable must include everything except the design system.

See [`docs/pipelines.md`](docs/pipelines.md) for the workflow, required GitHub
Environment variables/secrets and rollback.

## Ingestion

The systemd runner and the nine timers live in `ops/systemd/`. They run the same
image as the API and call `python -m processor.ingest_power`,
`processor.ingest_eonet` and `processor.ingest_gibs`.

```bash
sudo ops/systemd/install-all.sh
```

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
