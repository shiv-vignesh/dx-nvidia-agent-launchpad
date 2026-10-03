# Model registry — one endpoint, swappable backend

Our product's inference seam. The agent (OpenClaw) and the stack (OpenShell `inference.local`) call **one**
OpenAI-compatible endpoint — this router. Each request names a *logical* model; the router looks it up in
[`registry.json`](registry.json), rewrites it to the backend's real model id, and forwards it. **Swap a model's
backend by editing one line — the agent never changes.** That's the "swappable by the inference software
(ollama / vllm / colibri)" requirement, made concrete.

```
agent / stack  ──►  router.py (:9000)  ──►  ollama  (:11434)   qwen2.5:7b        (Mac, tonight)
                     reads registry.json     vllm    (:8000)    Qwen3.6-35B       (GB10, tomorrow)
                                             colibri (:8001)    GLM-5.2 int4      (frontier MoE)
```

## Why a router instead of pointing the agent straight at a backend

| Benefit | How |
|---|---|
| **Swap engine without touching the agent** | ollama → vLLM → colibri is a one-line edit in `registry.json` |
| **Stable logical names** | agent asks for `qwen2.5:7b`; the registry decides *where* that resolves |
| **Matches the stack's own design** | OpenShell already routes `inference.local` → a provider; this is that seam, owned by us |
| **Demo-friendly** | the router prints every `model → backend` decision; great for the "it's local" story |

## Run

```bash
python3 registry/router.py                      # serves on 127.0.0.1:9000 (from registry.json)
# in another shell:
curl -s localhost:9000/v1/models | jq           # what the agent sees
curl -s localhost:9000/registry | jq            # the full active mapping
curl -s localhost:9000/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"hi"}]}'
```

Env: `REGISTRY_FILE` (default `registry/registry.json`), `REGISTRY_PORT` (overrides config).

## Swapping a backend (the whole point)

In `registry.json`, change one line:

```jsonc
"qwen2.5:7b": { "backend": "ollama", "upstream_model": "qwen2.5:7b" }
//            ↓ later, on the GB10, point the SAME name at vLLM — agent code unchanged
"qwen2.5:7b": { "backend": "vllm",   "upstream_model": "nvidia/Qwen3.6-35B-A3B-NVFP4" }
```

`registry.json` is re-read on every request, so edits take effect immediately — no router restart, no agent change.

## Backends (all OpenAI-compatible)

| Backend | Endpoint | Notes |
|---|---|---|
| `ollama` | `:11434/v1` | local dev model (`qwen2.5:7b`); `api_key` is a dummy (`ollama-local`) |
| `vllm` | `:8000/v1` | the GB10 path; NemoClaw-managed `nemoclaw-vllm` |
| `colibri` | `:8001/v1` | `coli serve` exposes OpenAI-compat (default :8000 — we use :8001 to avoid clashing with vLLM) |

## Limits (honest)

- **Non-streaming** passthrough (buffers the upstream response, then relays). Fine for warm-up/eval; add SSE relay if a demo needs token streaming.
- Routes `/v1/chat/completions` and `/v1/models` only — the surface the agent loop uses.
- No auth on the router itself; it's loopback-only by default. Behind OpenShell tomorrow, the gateway is the auth/policy layer.
