#!/usr/bin/env bash
# Serve Qwen3.6-35B-A3B-NVFP4 on vLLM, wait for load, then ping it.
# Run on the GB10 as a user in the docker group (shiv). Daemon (root) reads dell's weights.
#
# Env:
#   BIND_HOST      127.0.0.1 (default, loopback only) | 0.0.0.0 to expose on the LAN
#   VLLM_API_KEY   if set, clients must send 'Authorization: Bearer <key>' (recommended on shared wifi)
#   GPU_MEM_UTIL   0.30     MAX_MODEL_LEN 16384
set -euo pipefail

NAME=vllm-qwen
PORT=8000
SERVED=qwen3.6
MODEL_DIR=/home/dell/nvidia-models/Qwen3.6-35B-A3B-NVFP4
IMAGE=nvcr.io/nvidia/vllm:26.05.post1-py3
UTIL="${GPU_MEM_UTIL:-0.30}"
MAXLEN="${MAX_MODEL_LEN:-16384}"
BIND_HOST="${BIND_HOST:-127.0.0.1}"
API_KEY="${VLLM_API_KEY:-}"

echo "== (re)starting $NAME on $BIND_HOST:$PORT (util=$UTIL, max_len=$MAXLEN, auth=$([ -n "$API_KEY" ] && echo on || echo off)) =="
docker rm -f "$NAME" 2>/dev/null || true
docker run -d --name "$NAME" --gpus all --restart unless-stopped -p "$BIND_HOST:$PORT:$PORT" \
  -v "$MODEL_DIR":/model:ro \
  "$IMAGE" \
  vllm serve /model --served-model-name "$SERVED" --port "$PORT" \
    --max-model-len "$MAXLEN" --gpu-memory-utilization "$UTIL" --trust-remote-code \
    ${API_KEY:+--api-key "$API_KEY"}
# If it errors that `vllm` isn't a command, drop the leading `vllm` (image entrypoint sets it).

AUTH=(); [ -n "$API_KEY" ] && AUTH=(-H "Authorization: Bearer $API_KEY")

echo "== waiting for $SERVED to load (first load = a few min) =="
for i in $(seq 1 180); do
  if curl -sS -m3 "${AUTH[@]}" -o /dev/null "http://127.0.0.1:$PORT/v1/models" 2>/dev/null; then
    echo "  ready after ~$((i*5))s"; break
  fi
  if ! docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
    echo "  ERROR: $NAME exited while loading — last logs:"; docker logs --tail 25 "$NAME" 2>&1 | tr -d '\r'; exit 1
  fi
  [ "$i" = 180 ] && { echo "  TIMEOUT after 15m — check: docker logs $NAME"; exit 1; }
  sleep 5
done

echo "== models =="
curl -s "${AUTH[@]}" "http://127.0.0.1:$PORT/v1/models" | (command -v jq >/dev/null && jq -r '.data[].id' || cat)

echo "== ping $SERVED (thinking off for a clean answer) =="
curl -s "${AUTH[@]}" "http://127.0.0.1:$PORT/v1/chat/completions" -H 'content-type: application/json' \
  -d "{\"model\":\"$SERVED\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: $SERVED-ok\"}],\"max_tokens\":32,\"chat_template_kwargs\":{\"enable_thinking\":false}}" \
  | (command -v jq >/dev/null && jq -r '.choices[0].message.content' || cat)
echo ""

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ "$BIND_HOST" = "0.0.0.0" ]; then
  echo "== $SERVED live — reachable at http://$IP:$PORT/v1 (LAN) =="
  [ -z "$API_KEY" ] && echo "   ⚠ NO AUTH: anyone on this network can use it. Set VLLM_API_KEY to require a token."
else
  echo "== $SERVED live at http://127.0.0.1:$PORT/v1 (loopback only; set BIND_HOST=0.0.0.0 to expose) =="
fi
