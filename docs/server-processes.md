# Server processes

This runbook describes how the VPS is configured so the API containers, the
PostgreSQL container and the NASA ingestion workers run reliably. It uses
placeholders for the server address and credentials: the real host is stored as
a GitHub Environment secret, not in this repository.

Related documents:

- [`infrastructure.md`](infrastructure.md) — host, PostgreSQL, nginx and TLS.
- [`pipelines.md`](pipelines.md) — CI/CD, GitHub Environments and rollback.
- [`data-seed.md`](data-seed.md) — dump, restore and materialized views.
- [`api-keys.md`](api-keys.md) — `X-API-Key` generation and rotation.
- [`../ops/systemd/README.md`](../ops/systemd/README.md) — timer commands.

## 1. Topology

```text
Cloudflare (proxy + TLS)
        │
        ▼
nginx :443
  ├── /                 → static placeholder (today) / frontend container (target)
  └── /api/v1/          → 127.0.0.1:8011 | 8012 | 8013
                              │
                              ▼
                     milanko-api-<env>  (uvicorn api.app:app)
                              │
                              ▼
                     milanko-postgres  (postgres:17-alpine)

systemd timer
  └── /usr/local/bin/milanko-ingest <job>-<env>
          └── docker run --rm milanko-api:<env> \
                python -m processor.ingest_<job>
                              │
                              ▼
                     milanko-postgres
```

The API and the workers use the same image and the same `milanko` Docker
network. The API is a long-running container; each worker is a one-off
container started by a systemd timer.

## 2. Host baseline

| Item | Value |
|---|---|
| OS | Ubuntu 26.04 LTS |
| CPU / RAM | 2 vCPU / 3.8 GiB |
| Swap | 4 GiB `/swapfile`, `vm.swappiness=10` |
| Disk | 96 GB |
| Timezone | UTC (`Etc/UTC`); timers use `UTC` explicitly |
| Docker | `docker-ce` 29.x, `json-file` logs, systemd cgroup driver |
| Docker network | `milanko` (`172.18.0.0/16`) |
| Firewall | UFW active: 22, 80 and 443 only |
| Edge | nginx + Let's Encrypt + Cloudflare proxy |

The bootstrap script installs Docker, nginx, Certbot, the PostgreSQL client,
`jq` and `ufw`, creates the swap file and the `deploy` user, and creates the
directory layout:

```bash
sudo ops/vps/bootstrap.sh
```

Do not expose PostgreSQL. The container has no published port and is only
reachable through the `milanko` network.

## 3. Filesystem and permissions

```text
/srv/milanko/
├── cache/
│   ├── develop/        # API + worker cache, owned by UID 10001
│   ├── qa/
│   └── production/
├── dumps/              # compressed pg_dump files, owned by deploy
├── frontend/
│   ├── develop/        # static placeholder / static export output
│   ├── qa/
│   └── production/
└── postgres/           # (reserved; PostgreSQL uses a named volume)

/etc/milanko/
├── postgres.env                 # POSTGRES_PASSWORD, 0600
├── backend-<env>.env            # DATABASE_URL + NASA keys, root:deploy 0640
├── frontend-<env>.env           # MILANKO_API_URL, APP_ENV, MILANKO_API_KEY, 0640
└── api-keys-<env>.tsv           # public-web + internal-smoke, 0600

/etc/nginx/
├── sites-available/milanko
├── conf.d/milanko-api.conf
└── snippets/
    ├── milanko-api-keys-<env>.conf   # generated, 0600
    ├── milanko-api-proxy.conf
    ├── milanko-api-errors.conf
    └── cloudflare-realip.conf
```

`deploy` is the CI/CD user. It owns `/srv/milanko`, belongs to the `docker`
group and can read the `backend-*.env` / `frontend-*.env` files. Remember that
membership in the `docker` group is root-equivalent on the host; protect the
`deploy` SSH keys accordingly.

## 4. Docker network

Create it once:

```bash
docker network create milanko
```

Containers attached:

| Container | Role | Address |
|---|---|---|
| `milanko-postgres` | PostgreSQL 17 | internal |
| `milanko-api-develop` | API develop | internal + `127.0.0.1:8011` |
| `milanko-api-qa` | API QA | internal + `127.0.0.1:8012` |
| `milanko-api-production` | API production | internal + `127.0.0.1:8013` |
| `milanko-ingest-<env>-<job>` | one-off worker | internal, `--rm` |
| `milanko-web-<env>` | future Next.js server | internal + `127.0.0.1:8021–8023` |

