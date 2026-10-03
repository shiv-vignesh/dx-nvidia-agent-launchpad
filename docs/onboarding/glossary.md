# Glossary

*Every term in the stack, one line each. ⚠ = not confirmed in `docs-raw/`.*

## The four products

| Term | Meaning |
|---|---|
| **OpenClaw** | The agent runtime: the loop, tools, skills, memory, channels, TUI/Web UI. Pinned `v2026.9.7`. |
| **OpenShell** | The cage: sandbox (Landlock + seccomp + netns) **+** an L7 gateway proxy + policy + credential store. Pinned `0.0.116` (exact, required by NemoClaw). |
| **NemoClaw** | NVIDIA's host CLI + versioned blueprint + in-sandbox plugin; `nemoclaw onboard` installs and wires everything. |
| **vLLM** | The model server on the host (`:8000`): chat template, decode, tool-call parsing, OpenAI-compatible API. |

## Agent concepts

| Term | Meaning |
|---|---|
| **Agent loop** | call model → if tool_call, run it, append result → call again → until a final answer / turn limit / timeout. |
| **Tool call** | Text the model generates in a trained format, parsed by the server into `message.tool_calls[]`. Nothing runs inside vLLM. |
| **Tool / skill** | Tool = a function the model may call (exec, files, web). Skill = a reusable procedure + prompt snippet, loaded on demand. |
| **Channel** | How users reach the agent: TUI, Control UI (`:18789`), Telegram/Slack/Discord. |
| **Memory / compaction** | Transcripts + durable facts the runtime reads into the prompt; compaction summarizes old turns when context fills. |
| **MCP** | Model Context Protocol — external tool providers over a standard protocol; NemoClaw "managed MCP" = authenticated HTTPS only. |

## Inference & serving

| Term | Meaning |
|---|---|
| **`inference.local`** | Virtual URL the agent always calls (`https://inference.local/v1`); the gateway rewrites it to the real backend. Never a real server. |
| **Chat template** | Jinja in `tokenizer_config.json` (or `--chat-template`) that serializes `tools` + messages into prompt tokens. |
| **`--tool-call-parser`** | vLLM flag that extracts tool calls from generated text; must match the model's wire format (`hermes`, `llama3_json`, `qwen3_xml`, `pythonic`, …). |
| **`--reasoning-parser`** | Routes a reasoning model's thoughts into `message.reasoning` instead of `content`/args. |
| **`--enable-auto-tool-choice`** | Required for `tool_choice:"auto"`. |
| **`tool_choice`** | `auto` (extract from free text, may be malformed) vs `required`/named (constrained decoding, guaranteed parseable). |
| **Constrained decoding** | FSM/grammar-guided generation guaranteeing a parseable call; first use pays a compile. |
| **Prefix caching** | KV-cache reuse of a shared prompt prefix — the thing that makes repeated agent prefills cheap. |
| **TTFT** | Time to first token ≈ prefill time. Agent latency is TTFT-dominated because every turn re-sends growing context. |

## Models

| Term | Meaning |
|---|---|
| **NVFP4** | NVIDIA 4-bit float checkpoint; runs natively on Blackwell (needs compute capability ≥ 12.1 on Spark). |
| **A3B** | MoE with ~3B *active* parameters/token → decodes much faster than a dense model of similar total size. |
| **MTP** | Multi-token prediction (speculative-style decode speedup in some serving profiles). |
| **FP8 KV** | 8-bit KV cache — saves memory for long contexts. |
| **`max_model_len` / `max-num-seqs` / `gpu-memory-utilization`** | Context length / concurrent sequences / fraction of memory vLLM may use. |

## OpenShell / policy

| Term | Meaning |
|---|---|
| **Gateway** | Host process (`:8080`) = L7 proxy + policy engine + credential store. Every egress and inference call crosses it. |
| **L7 proxy** | Inspects egress at host/port/binary/HTTP-method/path level; TLS terminated so rules apply to `CONNECT`. |
| **Isolation layers** | Filesystem (locked), Network (hot-reload), Process (locked), Inference (hot-reload). |
| **Landlock / seccomp / netns** | Kernel filesystem confinement / syscall filtering / network namespace — the sandbox walls. |
| **Policy tier** | Restricted / **Balanced** (default) / Open / Personal — bundles of presets. |
| **Preset** | A named host group (e.g. `huggingface`, `npm`, `pypi`, `brave`) added to the allowlist. |
| **`openshell term`** | TUI for live allow/deny: `r` Network Rules, `a` approve, `x` reject, `A` approve all — **session-only**. |
| **Credential placeholder** | What the sandbox sees instead of a real key; the gateway swaps in the real value at egress. |

## NemoClaw lifecycle

| Term | Meaning |
|---|---|
| **Blueprint** | Versioned YAML recipe: sandbox image, policies, presets, inference profiles. |
| **`nemoclaw onboard`** | The wizard: readiness probe → provider/model → route → sandbox → connect. `--resume`, `--name`, `--recreate-sandbox`, `--fresh`. |
| **`NEMOCLAW_PROVIDER`** | `install-vllm` (managed) · `vllm` (existing server you started) · **⚠** Ollama/other not documented. |
| **`nemoclaw-vllm`** | The managed vLLM Docker container on the host. |
| **DGX Spark detection** | NemoClaw decides Spark vs generic arm64 from product+firmware+arch+GPU — **⚠ the Dell Pro Max may fall back to generic.** |
| **Express Install** | One-shot path offered only when the box is detected as DGX Spark / Station. |

## Ports (memorize)

| Port | Service |
|---|---|
| `8000` | vLLM (`nemoclaw-vllm`) |
| `8080` | OpenShell gateway |
| `18789` | OpenClaw Control UI / dashboard (open via `127.0.0.1`, not `localhost`) |
| **⚠ `11434`** | Ollama default — from the brief, **not** in docs-raw |
