#!/usr/bin/env bash
# Download one model's weights DIRECTLY from HF to the GB10 (no gdrive round-trip).
# Resumable, parallel (hf_transfer). Token comes from ~/shiftguard-secrets.env — NEVER hardcoded.
#
# Usage: download-model.sh <qwen|nemotron|glm>
# Dest:  /home/shiv/models/<name>  (flat dir → vLLM serves it via --model <dir>)
set -euo pipefail

KEY="${1:?usage: download-model.sh <qwen|nemotron|glm>}"
case "$KEY" in
  qwen)     REPO="nvidia/Qwen3.6-35B-A3B-NVFP4";                   NAME="qwen3.6-35b-a3b-nvfp4" ;;
  nemotron) REPO="nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4"; NAME="nemotron-3-super-120b-a12b-nvfp4" ;;
  glm)      REPO="nvidia/GLM-5.2-NVFP4";                           NAME="glm-5.2-nvfp4" ;;
  *) echo "unknown model key '$KEY' (want: qwen|nemotron|glm)"; exit 2 ;;
esac
DEST="${MODELS_ROOT:-$HOME/models}/$NAME"

# HF token from the secrets file (outside the repo mirror); never baked into tracked files
[ -f "$HOME/shiftguard-secrets.env" ] && . "$HOME/shiftguard-secrets.env"
: "${HF_TOKEN:?HF_TOKEN not set — add 'export HF_TOKEN=hf_...' to ~/shiftguard-secrets.env}"
export HF_TOKEN HF_HUB_ENABLE_HF_TRANSFER=1

# hf CLI in a dedicated venv (system python is PEP-668 externally-managed)
VENV="$HOME/.venvs/hf"
if [ ! -x "$VENV/bin/hf" ]; then
  echo "== creating hf download venv =="
  python3 -m venv "$VENV"
  "$VENV/bin/pip" -q install -U "huggingface_hub[cli,hf_transfer]"
fi

echo "== checking repo size =="
"$VENV/bin/python" - "$REPO" <<'PY' || true
import sys; from huggingface_hub import HfApi
r=sys.argv[1]
try:
    files=HfApi().list_repo_tree(repo_id=r, recursive=True)
    gb=sum(f.size for f in files if getattr(f,"size",None))/1024**3
    print(f"  {r}: {gb:.1f} GB")
except Exception as e: print(f"  (size check failed: {e})")
PY

df -h "${MODELS_ROOT:-$HOME}" | awk 'NR==2{print "  free on target: "$4}'
mkdir -p "$DEST"
echo "== downloading $REPO -> $DEST (resumable) =="
"$VENV/bin/hf" download "$REPO" --local-dir "$DEST"
echo "== done: $(du -sh "$DEST" 2>/dev/null | cut -f1) at $DEST =="
echo "point the registry's upstream_model at: $DEST"