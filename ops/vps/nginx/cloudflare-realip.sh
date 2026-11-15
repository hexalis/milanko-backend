#!/usr/bin/env bash
# Refresh the Cloudflare real-IP ranges and reload nginx.
set -euo pipefail

dest="/etc/nginx/snippets/cloudflare-realip.conf"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

{
  for ip in $(curl -fsS https://www.cloudflare.com/ips-v4) $(curl -fsS https://www.cloudflare.com/ips-v6); do
    echo "set_real_ip_from $ip;"
  done
  echo "real_ip_header CF-Connecting-IP;"
} > "$tmp"

install -m 644 "$tmp" "$dest"
nginx -t
systemctl reload nginx
echo "Cloudflare real-IP ranges updated"
