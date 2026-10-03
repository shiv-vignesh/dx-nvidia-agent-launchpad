# Ollama + the warm-up loop — quick reference

Local setup on the Mac for tonight's warm-up. Ollama serves an OpenAI-compatible API on `:11434`;
`warmup/agent_loop.py` talks to it to demonstrate the agent loop.

## 1. Start the Ollama server

`ollama serve` starts the **API daemon only** — it loads **no model** until a request names one.

```bash
ollama serve                 # foreground: shows logs, Ctrl-C to stop
ollama serve &               # background: dies when you close the terminal
brew services start ollama   # persistent: managed service, restarts at login
```

Confirm it's up:

```bash
curl -s localhost:11434/api/tags      # HTTP 200 + JSON = listening
```

Binary lives at `/opt/homebrew/bin/ollama`. To stop a background/one-off server: `pkill -f "ollama serve"`
(or `brew services stop ollama` if you started it as a service).

## 2. Ollama commands you'll actually use

| Command | What it does |
|---|---|
| `ollama serve` | Start the API daemon on `:11434`. **No default model** — weights load on first request, unload after idle (`OLLAMA_KEEP_ALIVE`, default 5 min). |
| `ollama list` | Models **on disk** (we pulled `qwen2.5:7b`). |
| `ollama ps` | Models **loaded in memory** right now (empty just after `serve`). |
| `ollama pull <model>` | Download a model, e.g. `ollama pull qwen2.5:7b`. |
| `ollama run <model>` | Load + chat with a model in the terminal (also loads it for API use). |
| `ollama show <model>` | Model details: params, context length, chat template, license. |
| `ollama stop <model>` | Unload a model from memory (keeps it on disk). |
| `ollama rm <model>` | Delete a model from disk. |

Direct API test (OpenAI-compatible endpoint — the same one the warm-up script hits):

```bash
curl -s localhost:11434/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model":"qwen2.5:7b",
  "messages":[{"role":"user","content":"say hi"}]
}' | jq .choices[0].message.content
```

> **Note:** "default model" is a *client* concept, not Ollama's. `ollama serve` has none; every request must name a
> `model`. (OpenClaw sets its own default, `ollama/qwen2.5:7b`, in `~/.openclaw/openclaw.json`.)

## 3. What `warmup/agent_loop.py` does

A ~120-line, **pure-stdlib** agent loop (no pip installs) that hits the local Ollama endpoint and **narrates every
step** of the agent loop from [`../docs/onboarding/00-agents-101.md`](../docs/onboarding/00-agents-101.md):

```
render tools → model decodes → server parses tool_calls → client executes → append result → re-send → repeat
```

Run it (Ollama must be up, `qwen2.5:7b` pulled):

```bash
python3 warmup/agent_loop.py "What's the weather in Boston, in Fahrenheit?"
python3 warmup/agent_loop.py "Weather in Austin?"
# override model/endpoint if needed:
OLLAMA_MODEL=qwen2.5:7b OPENAI_BASE_URL=http://localhost:11434/v1 python3 warmup/agent_loop.py "..."
```

It defines two toy tools (`get_weather`, `convert_temp`) and prints, each round: the request number, the running
history size (~prompt tokens, which **grows every round**), `finish_reason`, each `tool_call` with its arguments,
and the tool result — then the final answer and how many model requests the single turn cost.

**What to notice (the inference-engineer takeaways):**
1. One user turn = **multiple model requests**; each **re-sends the whole history** → repeated prefill (why prefix caching matters).
2. The model only emits text; `message.tool_calls[]` is the **server parser's** output — nothing executes in the model.
3. `finish_reason` flips `tool_calls` → `stop` when the loop ends.
4. **Deliberate bug:** on the Fahrenheit question the 7B model fires both tools *in parallel*, so `convert_temp`
   runs on a guessed value before `get_weather` returns → wrong answer. That's the real "parallel vs dependent
   tool calls" failure mode, live.

> This is a **teaching rig, not the hackathon agent.** It uses Ollama on localhost; tomorrow's agent is OpenClaw
> inside the OpenShell sandbox calling `inference.local`. The loop is identical — only the model and the cage change.
