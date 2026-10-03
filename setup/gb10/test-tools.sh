#!/usr/bin/env bash
# Test tool-calling + reasoning on a vLLM model. Defaults to nemotron on :8001.
# Usage:   ./test-tools.sh
#   qwen:  MODEL=qwen3.6 PORT=8000 ./test-tools.sh
# Env: HOST(127.0.0.1) PORT(8001) MODEL(nemotron) VLLM_API_KEY(optional)
set -euo pipefail

HOST="${HOST:-127.0.0.1}"; PORT="${PORT:-8001}"; MODEL="${MODEL:-nemotron}"
API_KEY="${VLLM_API_KEY:-}"
AUTH=(); [ -n "$API_KEY" ] && AUTH=(-H "Authorization: Bearer $API_KEY")
URL="http://$HOST:$PORT/v1/chat/completions"

command -v jq >/dev/null || { echo "jq required (sudo apt install -y jq)"; exit 1; }
curl -sS -m5 "${AUTH[@]}" -o /dev/null "http://$HOST:$PORT/v1/models" 2>/dev/null \
  || { echo "ERROR: $MODEL not reachable at $HOST:$PORT — is the server up?"; exit 1; }

echo "== tool-calling + reasoning test: $MODEL @ $HOST:$PORT =="
resp=$(curl -sS "${AUTH[@]}" "$URL" -H 'content-type: application/json' -d "{
  \"model\":\"$MODEL\",
  \"messages\":[{\"role\":\"user\",\"content\":\"What is the weather in Boston? Use the tool.\"}],
  \"tools\":[{\"type\":\"function\",\"function\":{\"name\":\"get_weather\",\"description\":\"weather for a city\",\"parameters\":{\"type\":\"object\",\"properties\":{\"city\":{\"type\":\"string\"}},\"required\":[\"city\"]}}}],
  \"tool_choice\":\"auto\",\"max_tokens\":1024
}")

echo "$resp" | jq '{finish:.choices[0].finish_reason,
                     reasoning:.choices[0].message.reasoning_content,
                     tool_calls:.choices[0].message.tool_calls}' 2>/dev/null \
  || { echo "non-JSON response:"; echo "$resp" | head -c 500; echo; exit 1; }

finish=$(echo "$resp" | jq -r '.choices[0].finish_reason // "none"')
ntools=$(echo "$resp" | jq '(.choices[0].message.tool_calls // []) | length')
hasreason=$(echo "$resp" | jq -r 'if (.choices[0].message.reasoning_content // "") != "" then "yes" else "no" end')
echo ""
echo "  finish_reason=$finish | tool_calls=$ntools | reasoning=$hasreason"
if [ "$finish" = "tool_calls" ] && [ "${ntools:-0}" -ge 1 ]; then
  echo "  ✅ PASS — tool calling works (reasoning=$hasreason)"
else
  echo "  ❌ FAIL — expected finish=tool_calls with >=1 tool_call. Check: docker logs vllm-$MODEL"
  exit 1
fi
