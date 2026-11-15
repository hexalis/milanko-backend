#!/usr/bin/env bash
# One-shot container runner for Milanko NASA ingestion jobs.
set -euo pipefail

instance="${1:?usage: milanko-ingest <power|eonet|gibs>[-<develop|qa|production>]}"
if [[ "$instance" == *-* ]]; then
  job="${instance%%-*}"
  env_name="${instance#*-}"
else
  job="$instance"
  env_name="${MILANKO_ENV:-develop}"
fi

case "$env_name" in
  develop) image="milanko-api:develop"; cache="/srv/milanko/cache/develop" ;;
  qa) image="milanko-api:qa"; cache="/srv/milanko/cache/qa" ;;
  production) image="milanko-api:production"; cache="/srv/milanko/cache/production" ;;
  *) echo "invalid environment: $env_name" >&2; exit 2 ;;
esac

env_file="/etc/milanko/backend-${env_name}.env"
[ -r "$env_file" ] || { echo "cannot read $env_file" >&2; exit 2; }
mkdir -p "$cache"
chown 10001:10001 "$cache"
chmod 755 "$cache"

exec 9>"/run/milanko-ingest-${env_name}-${job}.lock"
flock -n 9 || { echo "job ${env_name}/${job} already running"; exit 0; }

case "$job" in
  power)
    args=(python -m backend.ingest_power --days "${POWER_DAYS:-14}")
    ;;
  eonet)
    since="$(date -u -d "${EONET_DAYS:-45} days ago" +%F)"
    args=(python -m backend.ingest_eonet --since "$since")
    ;;
  gibs)
    args=(python -m backend.ingest_gibs run --days "${GIBS_DAYS:-10}" --workers "${GIBS_WORKERS:-2}")
    ;;
  *)
    echo "invalid job: $job" >&2
    exit 2
    ;;
esac

exec docker run --rm \
  --name "milanko-ingest-${env_name}-${job}" \
  --network milanko \
  --env-file "$env_file" \
  --volume "${cache}:/app/data/cache:rw" \
  --log-opt max-size=50m \
  --log-opt max-file=3 \
  --no-healthcheck \
  "$image" "${args[@]}"
