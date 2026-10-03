#!/usr/bin/env bash
# verify-bundle.sh — sanity-check the USB before we leave: presence, sizes, checksums.
# Cross-references configs/models.md so a forgotten model/image is caught.
# Usage: scripts/verify-bundle.sh [USB_DIR] [--dry-run] [--help]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
MODELS_MD="$ROOT/configs/models.md"
[[ -f "$ROOT/.env" ]] && set -a && . "$ROOT/.env" && set +a || true

DRY_RUN=0; USB_DIR="${USB_DIR:-$ROOT/bundle}"
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --*) echo "unknown arg: $a (try --help)" >&2; exit 2 ;;
    *) USB_DIR="$a" ;;
  esac
done

pass=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; pass=$((pass+1)); }
nope() { printf '  \033[31m✗\033[0m %s\n' "$*"; fail=$((fail+1)); }
hdr()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
hsize(){ du -h "$1" 2>/dev/null | awk '{print $1}'; }

extract_block() {
  awk -v s="$1" -v e="$2" '$0 ~ s {grab=1; next} $0 ~ e {grab=0} grab' "$MODELS_MD" | sed 's/#.*//' | awk 'NF'
}

if [[ "$DRY_RUN" == 1 ]]; then
  echo "[dry-run] would verify $USB_DIR: dir layout, each image/model/wheel from models.md, SHA256SUMS"
  exit 0
fi

echo "Verifying bundle at: $USB_DIR"
[[ -d "$USB_DIR" ]] || { nope "USB_DIR '$USB_DIR' not found"; exit 1; }

hdr "Directory layout"
for d in images hf/hub wheels installers; do
  [[ -d "$USB_DIR/$d" ]] && ok "$d/ ($(hsize "$USB_DIR/$d"))" || nope "$d/ missing"
done

hdr "Container images"
while IFS= read -r img; do
  [[ -z "$img" ]] && continue
  safe="$(echo "$img" | tr '/:@' '___')"
  if ls "$USB_DIR"/images/"${safe}".tar* >/dev/null 2>&1; then
    f="$(ls "$USB_DIR"/images/"${safe}".tar* | head -1)"; ok "$img → $(basename "$f") ($(hsize "$f"))"
  else nope "$img — no saved tarball in images/"; fi
done < <(extract_block 'BUNDLE-IMAGES-START' 'BUNDLE-IMAGES-END')

hdr "Model weights"
if [[ -d "$USB_DIR/hf/hub" ]]; then
  while IFS= read -r entry; do
    [[ -z "$entry" ]] && continue
    model="${entry%@*}"; key="models--$(echo "$model" | tr '/' '-')"
    if ls -d "$USB_DIR"/hf/hub/"$key"* >/dev/null 2>&1; then
      ok "$model ($(hsize "$(ls -d "$USB_DIR"/hf/hub/"$key"* | head -1)"))"
    else nope "$model — not in hf/hub (expected dir $key)"; fi
  done < <(extract_block 'BUNDLE-MODELS-START' 'BUNDLE-MODELS-END')
fi

hdr "Python wheels"
n_wheels="$(ls "$USB_DIR"/wheels/*.whl 2>/dev/null | wc -l | tr -d ' ')"
(( n_wheels > 0 )) && ok "$n_wheels wheel(s) present" || nope "no .whl files in wheels/"

hdr "Installers"
for f in nemoclaw.sh openshell-install.sh nemoclaw.bundle; do
  [[ -s "$USB_DIR/installers/$f" ]] && ok "$f ($(hsize "$USB_DIR/installers/$f"))" || nope "installers/$f missing"
done
[[ -s "$USB_DIR/installers/uninstall.sh" ]] && ok "uninstall.sh" || printf '  \033[33m!\033[0m uninstall.sh missing (optional)\n'

hdr "Checksums (SHA256SUMS)"
if [[ -f "$USB_DIR/SHA256SUMS" ]]; then
  SHA="sha256sum"; command -v sha256sum >/dev/null 2>&1 || SHA="shasum -a 256"
  if ( cd "$USB_DIR" && $SHA -c SHA256SUMS >/tmp/_verify.$$ 2>&1 ); then
    ok "all $(wc -l < "$USB_DIR/SHA256SUMS" | tr -d ' ') checksums match"
  else
    nope "checksum mismatch — see failures:"; grep -i 'FAILED' /tmp/_verify.$$ | sed 's/^/     /' || true
  fi
  rm -f /tmp/_verify.$$
else
  nope "SHA256SUMS missing — re-run bundle-offline.sh"
fi

hdr "Total"
echo "  bundle size: $(hsize "$USB_DIR")"
printf "  %d ok · %d problems\n" "$pass" "$fail"
(( fail > 0 )) && { echo "  → fix before leaving. Secrets (NGC/HF/Telegram) are NOT on the USB — bring them in a password manager."; exit 1; }
echo "  → bundle looks complete. Don't forget: NGC_API_KEY, HF_TOKEN, TELEGRAM_BOT_TOKEN in a password manager (not the USB)."
