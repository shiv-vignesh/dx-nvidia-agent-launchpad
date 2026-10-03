#!/usr/bin/env bash
# run.sh — complex warm-up: the REAL stack runtime (OpenClaw) runs a multi-file triage task
# THROUGH our swappable model registry, served by Ollama qwen2.5:7b. Then it demonstrates a
# live backend swap (edit one line → routing changes, agent untouched).
#
#   OpenClaw (registry/qwen2.5:7b) ──► registry router :9000 ──► ollama :11434 ──► qwen2.5:7b
#
# Mirrors the hackathon "GPU failed-job triage" idea, but the point is the PLUMBING:
# agent runtime + model registry + local inference, chained and swappable.
set -euo pipefail

export PATH="/opt/homebrew/opt/ollama/bin:/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
REGISTRY="$ROOT/registry/registry.json"
ROUTER_LOG="/tmp/registry-router.log"
DATA="$HERE/sample-data"

b(){ printf '\n\033[1m%s\033[0m\n' "$*"; }

up(){ curl -sS -m2 -o /dev/null "$1" 2>/dev/null; }

b "1. Bring up Ollama + the registry router"
up http://localhost:11434/api/tags || { echo "  starting ollama..."; nohup ollama serve >/tmp/ollama.log 2>&1 & sleep 3; }
pkill -f "registry/router.py" 2>/dev/null || true; sleep 0.5
nohup python3 "$ROOT/registry/router.py" >"$ROUTER_LOG" 2>&1 & sleep 1.5
echo "  ollama=$(curl -s -o /dev/null -w '%{http_code}' localhost:11434/api/tags)  router=$(curl -s -o /dev/null -w '%{http_code}' localhost:9000/healthz)"

b "2. Ensure OpenClaw has the 'registry' provider (points at our router)"
if ! openclaw config get models.providers.registry.baseUrl >/dev/null 2>&1; then
  cat > /tmp/registry-provider.json5 <<'EOF'
{ models: { providers: { registry: {
  baseUrl: "http://127.0.0.1:9000/v1", apiKey: "placeholder", api: "openai-completions",
  models: [ { id: "qwen2.5:7b", name: "qwen2.5:7b", input: ["text"] } ] } } } }
EOF
  openclaw config patch --file /tmp/registry-provider.json5 | head -1
else echo "  registry provider already configured"; fi

b "3. The registry mapping (what's swappable)"
curl -s localhost:9000/v1/models | (jq -r '.data[] | "  \(.id)  ->  \(.owned_by)"' 2>/dev/null || cat)

b "4. OpenClaw agent triages the logs — via registry/qwen2.5:7b (through our router → ollama)"
echo "  (data: $(ls "$DATA" | tr '\n' ' '))"
echo "  ---------------------------------------------------------------"
openclaw agent exec \
  --model registry/qwen2.5:7b --local-model-lean --thinking off --cwd "$DATA" --timeout 180 \
  "Read every *.log file in this directory. For each, output one line: '<file>: <OOM|NCCL-timeout|user-bug|other> - <5-word reason>'. Then one final line recommending which to retry vs escalate." \
  2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -vE '\[(provider-transport-fetch|session-sqlite|state/agent-db|agent/embedded|agents/agent-command|memory)\]' \
  | sed 's/^/  /'
echo "  ---------------------------------------------------------------"
echo "  (note: a 7B model often thrashes across 38 tools — that's the 'fewer tools, bigger model' lesson,"
echo "   not a plumbing failure. The GB10's 35B is the fix. What we're proving here is the CHAIN below.)"

b "5. PROOF the inference went through our registry (not straight to ollama)"
n=$(grep -c '\[route\]' "$ROUTER_LOG" 2>/dev/null || echo 0)
echo "  $n inference call(s) transited the registry this run — sample:"
grep '\[route\]' "$ROUTER_LOG" | head -1 | sed 's/^/    /' || echo "  (no route logged)"

b "6. Live backend SWAP demo — edit one line, routing changes, agent code untouched"
cp "$REGISTRY" "$REGISTRY.bak"; trap 'mv -f "$REGISTRY.bak" "$REGISTRY" 2>/dev/null || true' EXIT
# repoint qwen2.5:7b from ollama -> vllm (vLLM isn't running here, so we expect a graceful 502)
sed -i '' 's#"qwen2.5:7b":  { "backend": "ollama",  "upstream_model": "qwen2.5:7b" }#"qwen2.5:7b":  { "backend": "vllm",    "upstream_model": "nvidia/Qwen3.6-35B-A3B-NVFP4" }#' "$REGISTRY"
echo "  edited registry.json: qwen2.5:7b now -> vllm (no router restart, no agent change)"
echo "  same request now routes to vLLM:"
curl -s localhost:9000/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"hi"}]}' | (jq -c 2>/dev/null || cat) | sed 's/^/    /'
mv -f "$REGISTRY.bak" "$REGISTRY"; trap - EXIT
echo "  reverted registry.json -> ollama."
echo "  => On the GB10 this same edit points the agent at Qwen3.6-35B on vLLM. That's the whole trick."

b "Done."
