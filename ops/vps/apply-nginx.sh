#!/usr/bin/env bash
# Install the nginx site, API-key maps and snippets. Run as root.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
nginx_dir="$here/nginx"

install -d -m 755 /etc/nginx/snippets
install -m 644 "$nginx_dir/milanko.conf" /etc/nginx/sites-available/milanko
ln -sfn /etc/nginx/sites-available/milanko /etc/nginx/sites-enabled/milanko
rm -f /etc/nginx/sites-enabled/default

install -m 644 "$nginx_dir/milanko-api.conf" /etc/nginx/conf.d/milanko-api.conf
install -m 644 "$nginx_dir/snippets/milanko-api-proxy.conf" /etc/nginx/snippets/milanko-api-proxy.conf
install -m 644 "$nginx_dir/snippets/milanko-api-errors.conf" /etc/nginx/snippets/milanko-api-errors.conf

"$nginx_dir/cloudflare-realip.sh" --no-reload

for env in develop qa production; do
  if [ -r "/etc/milanko/api-keys-${env}.tsv" ]; then
    "$nginx_dir/render-api-keys.sh" "$env" --no-reload
  else
    echo "WARNING: /etc/milanko/api-keys-${env}.tsv is missing; creating an empty key map" >&2
    printf '# no keys configured for %s\n' "$env" > "/etc/nginx/snippets/milanko-api-keys-${env}.conf"
    chmod 600 "/etc/nginx/snippets/milanko-api-keys-${env}.conf"
  fi
done

install -d -m 755 /var/www/html/.well-known/acme-challenge
nginx -t
systemctl reload nginx
echo "nginx configuration applied"