The API and PostgreSQL are not published on a public interface. The frontend
server will be reachable only from nginx.

## 5. PostgreSQL

```bash
docker run -d \
  --name milanko-postgres \
  --restart unless-stopped \
  --network milanko \
  --env-file /etc/milanko/postgres.env \
  --volume milanko-postgres-data:/var/lib/postgresql/data \
  --shm-size=512m \
  --memory=1536m \
  --log-opt max-size=50m \
  --log-opt max-file=3 \
  postgres:17-alpine \
  postgres \
    -c shared_buffers=512MB \
    -c work_mem=16MB \
    -c maintenance_work_mem=256MB \
    -c max_connections=50 \
    -c effective_cache_size=1536MB \
    -c max_wal_size=2GB \
    -c min_wal_size=512MB
```

- Data lives in the named volume `milanko-postgres-data`.
- `--shm-size=512m` is required for parallel queries and large restores.
- `max_connections=50` is enough for three APIs (`core/db.py` uses
  `pool_size=5`, `max_overflow=5`) plus one-off workers.
- The application roles own their databases. Restores must use
  `pg_restore --no-owner --no-privileges --role=milanko_<env>_app`; see
  [`data-seed.md`](data-seed.md).
- Materialized views `variable_coverage` and `region_monthly` are refreshed by
  the POWER and GIBS workers after a successful run.

Check:

```bash
docker exec milanko-postgres pg_isready -U postgres
docker exec milanko-postgres psql -U postgres -Atc \
  "select datname, pg_size_pretty(pg_database_size(datname)) from pg_database where datname like 'milanko%';"
```

## 6. API containers

The deploy pipeline builds `milanko-api:<env>` on the VPS and starts:

```bash
docker run -d \
  --name milanko-api-<env> \
  --restart unless-stopped \
  --network milanko \
  -p 127.0.0.1:<8011|8012|8013>:8000 \
  --env-file /etc/milanko/backend-<env>.env \
  --volume /srv/milanko/cache/<env>:/app/data/cache \
  --log-opt max-size=50m \
  --log-opt max-file=3 \
  milanko-api:<env>
```

- `DATABASE_URL` points to `milanko-postgres:5432/milanko_<env>`.
- `NASA_API_KEY`, `FIRMS_MAP_KEY` and `EARTHDATA_TOKEN` are in the same env
  file.
- The cache volume is shared with the workers. It is best-effort; deleting it
  never deletes PostgreSQL data.
- The image healthcheck calls `/health`; the deploy pipeline also waits for the
  same URL and runs the `X-API-Key` smoke test.
- The API response for `/regions/{code}/anomalies` can be large (tens of MB);
  keep the nginx `proxy_read_timeout` at 180s.

Current observed usage: ~75 MB per API container. The containers have no hard
memory cap today. If the host starts other workloads, append
`--memory=512m` to `DEPLOY_EXTRA_RUN_ARGS` for each environment so an API leak
cannot take PostgreSQL down.

## 7. Ingestion workers

### 7.1 Unit model

A single templated service and nine timers:

```text
/etc/systemd/system/milanko-ingest@.service
/etc/systemd/system/milanko-ingest-power.timer
/etc/systemd/system/milanko-ingest-eonet.timer
/etc/systemd/system/milanko-ingest-gibs.timer
/etc/systemd/system/milanko-ingest-qa-*.timer
/etc/systemd/system/milanko-ingest-production-*.timer
/usr/local/bin/milanko-ingest
```

The service is `Type=oneshot`. The instance encodes the job and the
environment:

| Instance | Job | Environment |
|---|---|---|
| `power` | POWER | develop |
| `power-qa` | POWER | qa |
| `power-production` | POWER | production |
| `eonet`, `eonet-qa`, `eonet-production` | EONET | develop / qa / production |
| `gibs`, `gibs-qa`, `gibs-production` | GIBS | develop / qa / production |

`MILANKO_ENV=develop` is the default for the unsuffixed instances.

### 7.2 Schedule (UTC)

| Environment | POWER | EONET | GIBS |
|---|---|---|---|
| develop | 03:15 | 04:15 | 05:30 |
| qa | 06:15 | 07:15 | 08:30 |
| production | 09:15 | 10:15 | 11:30 |

