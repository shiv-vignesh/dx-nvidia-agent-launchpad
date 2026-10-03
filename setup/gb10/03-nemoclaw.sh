#!/usr/bin/env bash
# Stage 3 — NemoClaw (orchestrator) install + onboard. THE risky stage:
#   (a) needs NGC_API_KEY + HF_TOKEN  (from ~/shiftguard-secrets.env, NOT synced/committed)
#   (b) `nemoclaw onboard` is an INTERACTIVE WIZARD — this script does the deterministic
#       prep (docker login + install) non-interactively, then onboard runs only if it has a
#       TTY; otherwise it prints the exact command for you to run interactively.
#   (c) DGX-Spark detection: this box reports "Dell Pro Max with GB10". If NemoClaw treats it
#       as generic arm64, Express Install is gone and the Qwen slug is rejected → fall back to
#       self-serve vLLM (NEMOCLAW_PROVIDER=vllm). We watch onboard's output to find out.
set -euo pipefail

SECRETS="${HOME}/shiftguard-secrets.env"
[ -f "$SECRETS" ] || { echo "ERROR: $SECRETS not found — create it with NGC_API_KEY + HF_TOKEN"; exit 1; }
# shellcheck disable=SC1090
. "$SECRETS"
: "${NGC_API_KEY:?NGC_API_KEY not set in secrets}"; : "${HF_TOKEN:?HF_TOKEN not set in secrets}"

echo "== docker login nvcr.io (user is literally \$oauthtoken) =="
echo "$NGC_API_KEY" | docker login nvcr.io -u '$oauthtoken' --password-stdin

echo "== install NemoClaw (non-interactive: accept third-party upfront, no Express) =="
if command -v nemoclaw >/dev/null 2>&1; then
  echo "nemoclaw already present: $(nemoclaw --version 2>&1 | head -1 || echo installed)"
else
  curl -fsSLo /tmp/nemoclaw.sh https://www.nvidia.com/nemoclaw.sh
  # NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1 clears the TTY acceptance gate; </dev/null declines the
  # Express-Install prompt so this just installs the CLI and we run `onboard` interactively after.
  NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1 bash /tmp/nemoclaw.sh < /dev/null
fi
# NemoClaw installs user-local: CLI → ~/.npm-global/bin, OpenShell → ~/.local/bin
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$HOME/.nemoclaw/bin:/usr/local/bin:$PATH"
command -v nemoclaw >/dev/null 2>&1 || { echo "ERROR: nemoclaw not on PATH after install — check installer output above (may need a fresh shell)"; exit 1; }
echo "nemoclaw installed: $(nemoclaw --version 2>&1 | head -1 || echo ok)"

export HF_TOKEN
ONBOARD_CMD='nemoclaw onboard --name shiftguard'
echo "== onboard =="
if [ -t 0 ] && [ -t 1 ]; then
  echo "interactive TTY detected — launching the wizard. Choose: agent=OpenClaw, provider=install-vllm"
  echo "(if it rejects the Spark model, re-run with: NEMOCLAW_PROVIDER=vllm $ONBOARD_CMD)"
  eval "$ONBOARD_CMD"
  echo "---- nemoclaw status ----"; nemoclaw shiftguard status 2>&1 | head -15 || true
else
  echo "NO TTY (runway task is non-interactive). Prep done (docker login + nemoclaw installed)."
  echo "Run onboarding yourself in your SSH session on the box:"
  echo "    export PATH=\"\$HOME/.npm-global/bin:\$HOME/.local/bin:\$PATH\""
  echo "    source ~/shiftguard-secrets.env"
  echo "    $ONBOARD_CMD"
  echo "Then verify:  nemoclaw shiftguard status"
  echo "== stage 3 PREP OK — onboard pending (interactive) =="
fi