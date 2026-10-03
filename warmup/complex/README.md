# Complex warm-up — the stack, end to end, through our registry

This is the real thing in miniature: the **actual stack runtime (OpenClaw)** runs a multi-file triage task,
but every inference call goes **through our swappable model registry** to **Ollama `qwen2.5:7b`** — and we
demonstrate swapping the backend live without touching the agent.

```
OpenClaw  ──(provider=registry, api=openai-completions)──►  registry router :9000
   agent exec, 38 tools, reads *.log files                      │ reads registry.json
                                                                ▼
                                                   ollama :11434  →  qwen2.5:7b
          (swap registry.json → vllm :8000 / colibri :8001; agent code unchanged)
```

## Run it

```bash
bash warmup/complex/run.sh
```

Prereqs it handles for you: starts Ollama + the registry router, ensures OpenClaw has the `registry` provider.
(First run pulls nothing new — `qwen2.5:7b` is already on disk.)

## What each step proves

| Step | Shows |
|---|---|
| 1–2 | Ollama + registry router up; OpenClaw wired to the router as a provider |
| 3 | The registry mapping: `qwen2.5:7b→ollama`, `qwen3.6-35b→vllm`, `glm-5.2→colibri` |
| 4 | **OpenClaw agent** triages `sample-data/*.log` via `registry/qwen2.5:7b` |
| 5 | **Proof**: N inference calls transited our router (`[route] … → ollama`) — not Ollama directly |
| 6 | **Live swap**: edit one line → `qwen2.5:7b` repoints to vLLM → request re-routes (502 here, since vLLM isn't running locally) → revert |

## Honest notes (what this does and doesn't show)

- ✅ **Plumbing is the deliverable, and it works**: real agent runtime → our registry → local inference, with a
  one-line backend swap. On the GB10, step 6's edit points the *same* agent at Qwen3.6-35B on vLLM.
- ⚠ **The 7B agent thrashes**: it makes ~40+ model calls across 38 tools and its triage output is weak/incomplete.
  That's the [docs' "fewer tools, bigger model"](../../docs/onboarding/02-local-inference.md) lesson, live — not a
  bug in the chain. Tomorrow's 35B (and a trimmed tool set) is the fix.
- ⚠ **OpenShell is NOT in this loop.** It can't be exercised meaningfully on the Mac tonight (needs Docker +
  kernel controls; macOS support is claimed but unverified). On the GB10, OpenClaw runs *inside* OpenShell and
  calls `inference.local`, which you point at this same registry router. The agent loop + registry are identical;
  only the cage and the route target change.

## Files

| File | What |
|---|---|
| `run.sh` | orchestrates the whole demo (idempotent; starts services, runs agent, shows proof + swap) |
| `sample-data/*.log` | three synthetic GPU-job failures (OOM / NCCL timeout / user bug) for the triage task |

## Map to the hackathon

This mirrors the **GPU failed-job triage** project idea, but intentionally stops at plumbing — per the rules, the
*agent itself* (tools, prompt, skills) is built on the day. What you're rehearsing is the integration you'll need
working in the first hour: **agent runtime ↔ model registry ↔ local inference**, swappable and provable.