Each timer uses `RandomizedDelaySec=15m`, `Persistent=true` (a missed run is
executed after boot) and `OnCalendar ... UTC`. The environments are staggered
by three hours so two ingestion jobs do not compete for CPU and PostgreSQL
I/O.

### 7.3 Runner

`ops/systemd/milanko-ingest.sh`:

1. Parses `<job>[-<env>]`; default env is `develop`.
2. Maps the env to the image and cache path (`milanko-api:<env>`,
   `/srv/milanko/cache/<env>`).
3. Reads `/etc/milanko/backend-<env>.env`.
4. Creates the cache directory with UID/GID `10001`.
5. Takes an exclusive `flock` on
   `/run/milanko-ingest-<env>-<job>.lock`; an overlapping run exits cleanly.
6. Runs:

```bash
python -m processor.ingest_power --days 14
python -m processor.ingest_eonet --since <45 days ago>
python -m processor.ingest_gibs run --days 10 --workers 2
```

7. Runs the container with `--rm`, `--network milanko`, the env file, the cache
   volume and `--no-healthcheck`; Docker log rotation is `50m × 3`.

Environment overrides:

| Variable | Default | Purpose |
|---|---|---|
| `POWER_DAYS` | `14` | POWER incremental window |
| `EONET_DAYS` | `45` | EONET lookback days |
| `GIBS_DAYS` | `10` | GIBS incremental window |
| `GIBS_WORKERS` | `2` | GIBS extraction concurrency |

Keep `GIBS_WORKERS=2` on this 2-vCPU host. A full historical backfill is a
manual operation with a longer timeout, not something the daily timer should
absorb.

### 7.4 Install and update

```bash
sudo ops/systemd/install-all.sh
systemctl list-timers 'milanko-ingest-*' --all --no-pager
```

After changing `ops/systemd/milanko-ingest.sh` or the unit files, re-run
`install-all.sh` on the VPS: the timers call the copy at
`/usr/local/bin/milanko-ingest`.

Manual run:

```bash
sudo /usr/local/bin/milanko-ingest power-develop
sudo /usr/local/bin/milanko-ingest eonet-qa
sudo /usr/local/bin/milanko-ingest gibs-production
```

Inspect logs:

```bash
journalctl -u 'milanko-ingest@power.service' -n 100 --no-pager
journalctl -u 'milanko-ingest@*' --since '24 hours ago' --no-pager
```

### 7.5 Concurrency and safety

- The `flock` lock is per environment/job. A long POWER run does not block the
  EONET or GIBS timer.
- `Persistent=true` replays a missed timer after boot; the lock prevents
  duplicate overlapping runs.
- The worker is a one-off container with `--rm`; if the Docker CLI is killed,
  check for a leftover `milanko-ingest-*` container and remove it before
  retrying.
- `TimeoutStartSec=6h` covers the daily increments. A manual backfill that can
  exceed six hours should be run outside systemd or with a temporary override.
- Ingest jobs write `ingest_runs` and `ingest_checkpoints`; a failed run is
  recorded with its error. Use those tables to decide whether a retry is safe.

## 8. Environment files

| File | Mode | Contents |
|---|---|---|
| `/etc/milanko/postgres.env` | `0600 root:root` | `POSTGRES_PASSWORD` |
| `/etc/milanko/backend-<env>.env` | `0640 root:deploy` | `DATABASE_URL`, `NASA_API_KEY`, `FIRMS_MAP_KEY`, `EARTHDATA_TOKEN` |
| `/etc/milanko/frontend-<env>.env` | `0640 root:deploy` | `MILANKO_API_URL`, `APP_ENV`, `MILANKO_API_KEY` |
| `/etc/milanko/api-keys-<env>.tsv` | `0600 root:root` | `public-web`, `internal-smoke` |

Never commit these files. The server host is a GitHub Environment secret
(`DEPLOY_HOST`) in both the backend and frontend environments; the workflows
accept `secrets.DEPLOY_HOST || vars.DEPLOY_HOST`.

## 9. Nginx and TLS

- `sites-available/milanko` has one HTTPS server block per environment and a
  catch-all `return 444`.
- `/api/v1/` and `/api/` proxy to the API port of that environment; the API key
  is validated before proxying.
