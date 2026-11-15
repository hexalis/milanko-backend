# Ingestion timers

The timers run the same image as the API (`milanko-api:<environment>`) as a
one-off container on the `milanko` Docker network. The database and NASA
credentials come from `/etc/milanko/backend-<environment>.env`.

## Schedule (UTC)

| Environment | POWER | EONET | GIBS |
|---|---|---|---|
| develop | 03:15 | 04:15 | 05:30 |
| qa | 06:15 | 07:15 | 08:30 |
| production | 09:15 | 10:15 | 11:30 |

All timers use `Persistent=true` and a randomized delay of up to 15 minutes.
The runner uses `flock` to prevent overlapping jobs.

## Install

```bash
sudo ops/systemd/install-all.sh
systemctl list-timers 'milanko-ingest-*' --all --no-pager
```

The ingestion modules (`backend.ingest_power`, `backend.ingest_eonet` and
`backend.ingest_gibs`) are migrated from the POC. Install the timers once those
modules exist in the image; until then they will fail with a clear Python
`ModuleNotFoundError`.

## Manual run

```bash
sudo milanko-ingest power-develop
sudo milanko-ingest power-qa
sudo milanko-ingest power-production
```

Use `journalctl -u 'milanko-ingest@*' -n 100 --no-pager` to inspect the logs.
