# Warm-up — tonight, on your Mac (no Spark needed)

Everything here runs locally on the M5 Pro against **Ollama**, so you arrive tomorrow with the agent
loop in muscle memory. This folder is **not** the hackathon agent and **not** part of the onboarding kit —
it's a practice rig. (Untracked by default; commit it only if the team wants it.)

## What's installed

| Thing | Where | Notes |
|---|---|---|
| Ollama | `brew`, serving on `:11434` | started with `ollama serve` (bg). `brew services start ollama` to persist |
| Model | `qwen2.5:7b` (4.7 GB) | strong tool-calling; thematically close to tomorrow's Qwen3.6 |
| OpenClaw | `npm i -g openclaw` → `v2026.9.8` | the **real** runtime; wired to Ollama as default model |

OpenClaw config lives at `~/.openclaw/openclaw.json` (we patched in the `ollama` provider + set
`ollama/qwen2.5:7b` as default). Reset anytime with `openclaw reset`.

## Track 1 — feel the loop by hand (`agent_loop.py`)

Pure-stdlib ~120-line agent loop that narrates every step of
[`../docs/onboarding/00-agents-101.md`](../docs/onboarding/00-agents-101.md).

```bash
# ensure ollama is up:  ollama serve &   (or: brew services start ollama)
python3 warmup/agent_loop.py "What's the weather in Boston, in Fahrenheit?"
python3 warmup/agent_loop.py "Weather in Austin?"          # single tool, one extra round
```

**Watch for (the inference-engineer aha's):**
1. One user turn = **multiple model requests** (printed as `model request #N`).
2. Each request **re-sends the whole history** → repeated prefill. The `~N prompt tokens` line grows every
   round. *This is why prefix caching matters so much for agents.*
3. The model only emits text; `message.tool_calls[]` is the **server's parser** output. Nothing runs in the model.
4. `finish_reason` flips `tool_calls` → `stop`.

**The bug you'll see (on purpose):** for the Fahrenheit question the 7B model issues **both** tool calls in
*parallel* — so `convert_temp` fires with a guessed value *before* `get_weather` returns, and the final answer
is wrong (says 12°C ≈ 68°F; it's really 53.6°F). That's the doc's **parallel-vs-dependent tool call** warning,
live. Fix in the real world: sequential tools, or a model/prompt that chains. Great thing to have already seen.

## Track 2 — run the real runtime (OpenClaw)

```bash
openclaw models status                    # Default should be ollama/qwen2.5:7b
openclaw infer model run --model ollama/qwen2.5:7b --prompt "Reply with exactly: ok"   # plumbing check

# the interactive TUI — THIS is the thing to actually play with:
openclaw chat                             # (alias for `tui --local`)

# one-shot headless agent turn (what we smoke-tested):
openclaw agent exec --model ollama/qwen2.5:7b --local-model-lean --thinking off \
  --cwd /tmp "List the files in the current directory"
```

**In `openclaw chat`, try:**
- Ask it to read/write a file or run a shell command → watch the **tool call + approval** flow (this is OpenClaw's
  exec-approval gate — the same mechanism as tomorrow's "destructive action needs approval" demo beat).
- `openclaw docs <query>` searches the live docs from the CLI (e.g. `openclaw docs skills`).
- `openclaw models status`, `openclaw doctor` — the health/debug surface.

**Map to tomorrow:** OpenClaw here is standalone. Tomorrow it's the *same runtime* but **inside the OpenShell
sandbox**, reached via NemoClaw, calling `inference.local` instead of Ollama directly. The loop, tools, skills,
memory, approvals you practice tonight are identical — only the cage and the inference route change.
*(OpenShell's sandbox can't run on macOS: it needs Linux Landlock/seccomp/netns. That's the one piece you can
only see on the Spark.)*

## What this proved for tomorrow (open questions, now answered)

- ✅ **Ollama returns structured `tool_calls` on :11434** exactly like vLLM (`finish_reason=tool_calls`, args as a
  JSON string). The ⚠ "does Ollama tool-call?" question from the docs is settled — it does.
- ✅ **OpenClaw is a real, installable runtime** (`npm i -g openclaw`, `v2026.9.8` ≈ the doc's pinned `v2026.9.7`)
  with first-class Ollama support and implicit model discovery.
- ⚠ Small (7B) models make dumb errors (parallel-call bug; "6×7=21"). Tomorrow's 35B A3B is the fix — but the
  *plumbing* you practiced is identical.

## Teardown (if you want a clean slate)

```bash
openclaw reset                 # clears ~/.openclaw config/state (keeps the CLI)
# brew services stop ollama    # if you started it as a service
# npm uninstall -g openclaw ; brew uninstall ollama
```
