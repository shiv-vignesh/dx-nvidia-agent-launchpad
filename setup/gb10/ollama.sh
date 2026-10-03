#!/usr/bin/env bash
# Ollama on the GB10 — a fast local inference backend for TESTING the agent while the
# vLLM/NemoClaw image+weights finish downloading. The registry swaps to vLLM later.
# Idempotent. Needs passwordless sudo (install.sh sets up a systemd service).
#
# NOTE: the GB10 GPU is Blackwell (sm_121); Ollama's bundled CUDA may not support it yet and
# could fall back to CPU. Fine for plumbing/tests (7B on CPU is slow but works); vLLM (NVFP4,
# GPU) remains the real demo path.
set -euo pipefail
MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"

if command -v ollama >/dev/null 2>&1; then
  echo "ollama present: $(ollama --version 2>&1 | head -1)"
else
  echo "== installing ollama =="
  curl -fsSL https://ollama.com/install.sh | sh
fi

echo "== ensure server up =="
if curl -sS -m2 -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null; then
  echo "already serving on :11434"
else
  sudo systemctl enable --now ollama 2>/dev/null || { nohup ollama serve >/tmp/ollama.log 2>&1 & }
  for _ in $(seq 1 30); do sleep 1; curl -sS -m2 -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null && break; done
fi
curl -sS -m3 -o /dev/null -w "  :11434 http=%{http_code}\n" http://127.0.0.1:11434/api/tags

echo "== pull $MODEL =="
ollama list 2>/dev/null | grep -q "${MODEL%%:*}" && echo "already pulled" || ollama pull "$MODEL"

echo "== smoke test (OpenAI-compatible) =="
curl -sS http://127.0.0.1:11434/v1/chat/completions -H 'content-type: application/json' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"reply with exactly: ollama-ok\"}],\"stream\":false}" \
  | (command -v jq >/dev/null && jq -r '.choices[0].message.content' || head -c 200)
echo ""
echo "== GPU or CPU? =="
ollama ps 2>/dev/null || true
echo "== ollama ready on :11434, model=$MODEL =="
