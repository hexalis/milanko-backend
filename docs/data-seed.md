# Data seed

The three PostgreSQL databases were seeded from a fresh dump of the legacy
`hexalis_develop` database on 2026-11-15.

## Current contents

| Item | Value |
|---|---|
| Regions (`locations`) | 162 |
| Variables | 46 (36 POWER + 10 GIBS) |
| GIBS source layers | 10 |
| Observations | ~51.6 million |
| EONET events | 25,142 |
| Event-region assignments | 27,991 |
| `region_monthly` rows | 1,500,460 |
| Alembic head | `c3d4e5f6a7b8` |

## Dump

The dump was taken from the old VPS (inside `hexalis-postgres`) and transferred
directly to the new VPS:

```bash
# On the old VPS
sudo docker exec hexalis-postgres pg_dump -U postgres -Fc -Z6 hexalis_develop \
  > /srv/hexalis/dumps/milanko_develop_<timestamp>.dump
```

The new VPS stores it at `/srv/milanko/dumps/`.

## Restore into develop

```bash
sudo docker exec -i milanko-postgres pg_restore \
  -U postgres \
  -d milanko_develop \
  --no-owner --no-privileges \
  --role=milanko_develop_app \
  --exit-on-error \
  < /srv/milanko/dumps/milanko_develop_<timestamp>.dump

sudo docker exec milanko-postgres psql -U postgres -d milanko_develop -c "ANALYZE"
```

`--role` makes the app role own every restored object, including the
materialized views. Without it, `REFRESH MATERIALIZED VIEW CONCURRENTLY` and
future migrations fail.

## Clone qa and production

`CREATE DATABASE ... TEMPLATE` is much faster than a second restore and copies
the data files:

```bash
sudo docker exec milanko-postgres psql -U postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='milanko_develop' AND pid <> pg_backend_pid();"

sudo docker exec milanko-postgres psql -U postgres \
  -c "CREATE DATABASE milanko_qa OWNER milanko_qa_app TEMPLATE milanko_develop;"
sudo docker exec milanko-postgres psql -U postgres -d milanko_qa \
  -c "REASSIGN OWNED BY milanko_develop_app TO milanko_qa_app;"

sudo docker exec milanko-postgres psql -U postgres \
  -c "CREATE DATABASE milanko_production OWNER milanko_production_app TEMPLATE milanko_develop;"
sudo docker exec milanko-postgres psql -U postgres -d milanko_production \
  -c "REASSIGN OWNED BY milanko_develop_app TO milanko_production_app;"
```

Run `ANALYZE` in each clone and verify the ownership:

```sql
SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public';
-- must return only milanko_<env>_app
```

## Verification

```sql
SELECT version_num FROM alembic_version;
SELECT count(*) FROM locations;
SELECT count(*) FROM variables;
SELECT count(*) FROM source_layers;
SELECT reltuples::bigint FROM pg_class WHERE relname = 'observations';
SELECT count(*) FROM events;
SELECT count(*) FROM event_regions;
SELECT count(*) FROM region_monthly;
```

## Incremental catch-up

The dump is current as of 2026-11-15. The systemd timers keep the three
databases current:

- POWER: last 14 days.
- EONET: last 45 days.
- GIBS: last 10 days, 2 workers.

If the new environment comes online later, run a manual catch-up from the dump
date before enabling the timers:

```bash
sudo milanko-ingest power-develop
sudo milanko-ingest eonet-develop
sudo milanko-ingest gibs-develop
```

Use the corresponding `-qa` / `-production` instance for the other databases.

## Disk

The three databases are ~18 GB each. The host has 96 GB, so the databases,
images, dump, cache and logs fit with roughly 30 GB of headroom. Incremental
data growth is small (roughly 7,500 rows/day across POWER and GIBS).
