# Pipelines

The CI/CD pipeline lives in [`.github/workflows/pipeline.yml`](../.github/workflows/pipeline.yml).
It is intentionally **self-contained**: the public deliverable must include its
pipelines, so this repository does not call `hexalis/github-workflows`.

## Branch model

| Environment | Branch | URL | Container | Port | Database |
|---|---|---|---|---|---|
| develop | `develop` | `https://dev-milanko.hexalis.org` | `milanko-api-develop` | `127.0.0.1:8011` | `milanko_develop` |
| qa | `qa` | `https://qa-milanko.hexalis.org` | `milanko-api-qa` | `127.0.0.1:8012` | `milanko_qa` |
| production | `main` | `https://milanko.hexalis.org` | `milanko-api-production` | `127.0.0.1:8013` | `milanko_production` |

Promotion is `develop` → `qa` → `main` by fast-forward. Pull requests run the
test job only. Pushes to the three long-lived branches run tests, build the
image on the server and deploy.

## Jobs

1. **Tests and image build** (`test`)
   - Python 3.14, `pip install -r backend/requirements.txt`.
   - `python -m compileall -q backend`.
   - `python -m unittest discover -s tests -v`.
   - `docker build -t milanko-api:ci .` to validate the Dockerfile.

2. **Deploy** (`deploy`)
   - Runs only for `push`/`workflow_dispatch` on `develop`, `qa` or `main`.
   - Maps the branch to the GitHub Environment: `main` → `production`.
   - Validates `DEPLOY_SSH_KEY` and `DEPLOY_KNOWN_HOSTS`; there is no
     `ssh-keyscan` fallback.
   - On the server: clones the public repository if needed, fetches, resets to
     `origin/<branch>`, builds tags `<image>:<env>` and `<image>:<env>-<sha>`.
   - Runs Alembic only when `backend/alembic.ini` exists.
   - Recreates the container, waits for `DEPLOY_HEALTH_URL` and prunes dangling
     images.
   - Runs a public smoke test: `/api/v1/health` without a key and
     `/api/v1/ping` with `SMOKE_API_KEY` (200) and without it (401).

3. **API smoke test**
   - Skipped if `PUBLIC_BASE_URL` or `SMOKE_API_KEY` is not configured.

## Required GitHub Environment configuration

Create the environments `develop`, `qa` and `production`. Restrict each
environment to its branch and require reviewers for `production`.

### Secrets

| Secret | Description |
|---|---|
| `DEPLOY_SSH_KEY` | Private key authorized for the `deploy` user on the VPS |
| `DEPLOY_KNOWN_HOSTS` | Pinned `known_hosts` line for the VPS |
| `SMOKE_API_KEY` | `internal-smoke` API key for the environment |

### Variables

| Variable | develop | qa | production |
|---|---|---|---|
| `DEPLOY_HOST` | VPS IP / host | VPS IP / host | VPS IP / host |
| `DEPLOY_USER` | `deploy` | `deploy` | `deploy` |
| `DEPLOY_SSH_PORT` | `22` | `22` | `22` |
| `DEPLOY_REMOTE_PATH` | `/home/deploy/milanko-backend-develop` | `/home/deploy/milanko-backend-qa` | `/home/deploy/milanko-backend-production` |
| `DEPLOY_CONTAINER` | `milanko-api-develop` | `milanko-api-qa` | `milanko-api-production` |
| `DEPLOY_IMAGE_TAG` | `milanko-api:develop` | `milanko-api:qa` | `milanko-api:production` |
| `DEPLOY_PORTS` | `127.0.0.1:8011:8000` | `127.0.0.1:8012:8000` | `127.0.0.1:8013:8000` |
| `DEPLOY_ENV_FILE` | `/etc/milanko/backend-develop.env` | `/etc/milanko/backend-qa.env` | `/etc/milanko/backend-production.env` |
| `DEPLOY_HEALTH_URL` | `http://127.0.0.1:8011/health` | `http://127.0.0.1:8012/health` | `http://127.0.0.1:8013/health` |
| `DEPLOY_EXTRA_RUN_ARGS` | `-v /srv/milanko/cache/develop:/app/data/cache` | `-v /srv/milanko/cache/qa:/app/data/cache` | `-v /srv/milanko/cache/production:/app/data/cache` |
| `DEPLOY_DOCKER_NETWORK` | `milanko` | `milanko` | `milanko` |
| `DEPLOY_USE_SUDO` | `false` | `false` | `false` |
| `PUBLIC_BASE_URL` | `https://dev-milanko.hexalis.org` | `https://qa-milanko.hexalis.org` | `https://milanko.hexalis.org` |

Optional: `DEPLOY_DOCKERFILE`, `DEPLOY_CONTEXT`, `DEPLOY_MIGRATE_COMMAND`,
`DEPLOY_HEALTH_TIMEOUT_SECONDS`.

## Manual deploy

```bash
gh workflow run pipeline.yml --repo hexalis/milanko-backend --ref develop
gh workflow run pipeline.yml --repo hexalis/milanko-backend --ref qa
gh workflow run pipeline.yml --repo hexalis/milanko-backend --ref main
```

## Rollback

Every deploy leaves an image tagged with the short commit SHA:

```bash
ssh deploy@<vps>
sudo docker images 'milanko-api:<env>-*'
sudo docker stop milanko-api-<env>
sudo docker rm milanko-api-<env>
sudo docker run -d --name milanko-api-<env> --restart unless-stopped \
  --network milanko -p 127.0.0.1:<port>:8000 \
  --env-file /etc/milanko/backend-<env>.env \
  -v /srv/milanko/cache/<env>:/app/data/cache \
  milanko-api:<env>-<sha>
```

Alternatively, revert the commit on the branch and let the pipeline deploy it.

## Frontend

`milanko-frontend` will have its own self-contained pipeline when its code
lands. This repository does not deploy the frontend.