- Public exceptions: `/api/v1/health`, `/docs`, `/redoc`,
  `/openapi.json`, and `OPTIONS` (CORS preflight).
- Rate limits: 20 r/s per real client IP, 10 r/s per API key; burst 40/20;
  20 concurrent connections per IP.
- Cloudflare real IP ranges are loaded from
  `/etc/nginx/snippets/cloudflare-realip.conf`.
- TLS is Let's Encrypt with the HTTP-01 webroot challenge; Cloudflare forwards
  `/.well-known/acme-challenge/` to the origin. Renewal is automatic.
- The static placeholder lives in `/srv/milanko/frontend/<env>/index.html`.
  When the Next.js frontend is ready, nginx root should proxy to the
  `milanko-web-<env>` container instead of serving the placeholder.

Useful checks:

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run --no-random-sleep-on-renew
curl -fsS https://dev-milanko.hexalis.org/api/v1/health
```

## 10. Monitoring

### Containers and host

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker stats --no-stream
free -h
swapon --show
df -h /
sudo systemctl list-timers 'milanko-ingest-*' --all --no-pager
```

### API

```bash
curl -fsS https://dev-milanko.hexalis.org/api/v1/health
curl -fsS https://qa-milanko.hexalis.org/api/v1/health
curl -fsS https://milanko.hexalis.org/api/v1/health
```

`/health` returns `database: ok` and `core_variables: 80` when the API can reach
PostgreSQL.

### Ingestion

```sql
SELECT job, started_at, finished_at, status, rows_read, rows_written, error
FROM ingest_runs
ORDER BY started_at DESC
LIMIT 20;

SELECT * FROM ingest_checkpoints ORDER BY updated_at DESC LIMIT 20;
```

```bash
journalctl -u 'milanko-ingest@*' --since '24 hours ago' --no-pager
```

### PostgreSQL

```sql
SELECT datname, pg_size_pretty(pg_database_size(datname))
FROM pg_database WHERE datname LIKE 'milanko%';

SELECT pid, state, wait_event_type, left(query, 80)
FROM pg_stat_activity
WHERE datname LIKE 'milanko%';

SELECT relname, last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
WHERE relname IN ('observations', 'events', 'event_regions');
```

Suggested alerts:

- Any `ingest_runs.status = 'failed'`.
- API `/health` non-200 or `database != ok`.
- Disk above 80%.
- PostgreSQL down or connection count near 50.
- Timer missed and `Persistent=true` not replayed after boot.
- `docker stats` memory near the configured caps.

## 11. Failure recovery

### Timer or worker failed

1. `journalctl -u 'milanko-ingest@<instance>.service' -n 200 --no-pager`.
2. Check `ingest_runs` for the error and `rows_written`.
3. Check for a leftover container:
   `docker ps -a --filter name=milanko-ingest-`.
4. If the name is taken but the container is dead:
   `docker rm -f milanko-ingest-<env>-<job>`.
5. Check disk and memory (`df -h`, `free -h`, `docker stats`).
6. Re-run manually: `sudo /usr/local/bin/milanko-ingest <job>-<env>`.
7. If the failure is an upstream NASA error, retry after the API recovers; the
   jobs are idempotent (`upsert` + checkpoints).

### OOM or container exit 137

```bash
dmesg -T | tail -50
docker inspect <container> --format '{{.State.ExitCode}} {{.State.OOMKilled}}'
```

Reduce `GIBS_WORKERS`, add a memory cap to the worker, or run the job outside
the time window of another heavy job. The host has 4 GB swap, but swap is not a
substitute for a memory cap.

### PostgreSQL is down

```bash
docker start milanko-postgres
docker exec milanko-postgres pg_isready -U postgres
docker logs --tail 100 milanko-postgres
```

If the volume is corrupted, restore from the latest dump in
`/srv/milanko/dumps/`; see [`data-seed.md`](data-seed.md). Do not delete the
volume without a verified dump.

### API is down

```bash
docker logs --tail 100 milanko-api-<env>
docker inspect milanko-api-<env> --format '{{.State.Status}} {{.State.Health.Status}}'
curl -fsS http://127.0.0.1:<8011|8012|8013>/health
```

The container uses `--restart unless-stopped`. If the healthcheck fails, check
`DATABASE_URL`, PostgreSQL and the image tag. The deploy pipeline keeps
`milanko-api:<env>-<sha>` tags for rollback.

