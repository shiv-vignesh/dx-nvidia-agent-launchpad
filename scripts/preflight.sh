#!/usr/bin/env bash
# preflight.sh — is this box ready for NemoClaw onboarding?
# Read-only checks: OS/arch, GPU, Docker, disk, required ports free.
# Usage: scripts/preflight.sh [--dry-run] [--help]
set -euo pipefail

DRY_RUN=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown arg: $a (try --help)" >&2; exit 2 ;;
  esac
done

# Ports NemoClaw/OpenShell/OpenClaw use (doc-backed). 11434 is Ollama — ⚠ unverified, checked anyway.
PORTS_DOC="8000 8080 18789"
PORT_OLLAMA="11434"
MIN_DISK_GB="${MIN_DISK_GB:-120}"   # vLLM image + weights + staging; override via env

pass=0; warn=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; pass=$((pass+1)); }
nope() { printf '  \033[31m✗\033[0m %s\n' "$*"; fail=$((fail+1)); }
flag() { printf '  \033[33m!\033[0m %s\n' "$*"; warn=$((warn+1)); }
hdr()  { printf '\n\033[1m%s\033[0m\n' "$*"; }

port_in_use() {
  local p="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$p" -sTCP:LISTEN -P -n >/dev/null 2>&1
  elif command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -q ":$p "
  elif command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$p" >/dev/null 2>&1
  else
    return 2  # no tool to check
  fi
}

if [[ "$DRY_RUN" == 1 ]]; then
  echo "[dry-run] would check: OS/arch, nvidia-smi, docker, >=${MIN_DISK_GB}GB disk, ports ${PORTS_DOC} ${PORT_OLLAMA}, nemoclaw/openshell CLIs"
  exit 0
fi

echo "NemoClaw preflight — $(date 2>/dev/null || true)"

hdr "OS / architecture"
OS="$(uname -s)"; ARCH="$(uname -m)"
echo "  $OS $ARCH"
case "$ARCH" in
  aarch64|arm64) ok "arm64 architecture" ;;
  *) flag "arch is $ARCH — venue box should be linux arm64" ;;
esac
[[ "$OS" == "Linux" ]] && ok "Linux" || flag "$OS (venue box is Linux; this is fine for prep)"

hdr "GPU"
if command -v nvidia-smi >/dev/null 2>&1; then
  if nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader 2>/dev/null | sed 's/^/  /' || true
    ok "nvidia-smi works"
    flag "Confirm this box is detected as a DGX Spark: run 'nemoclaw host probe' && 'nemoclaw profiles list'"
  else
    nope "nvidia-smi present but failed to run"
  fi
else
  flag "nvidia-smi not found (expected on the GB10; fine on a dev laptop)"
fi

hdr "Docker"
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    ok "docker daemon reachable ($(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?'))"
  else
    nope "docker installed but daemon not reachable (start Docker / check permissions)"
  fi
else
  nope "docker not found"
fi

hdr "Disk space"
AVAIL_GB="$(df -Pk . 2>/dev/null | awk 'NR==2{printf "%d", $4/1024/1024}')"
if [[ -n "${AVAIL_GB:-}" ]]; then
  if (( AVAIL_GB >= MIN_DISK_GB )); then ok "${AVAIL_GB} GB free (need >= ${MIN_DISK_GB})"
  else nope "${AVAIL_GB} GB free — need >= ${MIN_DISK_GB} GB for image + weights + staging"; fi
else
  flag "could not determine free disk"
fi

hdr "Ports (must be FREE before onboarding)"
for p in $PORTS_DOC; do
  if port_in_use "$p"; then nope "port $p in use (vLLM 8000 / gateway 8080 / dashboard 18789)"
  else ok "port $p free"; fi
done
if port_in_use "$PORT_OLLAMA"; then
  flag "port $PORT_OLLAMA in use — an Ollama server may be running (⚠ Ollama provider unverified in docs)"
else
  ok "port $PORT_OLLAMA free (Ollama, ⚠ unverified)"
fi

hdr "Stack CLIs (optional — installed by nemoclaw.sh)"
for c in nemoclaw openshell openclaw node; do
  if command -v "$c" >/dev/null 2>&1; then ok "$c: $("$c" --version 2>/dev/null | head -1 || echo present)"
  else flag "$c not installed yet"; fi
done

hdr "Summary"
printf "  %d ok · %d warnings · %d failures\n" "$pass" "$warn" "$fail"
if (( fail > 0 )); then
  echo "  → fix failures before 'nemoclaw onboard'. See docs/onboarding/04-debugging.md"
  exit 1
fi
echo "  → looks good. Next: scripts/bundle-offline.sh (tonight), then 'nemoclaw onboard' (venue)."
