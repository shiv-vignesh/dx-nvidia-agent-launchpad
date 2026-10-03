#!/usr/bin/env bash
# Stage 2 — OpenClaw (the agent runtime) on the GB10. Needs Node 22.x (stage 0).
# Global npm install under NodeSource lives in /usr/lib → needs root (passwordless sudo).
# Idempotent.
set -euo pipefail

command -v node >/dev/null 2>&1 || { echo "ERROR: node missing — run stage 0 first"; exit 1; }
echo "node $(node -v) / npm $(npm -v)"

if command -v openclaw >/dev/null 2>&1; then
  echo "openclaw already present: $(openclaw --version 2>&1 | head -1)"
else
  echo "== npm i -g openclaw (allow native build scripts: koffi/esbuild) =="
  sudo npm i -g openclaw --allow-scripts=openclaw
fi

command -v openclaw >/dev/null 2>&1 || { echo "ERROR: openclaw not on PATH after install"; exit 1; }
echo "== verify =="
openclaw --version 2>&1 | head -1
echo "== stage 2 OK =="