#!/usr/bin/env bash
# Host bootstrap for the Milanko VPS. Run as root on a fresh Ubuntu 24.04+ host.
# This script installs packages and creates the host layout; it does not create
# databases, secrets or API keys.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg git nginx certbot \
  python3-certbot-nginx postgresql-client jq ufw

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
printf 'vm.swappiness=10\n' > /etc/sysctl.d/99-milanko.conf
sysctl -p /etc/sysctl.d/99-milanko.conf >/dev/null

id -u deploy >/dev/null 2>&1 || useradd -m -s /bin/bash deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
touch /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys

install -d -m 750 -o root -g deploy /etc/milanko
install -d -m 700 -o root -g root /etc/ssl/milanko
install -d -m 755 -o deploy -g deploy /srv/milanko /srv/milanko/dumps /srv/milanko/frontend
for env in develop qa production; do
  install -d -m 755 -o deploy -g deploy "/srv/milanko/frontend/$env"
  install -d -m 755 "/srv/milanko/cache/$env"
  chown -R 10001:10001 "/srv/milanko/cache/$env"
done

docker network inspect milanko >/dev/null 2>&1 || docker network create milanko

ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

echo "Host bootstrap complete."
echo "Next: create PostgreSQL roles/databases, restore the dump, configure"
echo "/etc/milanko/backend-*.env and run ops/vps/apply-nginx.sh."