### Disk pressure

```bash
docker system df
docker image prune -f
df -h /
du -sh /srv/milanko/cache/* /srv/milanko/dumps/* 2>/dev/null
```

Delete old compressed dumps only after verifying the latest restore. The cache
is disposable; deleting it forces NASA clients to re-fetch.

### Journald growth

The default journal can grow to a large fraction of the disk. Cap it:

```ini
# /etc/systemd/journald.conf
[Journal]
SystemMaxUse=500M
SystemMaxFileSize=50M
```

Then `sudo systemctl restart systemd-journald`. This is a recommendation; the
current host uses the distribution default.

## 12. Update and deploy procedure

1. Push to `develop`; the pipeline runs tests, OpenAPI checks, Docker build and
   deploy.
2. Verify develop (`/health`, `/regions`, `/events/stats`, `/ping` with key).
3. Fast-forward `qa` and repeat the checks.
4. Fast-forward `main`; approve the `production` Environment deployment.
5. After changing `ops/systemd/`, re-run `sudo ops/systemd/install-all.sh` on
   the VPS.
6. Do not run a full historical backfill during a deploy or during another
   environment's timer window. The daily increments are safe.

The image is currently built on the VPS (no registry). The deploy leaves
`milanko-api:<env>` and `milanko-api:<env>-<sha>` tags; use the SHA tag for a
manual rollback.

## 13. Fresh-host checklist

- [ ] `ops/vps/bootstrap.sh` (Docker, nginx, Certbot, psql client, swap, UFW).
- [ ] `milanko` Docker network and `/srv/milanko` layout.
- [ ] PostgreSQL container, roles and databases.
- [ ] Dump restored into `milanko_develop`; QA/production cloned.
- [ ] `ANALYZE` and materialized views present.
- [ ] `/etc/milanko/backend-<env>.env` and API key TSV files.
- [ ] `ops/vps/apply-nginx.sh`, Cloudflare ranges and Let's Encrypt.
- [ ] Backend deployed on the three branches; health and API key smoke test.
- [ ] `/etc/milanko/frontend-<env>.env` and frontend deploy variables.
- [ ] `ops/systemd/install-all.sh` and nine timers listed.
- [ ] `journalctl` and `ingest_runs` show the first successful run.
- [ ] Disk, RAM, swap and Docker log rotation checked.

## 14. Frontend process (target)

The current frontend code is a Next.js server with rewrites, not a static
export. The target deployment is:

```bash
docker run -d \
  --name milanko-web-<env> \
  --restart unless-stopped \
  --network milanko \
  -p 127.0.0.1:<8021|8022|8023>:3000 \
  --env-file /etc/milanko/frontend-<env>.env \
  --log-opt max-size=50m \
  --log-opt max-file=3 \
  milanko-web:<env>
```

- `MILANKO_API_URL` points to the internal API
  (`http://milanko-api-<env>:8000`), so server-side requests do not need the
  public API key.
- If the frontend uses the public API URL instead, it must send
  `X-API-Key: $MILANKO_API_KEY`.
- nginx must proxy `/` to `127.0.0.1:<8021|8022|8023>` when the container is
  deployed; today it serves the static placeholder.
- If the team chooses a static export instead, remove the container variables
  and publish the `out/` directory to `/srv/milanko/frontend/<env>`; the
  frontend API key becomes public in the bundle.

## 15. Quick reference

| Task | Command |
|---|---|
| API health | `curl -fsS https://<domain>/api/v1/health` |
| Container status | `docker ps --format 'table {{.Names}}\t{{.Status}}'` |
| Resource use | `docker stats --no-stream` |
| Timers | `systemctl list-timers 'milanko-ingest-*' --all` |
| Worker logs | `journalctl -u 'milanko-ingest@*' -n 100` |
| Manual ingest | `sudo /usr/local/bin/milanko-ingest power-<env>` |
| PostgreSQL | `docker exec milanko-postgres psql -U postgres` |
| Ingest runs | `SELECT * FROM ingest_runs ORDER BY started_at DESC LIMIT 20;` |
| Nginx test | `sudo nginx -t` |
| TLS dry run | `sudo certbot renew --dry-run --no-random-sleep-on-renew` |
| Reinstall timers | `sudo ops/systemd/install-all.sh` |
