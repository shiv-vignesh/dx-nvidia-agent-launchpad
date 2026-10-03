#!/usr/bin/env bash
# bundle-offline.sh — build the offline USB bundle (run TONIGHT on fast Wi-Fi).
# Saves container images, HF weights, pip wheels, installers; writes SHA256SUMS.
# Model/image/wheel lists come from configs/models.md — NOTHING is hardcoded here.
#
# Usage: scripts/bundle-offline.sh [--dry-run] [--usb DIR] [--only images|models|wheels|installers] [--help]
# Env:   USB_DIR, HF_HOME, TARGET_PLATFORM(linux/arm64), PIP_PLATFORM(manylinux2014_aarch64), PY_VERSION(3.12)
#
# NOTE: this downloads tens of GB and needs `docker login nvcr.io` (NGC) + HF_TOKEN. It is idempotent:
# anything already present is skipped. It is an ACCELERATOR, not an air-gap (no documented offline install).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
MODELS_MD="$ROOT/configs/models.md"
[[ -f "$ROOT/.env" ]] && set -a && . "$ROOT/.env" && set +a || true

DRY_RUN=0; ONLY=""
USB_DIR="${USB_DIR:-$ROOT/bundle}"
TARGET_PLATFORM="${TARGET_PLATFORM:-linux/arm64}"
PIP_PLATFORM="${PIP_PLATFORM:-manylinux2014_aarch64}"
PY_VERSION="${PY_VERSION:-3.12}"
HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --usb) USB_DIR="$2"; shift ;;
    --only) ONLY="$2"; shift ;;
    -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
skip() { printf '    \033[33m↷ skip\033[0m %s\n' "$*"; }
run()  { if [[ "$DRY_RUN" == 1 ]]; then printf '    [dry-run] %s\n' "$*"; else printf '    $ %s\n' "$*"; eval "$@"; fi; }

# Extract the lines strictly between two HTML-comment markers in models.md, dropping blanks/comments.
extract_block() {
  local start="$1" end="$2"
  awk -v s="$start" -v e="$end" '
    $0 ~ s {grab=1; next} $0 ~ e {grab=0} grab' "$MODELS_MD" \
    | sed 's/#.*//' | awk 'NF'
}

should() { [[ -z "$ONLY" || "$ONLY" == "$1" ]]; }

COMPRESS="cat"; EXT="tar"
if command -v zstd >/dev/null 2>&1; then COMPRESS="zstd -T0 -19"; EXT="tar.zst"
else say "zstd not found — saving uncompressed .tar (bigger). brew install zstd to shrink."; fi

say "USB target: $USB_DIR   platform: $TARGET_PLATFORM   (dry-run=$DRY_RUN)"
run "mkdir -p '$USB_DIR'/{images,hf/hub,wheels,installers}"

# ── 1. Container images ────────────────────────────────────────────────────
if should images; then
  say "Container images (docker pull → docker save → $COMPRESS)"
  while IFS= read -r img; do
    [[ -z "$img" ]] && continue
    safe="$(echo "$img" | tr '/:@' '___')"
    out="$USB_DIR/images/${safe}.${EXT}"
    if [[ -s "$out" ]]; then skip "$out exists"; continue; fi
    run "docker pull --platform '$TARGET_PLATFORM' '$img'"
    run "docker save '$img' | $COMPRESS > '$out'"
  done < <(extract_block 'BUNDLE-IMAGES-START' 'BUNDLE-IMAGES-END')
fi

# ── 2. Model weights (HF cache layout, so NemoClaw's downloader reuses them) ─
if should models; then
  say "Model weights (hf download → $USB_DIR/hf/hub)"
  if ! command -v hf >/dev/null 2>&1 && [[ "$DRY_RUN" == 0 ]]; then
    say "⚠ 'hf' CLI missing — pip install 'huggingface_hub[cli]' (or add it to wheels and install)"
  fi
  while IFS= read -r entry; do
    [[ -z "$entry" ]] && continue
    model="${entry%@*}"; rev=""
    [[ "$entry" == *"@"* ]] && rev="--revision ${entry#*@}"
    run "hf download '$model' $rev --cache-dir '$USB_DIR/hf/hub'"
  done < <(extract_block 'BUNDLE-MODELS-START' 'BUNDLE-MODELS-END')
fi

# ── 3. Python wheels (aarch64 cp312, installed offline in the sandbox) ──────
if should wheels; then
  say "Python wheels (pip download → $USB_DIR/wheels)"
  while IFS= read -r pkg; do
    [[ -z "$pkg" ]] && continue
    run "pip download '$pkg' --platform '$PIP_PLATFORM' --python-version '$PY_VERSION' --only-binary=:all: -d '$USB_DIR/wheels'"
  done < <(extract_block 'BUNDLE-WHEELS-START' 'BUNDLE-WHEELS-END')
fi

# ── 4. Installers & source (linux-arm64) ────────────────────────────────────
if should installers; then
  say "Installers & source"
  dl() { local url="$1" out="$2"; [[ -s "$USB_DIR/installers/$out" ]] && { skip "$out exists"; return; }; run "curl -fsSL '$url' -o '$USB_DIR/installers/$out'"; }
  dl "https://www.nvidia.com/nemoclaw.sh" "nemoclaw.sh"
  dl "https://raw.githubusercontent.com/NVIDIA/NemoClaw/refs/heads/main/uninstall.sh" "uninstall.sh"
  dl "https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh" "openshell-install.sh"
  say "  (Also grab from GitHub Releases, by hand: OpenShell 0.0.116 linux-arm64 asset, Node.js 22.19+ linux-arm64 tarball)"
  if [[ ! -e "$USB_DIR/installers/nemoclaw.bundle" ]]; then
    run "git clone --depth 1 https://github.com/NVIDIA/NemoClaw.git '$USB_DIR/installers/NemoClaw.src'"
    run "git -C '$USB_DIR/installers/NemoClaw.src' bundle create '$USB_DIR/installers/nemoclaw.bundle' --all"
  else skip "nemoclaw.bundle exists"; fi
fi

# ── 5. Checksums + loader ───────────────────────────────────────────────────
say "Checksums (SHA256SUMS at USB root)"
SHA="sha256sum"; command -v sha256sum >/dev/null 2>&1 || SHA="shasum -a 256"
run "cd '$USB_DIR' && find images wheels installers -type f 2>/dev/null | sort | xargs -r $SHA > SHA256SUMS || true"

say "Done. Next: scripts/verify-bundle.sh '$USB_DIR'"
[[ "$DRY_RUN" == 1 ]] && say "(dry-run: nothing downloaded)"
