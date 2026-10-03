# Sources index

Everything in `docs/` is **summarized from** the raw material below. The raw files live in `docs-raw/`
(**gitignored** — not tracked, per our guardrail: summarize and link, don't copy third-party docs verbatim).

## Raw files (in `docs-raw/`, untracked)

| File | What it is | Authority | Summarized into |
|---|---|---|---|
| `Agent onboarding NemoClaw + OpenClaw + OpenShell on GB10.md` | **The source of truth.** 495 lines by @Shiv (Oct 2, 2026): tool-calling mechanics, agent loop, host/sandbox architecture, 4 Mermaid diagrams, isolation layers, install lifecycle, 128 GB model candidates, vLLM flags, debugging map, USB checklist, 3 project ideas, 9 open questions | **Primary** | all of `docs/onboarding/*` |
| `01-Getting-Started.md` | Gentle intro: OpenClaw=loop, OpenShell=cage, NemoClaw=installer; `inference.local` explained with analogies | Primary (intro) | `00`, `01` |
| `Agent onboarding … on GB10.pdf` | PDF export of the 495-line `.md` — **duplicate**, no new content | Duplicate | — |
| `Agent_Architecture_on_NVIDIA_NemoClaw.pptx` | 18-slide **image deck**: topology, host-vs-sandbox, responsibility matrix, message flow. Visual rendering of the `.md` — **good demo/judging visual** | Visual only | reuse for the pitch |
| `Agent_Architecture_on_NVIDIA_NemoClaw.pdf` | PDF of the deck | Visual only | — |

> The deck has no text layer (each slide is a full-page PNG), so facts come from the two `.md` files. The deck is
> still worth reusing as-is for the demo slides — see [../judging.md](../judging.md).

## Canonical upstream URLs (from the deep-dive's own Sources section)

Append `.md` to any `docs.nvidia.com/nemoclaw` URL to get the Markdown version (handy for the USB).

**NVIDIA DGX Spark build pages**
- Run NemoClaw with a Local LLM — https://build.nvidia.com/spark/nemoclaw · /instructions
- Run OpenClaw with a Local LLM — https://build.nvidia.com/spark/openclaw
- Secure AI Agents with OpenShell — https://build.nvidia.com/spark/openshell · /instructions · /agent-ready-models
- Run Hermes Agent with a Local LLM — https://build.nvidia.com/spark/hermes-agent · /agent-ready-models
- Serve LLMs with vLLM: choose a recipe — https://build.nvidia.com/spark/vllm/choose-recipe

**NemoClaw docs**
- Architecture Details — https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/architecture
- Architecture Overview (how it works) — https://docs.nvidia.com/nemoclaw/user-guide/openclaw/about/how-it-works
- Set Up vLLM — https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/inference/local-inference/set-up-vllm
- Network Policies — https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/network-policies
- Approve/Deny Network Requests — https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/network-policy/approve-network-requests
- Troubleshooting — https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/troubleshooting
- DGX Spark Express prompt asset — https://raw.githubusercontent.com/NVIDIA/NemoClaw/f3682a5be7069e58303d3345e682424d5c2453b2/docs/resources/prompt-assets/dgx-spark.md

**OpenClaw / vLLM**
- OpenClaw docs home — https://docs.openclaw.ai · /concepts/agent-loop · /providers/vllm
- vLLM Tool Calling — https://docs.vllm.ai/en/latest/features/tool_calling/

## Pinned versions & identifiers (verify at venue)

| Thing | Value | Confidence |
|---|---|---|
| OpenClaw | `v2026.9.7` | doc-stated |
| OpenShell | `0.0.116` (exact) | doc-stated; **⚠ PyPI availability unconfirmed** |
| Default model | `nvidia/Qwen3.6-35B-A3B-NVFP4` | doc-stated (DGX Spark profile) |
| vLLM image | `nvcr.io/nvidia/vllm:26.05.post1-py3` @ `sha256:9204569b17ee4c0eff75194b8e6e458479c8aee18953b5ab9cf359fcdac659e2` | doc-stated (arm64) |
| Generic-arm64 fallback image | `nvcr.io/nvidia/vllm:26.03.post1-py3` | doc-stated |
| Node.js | 22.19+ (also seen 22.16+; standalone OpenClaw 24.16+/26) | **⚠ conflicting** |
| Ollama default `:11434` | from the brief | **⚠ not in docs-raw** |

See [../onboarding/03-day-of-runbook.md](../onboarding/03-day-of-runbook.md) for the full open-questions list.
