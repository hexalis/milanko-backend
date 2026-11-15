#!/usr/bin/env bash
# Render /etc/nginx/snippets/milanko-api-keys-<env>.conf from the root-only TSV.
set -euo pipefail

env="${1:?usage: render-api-keys.sh <develop|qa|production>}"
src="/etc/milanko/api-keys-${env}.tsv"
dest="/etc/nginx/snippets/milanko-api-keys-${env}.conf"

[ -r "$src" ] || { echo "cannot read $src" >&2; exit 1; }

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
{
  echo "# generated from $src; do not edit by hand"
  while IFS=$'\t' read -r client key; do
    case "$client" in ""|\#*) continue ;; esac
    if [ "${#key}" -lt 32 ]; then
      echo "API key for $client is too short" >&2
      exit 1
    fi
    printf '    "%s" 1;\n' "$key"
  done < "$src"
} > "$tmp"

install -m 600 "$tmp" "$dest"
if [ "${2:-}" != "--no-reload" ]; then
  nginx -t
  systemctl reload nginx
  echo "API keys reloaded for $env"
else
  echo "API keys written for $env (reload deferred)"
fi
