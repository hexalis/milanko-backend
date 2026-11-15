#!/usr/bin/env bash
# Install and enable the nine ingestion timers. Run as root on the VPS.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install -m 755 "$here/milanko-ingest.sh" /usr/local/bin/milanko-ingest
install -m 644 "$here/milanko-ingest@.service" /etc/systemd/system/milanko-ingest@.service

for timer in "$here"/milanko-ingest-*.timer; do
  install -m 644 "$timer" "/etc/systemd/system/$(basename "$timer")"
done

systemctl daemon-reload
for timer in "$here"/milanko-ingest-*.timer; do
  systemctl enable --now "$(basename "$timer")"
done
systemctl list-timers 'milanko-ingest-*' --no-pager
