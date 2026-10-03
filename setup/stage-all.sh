#!/usr/bin/env bash
# stage-all.sh — ONE command to build the whole USB: stack + models + images + wheels.
# Wraps scripts/bundle-offline.sh (models/images) and setup/install-stack.sh (stack repos/SDKs),
# checks prerequisites + tokens first, and prints the few by-hand downloads that remain.
#
# Usage:  setup/stage-all.sh --usb /Volumes/USB [--dry-run]
# Needs:  .env with NGC_API_KEY + HF_TOKEN, `docker login nvcr.io`, and: git docker node npm python3 pip curl
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"
[[ -f "$ROOT/.env" ]] && set -a && . "$ROOT/.env" && set +a || true

USB=""; DRY=""
while [[ $# -gt 0 ]]; do case "$1" in
  --usb) USB="$2"; shift ;; --dry-run) DRY="--dry-run" ;;
  -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown arg: $1" >&2; exit 2 ;; esac; shift; done
[[ -n "$USB" ]] || { echo "need --usb DIR (e.g. --usb /Volumes/USB)"; exit 2; }

ok(){ printf '  \033[32m✓\033[0m %s\n' "$*"; }
no(){ printf '  \033[31m✗\033[0m %s\n' "$*"; }
hd(){ printf '\n\033[1m%s\033[0m\n' "$*"; }
fail=0

hd "0. Preflight — tools, tokens, disk"
for c in git docker node npm python3 curl; do
  command -v "$c" >/dev/null 2>&1 && ok "$c" || { no "$c missing"; fail=1; }
done
command -v pip >/dev/null 2>&1 || command -v pip3 >/dev/null 2>&1 && ok "pip/pip3" || { no "pip missing"; fail=1; }
docker info >/dev/null 2>&1 && ok "docker daemon up" || { no "docker daemon not reachable (start Docker Desktop)"; fail=1; }
command -v hf >/dev/null 2>&1 && ok "hf CLI" || no "hf CLI missing — pip install 'huggingface_hub[cli]' (needed to download weights)"
[[ -n "${NGC_API_KEY:-}" ]] && ok "NGC_API_KEY set" || { no "NGC_API_KEY unset (.env) — needed for the vLLM image"; fail=1; }
[[ -n "${HF_TOKEN:-}" ]]    && ok "HF_TOKEN set"    || { no "HF_TOKEN unset (.env) — needed for weights"; fail=1; }
if docker info 2>/dev/null | grep -qi 'nvcr.io'; then ok "logged in to nvcr.io"; else no "run: docker login nvcr.io  (use NGC_API_KEY)"; fi
avail=$(df -Pk "$(dirname "$USB")" 2>/dev/null | awk 'NR==2{printf "%d",$4/1024/1024}')
[[ -n "$avail" ]] && { (( avail >= 120 )) && ok "${avail}GB free near USB" || no "${avail}GB free — want >=120GB for images+weights"; }
if [[ "$fail" == 1 && -z "$DRY" ]]; then echo; echo "Fix the ✗ above, then re-run. (Or preview with --dry-run.)"; exit 1; fi

hd "1. Stage MODELS + docker images + wheels  (scripts/bundle-offline.sh)"
bash "$ROOT/scripts/bundle-offline.sh" --usb "$USB" $DRY

hd "2. Stage the STACK  (setup/install-stack.sh stage)"
bash "$HERE/install-stack.sh" stage --dir "$USB/stack-bundle" $DRY

hd "3. BY-HAND downloads the scripts can't automate (do these now, fast Wi-Fi)"
cat <<EOF
  [ ] OpenShell linux-arm64 release binary  -> $USB/stack-bundle/openshell-bin/
      https://github.com/NVIDIA/OpenShell/releases   (pin the version NemoClaw requires)
  [ ] colibri linux-arm64 release binary    -> $USB/stack-bundle/colibri-bin/   (optional backend)
      https://github.com/JustVugg/colibri/releases
  [ ] Real NemoClaw installer (NGC-gated)   -> $USB/stack-bundle/installers/nemoclaw.sh
      curl -fsSLo "$USB/stack-bundle/installers/nemoclaw.sh" https://www.nvidia.com/nemoclaw.sh
  [ ] (optional) a literal Hermes model for experiments:
      hf download NousResearch/Hermes-3-Llama-3.1-8B --cache-dir "$USB/hf/hub"
  [ ] Node.js 22.19+ linux-arm64 tarball     -> $USB/stack-bundle/installers/
EOF

hd "4. Verify the model bundle  (scripts/verify-bundle.sh)"
bash "$ROOT/scripts/verify-bundle.sh" "$USB" $DRY || true

hd "Done."
echo "  Secrets (NGC/HF/Telegram) do NOT go on the USB — carry them in a password manager."
echo "  At the venue:  setup/install-stack.sh install --dir $USB/stack-bundle  ->  nemoclaw onboard"
