#!/usr/bin/env bash
# Stage 0 — GB10 prerequisites: docker group + daemon, Node 22.x.
# Idempotent. Requires passwordless sudo (see setup/TEAMMATE / the runbook).
set -euo pipefail

echo "== user / sudo =="
whoami
sudo -n true 2>/dev/null && echo "passwordless sudo: ok" || { echo "ERROR: passwordless sudo required for this stage"; exit 1; }

echo "== docker group =="
if id -nG | tr ' ' '\n' | grep -qx docker; then
  echo "already in docker group"
else
  sudo usermod -aG docker "$USER"
  echo "added $USER to docker group (takes effect on next login; this script uses sudo docker meanwhile)"
fi

echo "== docker daemon =="
sudo systemctl enable --now docker
sudo docker version --format 'server {{.Server.Version}}'

echo "== node 22.x =="
need_node=1
if command -v node >/dev/null 2>&1; then
  major="$(node -v | sed 's/^v\([0-9]*\).*/\1/')"
  [ "${major:-0}" -ge 22 ] && { need_node=0; echo "node $(node -v) already >= 22"; }
fi
if [ "$need_node" = 1 ]; then
  echo "installing Node 22.x via NodeSource..."
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
echo "node $(node -v) / npm $(npm -v)"

echo "== stage 0 OK =="