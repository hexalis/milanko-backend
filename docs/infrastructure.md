# Infrastructure

## VPS

| Item | Value |
|---|---|
| Host | `core-monolith-02` |
| OS | Ubuntu 26.04.1 LTS |
| CPU / RAM | 2 vCPU / 3.8 GiB + 4 GiB swap |
| Disk | 96 GB |
| Docker | `docker-ce` from the official Ubuntu `resolute` repository |
| PostgreSQL | `postgres:17-alpine` container, no published port |
| Edge | nginx + Let's Encrypt + Cloudflare proxy |

The host bootstrap is idempotent:

```bash
sudo ops/vps/bootstrap.sh
```

It installs Docker, nginx, Certbot, the PostgreSQL client, `jq` and `ufw`;
creates the 4 GiB swap file, the `deploy` user, `/srv/milanko`, `/etc/milanko`,
the `milanko` Docker network and the UFW rules (22, 80, 443).

## Databases and roles

```text
milanko-postgres (postgres:17-alpine)
├── milanko_develop     owner milanko_develop_app
├── milanko_qa          owner milanko_qa_app
└── milanko_production  owner milanko_production_app
```

The container runs with `--shm-size=512m`, `--memory=1536m`, no published
port, a named volume `milanko-postgres-data`, and conservative PostgreSQL
settings (`shared_buffers=512MB`, `work_mem=16MB`,
`maintenance_work_mem=256MB`, `max_connections=50`).

The application roles own their databases. Restores must use:

```bash
pg_restore --no-owner --no-privileges --role=milanko_<env>_app
```

so tables and materialized views belong to the environment role. See
[`data-seed.md`](data-seed.md).

## Environment files

`/etc/milanko/backend-<env>.env` is `root:deploy 0640` and contains:

```dotenv
DATABASE_URL=postgresql+psycopg://milanko_<env>_app:<password>@milanko-postgres:5432/milanko_<env>
NASA_API_KEY=...
FIRMS_MAP_KEY=...
EARTHDATA_TOKEN=...
```

The PostgreSQL superuser password lives in `/etc/milanko/postgres.env`
(`0600`). API keys live in `/etc/milanko/api-keys-<env>.tsv` (`0600`).

## nginx

- Site: `/etc/nginx/sites-available/milanko`.
- API maps and rate limits: `/etc/nginx/conf.d/milanko-api.conf`.
- Key maps: `/etc/nginx/snippets/milanko-api-keys-<env>.conf` (generated).
- Proxy and error snippets: `/etc/nginx/snippets/milanko-api-{proxy,errors}.conf`.
- Cloudflare real IP: `/etc/nginx/snippets/cloudflare-realip.conf`.
- Static placeholder: `/srv/milanko/frontend/<env>/index.html`.

Apply the checked-in configuration with:

```bash
sudo ops/vps/apply-nginx.sh
```

The script installs the site, maps, snippets and Cloudflare ranges, renders the
three API-key maps and reloads nginx.

## TLS

The three public domains use Let's Encrypt certificates obtained with the
webroot challenge. Cloudflare proxies the domains and forwards
`/.well-known/acme-challenge/` over HTTP to the origin, so renewal is automatic:

```bash
sudo certbot certonly --webroot -w /var/www/html \
  -d dev-milanko.hexalis.org \
  -d qa-milanko.hexalis.org \
  -d milanko.hexalis.org \
  --cert-name milanko.hexalis.org
```

Cloudflare SSL/TLS mode should be **Full (strict)**.

## DNS

Create these proxied `A` records in Cloudflare:

| Name | Target |
|---|---|
| `dev-milanko` | new VPS |
| `qa-milanko` | new VPS |
| `milanko` | new VPS |

## GitHub Environments

Create `develop`, `qa` and `production` in `hexalis/milanko-backend`, add the
secrets and variables listed in [`pipelines.md`](pipelines.md), and restrict
production to `main` with required reviewers.

## Firewall

- GCP: allow ingress TCP 80 and 443 (HTTP/HTTPS tags or firewall rule).
- UFW on the VPS: allow 22, 80 and 443.
- PostgreSQL is only reachable on the internal `milanko` Docker network.
- API containers publish only on `127.0.0.1`.

## Verification

```bash
curl -fsS https://dev-milanko.hexalis.org/api/v1/health
curl -fsS https://qa-milanko.hexalis.org/api/v1/health
curl -fsS https://milanko.hexalis.org/api/v1/health
```

Without `X-API-Key`, `/api/v1/ping` must return `401`; with the
`internal-smoke` key it must return `{"pong":true}`.
