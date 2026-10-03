# 02 · Local inference

*This is our home turf. The agent calls `inference.local`; the gateway routes it to **a local provider you pick
at onboarding.** This page covers the providers, the responsibility split, and which models fit 128 GB.*

Sources: `docs-raw/Agent onboarding … GB10.md` Parts 3A–3B. **⚠ markers** flag claims the source docs do **not**
back — verify at the venue (see [sources/INDEX.md](../sources/INDEX.md) and the open-questions list).

## The three providers

| Provider | How NemoClaw uses it | Default port | Status in our docs |
|---|---|---|---|
| **vLLM (managed)** | `NEMOCLAW_PROVIDER=install-vllm` — NemoClaw pulls the image + weights and runs `nemoclaw-vllm` for you | `:8000` | ✅ **Documented default path.** Qwen3.6-35B-A3B-NVFP4 |
| **vLLM (existing)** | `NEMOCLAW_PROVIDER=vllm` — you start vLLM yourself, NemoClaw points the route at it | `:8000` | ✅ Documented. The offline/self-serve escape hatch |
| **Ollama** | **⚠ unverified** — your brief says the wizard detects/starts it on `:11434` and treats it as default. The source docs mention Ollama only as a capability column, never a wizard step or port 11434 | **⚠ `:11434`** | ⚠ **Unverified against docs-raw.** Confirm at venue |
| **Other OpenAI-compatible endpoint** | **⚠ unverified** — plausible generic path; not described in docs-raw | — | ⚠ Unverified |

> **Why the ⚠ on Ollama:** the deep-dive doc is vLLM-only. Ollama appears twice — "Ollama parses tool calls
> internally" and "chat template built into the model package" — i.e. it *can* serve tool-calling models, but the
> doc never shows it as a NemoClaw provider, never names port 11434, and the default model + serving profiles are
> all vLLM. Treat Ollama as a real option to **test**, not a documented fact. `preflight.sh` checks 11434 anyway.

### What the agent sees either way

```
OpenClaw (sandbox)  ──POST https://inference.local/v1/chat/completions──►  OpenShell gateway
                                                                                │  rewrites route + injects key
                                                                                ▼
                                            vLLM :8000   (or ⚠ Ollama :11434, or other endpoint)
```
Swap the provider → the agent doesn't notice. That indirection is also our **local-first proof**: point the route
only at a box-local server and the agent *physically cannot* reach a cloud model.
*(Scheme note: the deep-dive uses `https://inference.local`; `01-Getting-Started.md` shows `http://`. Use **https**.)*

## Who owns what — the responsibility matrix

● = owns it.

| Responsibility | vLLM / Ollama | OpenClaw | OpenShell | NemoClaw |
|---|:--:|:--:|:--:|:--:|
| Model loading (weights, quant, KV cache) | ● | — | — | pulls image+weights, starts container |
| Chat template | ● *(Ollama: built into the model package)* | sends `chat_template_kwargs` (thinking on/off) | — | registry supplies serve args |
| Tool-call parsing | ● `--tool-call-parser` *(Ollama: internal)* | consumes structured `tool_calls` | — | picks parser per model |
| OpenAI-compatible API | ● `/v1/chat/completions`, `/v1/models` | client | exposes `inference.local` in front | — |
| Agent loop | — | ● queue, prompt build, streaming, compaction | — | plugin injects context per turn |
| Tool execution | — | ● runs tools as sandbox processes; exec approvals | enforces what they reach | — |
| Sandboxing | — | optional own backends | ● Landlock + seccomp + netns | blueprint defines image/policy |
| Network policy | — | app-level | ● deny-by-default L7 proxy, live approvals | tiers + presets |
| Credential injection | — | sees placeholders only | ● stores secrets, rewrites `Authorization`/URL at egress | registers creds at onboarding |
| Inference routing | is the endpoint | calls `inference.local/v1` | ● resolves route → provider+model | validates, sets route |
| Channels | — | ● TUI, Control UI, Telegram/Slack/Discord | gates channel egress | collects tokens, adds presets |

**Reading for an inference engineer:** your knowledge covers the entire first column. Everything new is the loop
(OpenClaw) and the cage (OpenShell). NemoClaw just wires them.

## What makes a HF model good at tool calling

