#!/usr/bin/env bash
# install-stack.sh — stage the NemoClaw + OpenClaw + OpenShell (+ colibri) stack for offline USB,
# and install it at the venue. Install commands are the VERIFIED-correct ones (see setup/README.md:
# npm `openshell`/`nemoclaw` and PyPI `colibri` are SQUATS — we avoid them).
#
# Usage:
#   setup/install-stack.sh stage   [--dir DIR] [--dry-run]   # TONIGHT, fast Wi-Fi: download to USB
#   setup/install-stack.sh install [--dir DIR] [--dry-run]   # VENUE: install from the staged DIR
#   setup/install-stack.sh --help
#
# Env: STACK_DIR (default ./stack-bundle), PIP_PLATFORM(manylinux2014_aarch64), PY_VERSION(3.12)
#
# Complements scripts/bundle-offline.sh (which stages MODELS + docker images). This one = the STACK.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"
[[ -f "$ROOT/.env" ]] && set -a && . "$ROOT/.env" && set +a || true

MODE="${1:-}"; shift || true
DRY=0; STACK_DIR="${STACK_DIR:-$ROOT/stack-bundle}"
PIP_PLATFORM="${PIP_PLATFORM:-manylinux2014_aarch64}"; PY_VERSION="${PY_VERSION:-3.12}"
while [[ $# -gt 0 ]]; do case "$1" in
  --dir) STACK_DIR="$2"; shift ;; --dry-run) DRY=1 ;;
  -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown arg: $1" >&2; exit 2 ;; esac; shift; done

say(){ printf '\033[1m==>\033[0m %s\n' "$*"; }
skip(){ printf '    \033[33m↷\033[0m %s\n' "$*"; }
run(){ if [[ "$DRY" == 1 ]]; then printf '    [dry-run] %s\n' "$*"; else printf '    $ %s\n' "$*"; eval "$@"; fi; }

# ── verified source URLs / packages ─────────────────────────────────────────
NEMOCLAW_SH="https://raw.githubusercontent.com/NVIDIA/NemoClaw/refs/heads/main/uninstall.sh"  # see README: real installer is nemoclaw.sh (NGC); uninstall.sh shown as a known-good raw asset
OPENSHELL_SH="https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh"
declare -a REPOS=(
  "NVIDIA/NemoClaw"       # TS orchestrator (DGX/WSL)
  "NVIDIA/OpenShell"      # Rust sandbox+gateway (Linux / macOS-AS / WSL2)
  "JustVugg/colibri"      # C MoE engine, OpenAI-compatible server
)
# NOTE: openclaw/openclaw source is ~7.5 GB — we DON'T git-bundle it; we stage the npm tarball instead.

stage() {
  say "Staging stack into: $STACK_DIR   (dry-run=$DRY)"
  run "mkdir -p '$STACK_DIR'/{repos,npm,wheels,installers,colibri-bin,openshell-bin}"

  say "Git bundles (platform-agnostic source; small except openclaw which we skip)"
  for r in "${REPOS[@]}"; do
    name="${r#*/}"; out="$STACK_DIR/repos/${name}.bundle"
    [[ -s "$out" ]] && { skip "$name.bundle exists"; continue; }
    run "git clone --depth 1 'https://github.com/$r.git' '$STACK_DIR/repos/$name.src'"
    run "git -C '$STACK_DIR/repos/$name.src' bundle create '$out' --all"
  done

  say "OpenClaw (npm tarball — JS is platform-agnostic; native deps rebuild at install)"
  run "cd '$STACK_DIR/npm' && npm pack openclaw"       # → openclaw-<ver>.tgz
  skip "note: npm deps still fetched at install time unless you also copy an npm cache (~/.npm). See README."

  say "OpenShell (REAL = PyPI wheel for aarch64 + install.sh + GitHub release binary)"
  run "pip download openshell --platform '$PIP_PLATFORM' --python-version '$PY_VERSION' --only-binary=:all: -d '$STACK_DIR/wheels' || true"
  run "curl -fsSL '$OPENSHELL_SH' -o '$STACK_DIR/installers/openshell-install.sh'"
  skip "also grab, by hand: OpenShell linux-arm64 release binary from github.com/NVIDIA/OpenShell/releases → openshell-bin/"

  say "NemoClaw (installer script; real nemoclaw.sh is NGC-gated — see README for the exact curl)"
  run "curl -fsSL '$NEMOCLAW_SH' -o '$STACK_DIR/installers/nemoclaw-uninstall.sh' || true"
  skip "fetch the real installer per README (needs NGC); the git bundle above has the source as a fallback"

  say "colibri (git bundle above + prebuilt linux-arm64 release binary)"
  skip "download colibri linux-arm64 release from github.com/JustVugg/colibri/releases → colibri-bin/ (small)"

  say "Checksums"
  SHA="sha256sum"; command -v sha256sum >/dev/null 2>&1 || SHA="shasum -a 256"
  run "cd '$STACK_DIR' && find repos npm wheels installers colibri-bin openshell-bin -type f 2>/dev/null | sort | xargs -r $SHA > SHA256SUMS || true"
  say "Staged. Verify with: ls -R '$STACK_DIR'  (and scripts/verify-bundle.sh for the model bundle)"
}

install() {
  say "Installing stack from: $STACK_DIR   (dry-run=$DRY)"
  [[ -d "$STACK_DIR" ]] || { echo "staged dir '$STACK_DIR' not found — run 'stage' first (or pass --dir)"; exit 1; }

  say "OpenClaw (npm global from staged tarball; falls back to registry)"
  if ls "$STACK_DIR"/npm/openclaw-*.tgz >/dev/null 2>&1; then
    run "npm i -g --allow-scripts=openclaw \"$(ls "$STACK_DIR"/npm/openclaw-*.tgz | head -1)\""
  else
    run "npm i -g openclaw@latest --allow-scripts=openclaw"
  fi

  say "OpenShell (offline wheel first, else install.sh)"
  if ls "$STACK_DIR"/wheels/openshell-*.whl >/dev/null 2>&1; then
    run "pip install --no-index --find-links '$STACK_DIR/wheels' openshell"
  elif [[ -s "$STACK_DIR/installers/openshell-install.sh" ]]; then
    run "sh '$STACK_DIR/installers/openshell-install.sh'"
  else
    skip "no staged OpenShell — run: curl -LsSf $OPENSHELL_SH | sh"
  fi

  say "colibri (prebuilt binary if staged, else build from the bundle)"
  if ls "$STACK_DIR"/colibri-bin/* >/dev/null 2>&1; then
    skip "copy colibri-bin/* onto PATH (e.g. /usr/local/bin) and chmod +x"
  elif [[ -s "$STACK_DIR/repos/colibri.bundle" ]]; then
    run "git clone '$STACK_DIR/repos/colibri.bundle' '$STACK_DIR/colibri.src' && cd '$STACK_DIR/colibri.src/c' && ./setup.sh"
  fi

  say "NemoClaw (the orchestrator — needs the real installer; see README)"
  skip "run the NGC-authenticated nemoclaw.sh per setup/README.md, then: nemoclaw onboard"

  say "Post-install sanity"
  run "openclaw --version || true"
  run "openshell --version || true"
  say "Done. Next: configs/models.md + 'nemoclaw onboard' (GB10 only). See docs/onboarding/03-day-of-runbook.md"
}

case "$MODE" in
  stage) stage ;;
  install) install ;;
  *) echo "usage: $0 {stage|install} [--dir DIR] [--dry-run]   (--help for detail)"; exit 2 ;;
esac
