#!/usr/bin/env bash
# verify-stack — end-to-end health of the stack on the GB10. Read-only; never fails hard
# (reports each layer so we see exactly what's green/red).
set +e

ok(){ printf '  \033[32m✓\033[0m %s\n' "$*"; }
no(){ printf '  \033[31m✗\033[0m %s\n' "$*"; }
hd(){ printf '\n\033[1m%s\033[0m\n' "$*"; }

hd "Node / Docker"
node -v >/dev/null 2>&1 && ok "node $(node -v)" || no "node missing"
docker info >/dev/null 2>&1 && ok "docker usable ($(docker version --format '{{.Server.Version}}' 2>/dev/null))" || no "docker not usable by this user"

hd "OpenShell"
if command -v openshell >/dev/null 2>&1; then
  ok "openshell $(openshell --version 2>&1 | head -1)"
  openshell status 2>/dev/null | grep -qi Connected && ok "gateway Connected" || no "gateway not Connected"
  openshell sandbox list 2>/dev/null | head -5
else no "openshell not installed"; fi

hd "OpenClaw"
command -v openclaw >/dev/null 2>&1 && ok "$(openclaw --version 2>&1 | head -1)" || no "openclaw not installed"

hd "NemoClaw + inference"
if command -v nemoclaw >/dev/null 2>&1; then
  ok "nemoclaw present"
  echo "  -- nemoclaw shiftguard status --"; nemoclaw shiftguard status 2>&1 | sed 's/^/  /' | head -15
  docker ps --format '{{.Names}}' 2>/dev/null | grep -q nemoclaw-vllm && ok "nemoclaw-vllm container running" || no "nemoclaw-vllm not running"
  curl -sS -m5 -o /dev/null -w "  vLLM /v1/models http=%{http_code}\n" http://127.0.0.1:8000/v1/models 2>/dev/null || no "vLLM :8000 unreachable"
else no "nemoclaw not installed (stage 3 pending)"; fi

hd "GPU"
nvidia-smi --query-gpu=name,compute_cap,memory.used,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/  /' || no "nvidia-smi n/a"
echo ""