| Property | Why it matters |
|---|---|
| **Trained wire format + round-tripping template** | Template must render `tools`, prior `tool_calls`, and `tool`-role messages. A template that drops tool history **breaks turn 2, not turn 1.** |
| **A parser exists for that format** | Check vLLM's parser list (`hermes`, `llama3_json`, `qwen3_xml`, `openai`, `step3p5`, `pythonic`, …) or `--tool-call-parser hf` if the checkpoint ships a `response_template`. |
| **Reasoning is separable** | Reasoning models need `--reasoning-parser` so thoughts land in `message.reasoning`. Reasoning tokens count against `max_tokens` — NemoClaw's Nemotron note: **send ≥1,024** or you get empty output with `finish_reason=length`. |
| **Parallel calls + schema fidelity** | Llama 3 can't do parallel calls (per vLLM); prefer families documented as parallel-capable. |
| **Decode economics on GB10** | Unified memory is big but **bandwidth-bound**. Low-active-param MoE ("A3B" ≈ 3B active) decodes far faster than a dense model of similar size. Agent loops are prefill-heavy → **prefix caching > peak tok/s.** |
| **Native Blackwell quant** | NVFP4 checkpoints run natively; registry requires compute capability ≥ 12.1 on DGX Spark. |

## Candidates that fit 128 GB

Sizes marked ≈ are the author's estimates (params × bytes), **not** doc figures. Leave headroom — oversized
checkpoints or long contexts on Spark can cause `NV_ERR_NO_MEMORY`, SSH loss, or a host freeze under agent load.

| Model (HF id) | Weights | Profile on Spark | Verdict |
|---|---|---|---|
| **`nvidia/Qwen3.6-35B-A3B-NVFP4`** | ≈20 GB *(not stated)* | **Default.** ≥64 GB: 262,144 ctx, 4 seqs, 8,192 batched, util 0.4, async sched | **Start here.** Validated across NemoClaw/OpenShell/Hermes playbooks; A3B decodes fast |
| `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4` | 21.56 GB | Opt-in/Experimental: 65,536 ctx, 1 seq, util 0.65, FP8 KV, 1-tok MTP; ~102 tok/s | **Backup / NVIDIA-native story.** 1 seq → compaction queues behind the active turn |
| `Inferact/Muse-Glimmer-30B-NVFP4-W4A4` | 25.45 GB | Opt-in/Exp: 32,768 ctx, 1 seq, util 0.75, **nightly** vLLM image | Skip unless needed; nightly image, shortest context |
| `Qwen/Qwen3.6-27B-FP8` | ≈27 GB | Override `NEMOCLAW_VLLM_MODEL=qwen3.6-27b` | Dense → all 27B active/token → slower decode than A3B |
| `nvidia/NVIDIA-Nemotron-3-Nano-4B-FP8` | ≈5 GB | Generic-Linux default | **Smoke-test only**; weak at multi-step planning |
| `NousResearch/Hermes-3-Llama-3.1-8B` | ≈16 GB BF16 | Not in registry: run yourself + `NEMOCLAW_PROVIDER=vllm`; parser `hermes` | Canonical tool-calling example; older/small for agent work |
| `deepseek-ai/DeepSeek-R1-Distill-Llama-70B` | ≈141 GB BF16 | Listed for Spark, gated | **Avoid** — BF16 exceeds 128 GB unless quantized |

**Chosen tags & sizes live in [`../../configs/models.md`](../../configs/models.md)** — the single place scripts read from.

> **Two naming traps.** (1) "**Hermes Agent**" (Nous Research) is a different *agent runtime*, not a model —
> NemoClaw can host it. (2) NVIDIA's vLLM playbook (2026-09-14) now recommends `Qwen3.8-27B NVFP4` for a single
> Spark, but it's **not in NemoClaw's registry** → using it means the existing-server path + finding the parser yourself.

## vLLM flags for tool calling (reference)

```bash
vllm serve <model> \
  --enable-auto-tool-choice \        # mandatory for tool_choice=auto
  --tool-call-parser <family> \      # MUST match the model's wire format
  --reasoning-parser <parser> \      # reasoning models only
  --tool-strict-level function \     # optional floor; constrains the call envelope
  --max-model-len <ctx> --max-num-seqs <n> --gpu-memory-utilization <f> \
  --host 0.0.0.0 --port 8000         # manual path only — then FIREWALL the port
```

- On the **managed** path, read the flags NemoClaw actually used:
  `docker container inspect --format '{{json .Config.Cmd}}' nemoclaw-vllm`.
- **Never point the agent at `/v1/responses`** — NemoClaw notes vLLM's Responses endpoint skips the tool parser.
- **⚠ The tool-call + reasoning parsers for `Qwen3.6-35B-A3B-NVFP4` are not named in the docs.** Read them off a
  running managed container *before* you ever need to start vLLM by hand.
- **Security:** local vLLM has **no auth by default**. Firewall `:8000` to loopback + the OpenShell Docker bridge — especially on venue Wi-Fi.

→ Next: [03-day-of-runbook.md](03-day-of-runbook.md).
