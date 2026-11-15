# Milanko Backend

Backend for the **Milanko** public deliverable (NASA Space Challenge): a FastAPI
service and the ingestion jobs that keep the NASA POWER, EONET and GIBS data in
PostgreSQL.

This repository is being built from scratch for the public deliverable. The
current code is a **pipeline scaffold**: it exposes `/health` and `/ping`, runs
the CI/CD workflow and validates the deployment before the full backend is
migrated. The PostgreSQL data itself is already loaded in the three
environments.

## What is in the repository

| Path | Purpose |
|---|---|
| `backend/` | FastAPI application, requirements and database helpers |
| `src/` | Reserved for the shared NASA data client library |
| `tests/` | Unit tests |
| `ops/systemd/` | Ingestion runner and timers |
| `ops/vps/` | VPS bootstrap, nginx and API key helpers |
| `docs/` | Pipeline, infrastructure, data seed and API key runbooks |
| `Dockerfile` | Production image (Python 3.14, non-root) |

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.app:app --reload --port 8000
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
[`docs/api-keys.md`](docs/api-keys.md) for generation, rotation and the public
frontend caveat.

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

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
