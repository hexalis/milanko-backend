# API keys

The public edge validates an API key in **nginx** before proxying to FastAPI.
FastAPI documents the contract in OpenAPI (the "Authorize" button) but does not
duplicate the check.

## Contract

- Header: `X-API-Key: <key>`.
- Missing or invalid key: `401` with
  `{"detail":"Invalid or missing API key"}`.
- Rate limit exceeded: `429` with `{"detail":"Rate limit exceeded"}`.
- `OPTIONS` bypasses the key check so the backend can answer CORS preflight.
- Public routes: `/api/v1/health`, `/api/v1/docs`, `/api/v1/redoc`,
  `/api/v1/openapi.json` (and their `/api/...` legacy aliases).
- All other routes, including `/api/v1/ping`, require a key.
- nginx strips `X-API-Key` before proxying so the key never reaches backend
  logs.

## Keys per environment

Each environment has its own key file:

```text
/etc/milanko/api-keys-develop.tsv
/etc/milanko/api-keys-qa.tsv
/etc/milanko/api-keys-production.tsv
```

Format (`client<TAB>key`):

```text
public-web	mk_develop_public_<random>
internal-smoke	mk_develop_internal_<random>
```

Generate keys with:

```bash
openssl rand -hex 24
```

Use a prefix (`mk_<env>_public_`, `mk_<env>_internal_`) for identification.
Keys must be at least 32 characters.

## Render the nginx maps

```bash
sudo ops/vps/nginx/render-api-keys.sh develop
sudo ops/vps/nginx/render-api-keys.sh qa
sudo ops/vps/nginx/render-api-keys.sh production
```

The script writes `/etc/nginx/snippets/milanko-api-keys-<env>.conf` (`0600`),
validates nginx and reloads it.

## Rate limits

| Scope | Rate | Burst |
|---|---|---|
| Client IP (`CF-Connecting-IP` via real-IP) | 20 r/s | 40 |
| API key | 10 r/s | 20 |
| Concurrent connections per IP | 20 | - |

Cloudflare's IP ranges are trusted for `real_ip_header CF-Connecting-IP`; the
list is refreshed with `ops/vps/nginx/cloudflare-realip.sh`.

## Rotation

1. Generate a new key and add it to the environment TSV.
2. Run `render-api-keys.sh <env>`.
3. Update the client (frontend build or `SMOKE_API_KEY` secret).
4. Remove the old line and reload again.

## Public frontend caveat

The public frontend is a static site. A key embedded in its JavaScript bundle
is **not a secret**: anyone can read it. The key is a minimal gate that lets us
identify/revoke clients and apply rate limits; it is not real authentication.
For stronger protection, add Cloudflare Access, a backend-for-frontend proxy or
user authentication.

## Examples

```bash
KEY="$(awk -F'\t' '$1=="internal-smoke"{print $2}' /etc/milanko/api-keys-develop.tsv)"

# Public
curl -fsS https://dev-milanko.hexalis.org/api/v1/health

# Key required
curl -i https://dev-milanko.hexalis.org/api/v1/ping          # 401
curl -fsS -H "X-API-Key: $KEY" https://dev-milanko.hexalis.org/api/v1/ping

# CORS preflight
curl -i -X OPTIONS https://dev-milanko.hexalis.org/api/v1/ping \
  -H 'Origin: https://hexalis.github.io' \
  -H 'Access-Control-Request-Headers: x-api-key'
```
