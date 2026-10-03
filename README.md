# Dell × NVIDIA Hackathon — Local Agent on GB10

**Boston · Sat Oct 3, 2026.** We build a **local-first AI agent** on a Dell Pro Max with GB10
(DGX Spark-class, 128 GB unified memory). All inference runs on the box — nothing leaves the building.

This repo is **onboarding + prep, not the agent.** Per the rules, the agent itself is built on the day.
Read the docs tonight, run the preflight, pack the USB. Tomorrow we code.

## The stack in 5 lines

1. **vLLM** serves the model on the host (`:8000`) — the part we already know.
2. **OpenClaw** is the agent: a loop that calls the model, runs tools, keeps memory. *(the "hands")*
3. **OpenShell** is the cage: a sandbox + an L7 gateway proxy every call must cross. *(the "walls")*
4. **NemoClaw** is NVIDIA's installer/wiring (`nemoclaw onboard`) that sets up both and routes inference.
5. The agent only ever calls `inference.local`; the gateway routes it to our local vLLM. **No cloud, no keys in the cage.**

> New to agents? Start with [`docs/onboarding/00-agents-101.md`](docs/onboarding/00-agents-101.md) — written for inference engineers.

## Read in this order

| # | Doc | For |
|---|---|---|
| 0 | [00-agents-101.md](docs/onboarding/00-agents-101.md) | Tool calling + the agent loop, as HTTP you already understand |
| 1 | [01-stack-architecture.md](docs/onboarding/01-stack-architecture.md) | OpenClaw / OpenShell / NemoClaw; host vs sandbox; who owns what |
| 2 | [02-local-inference.md](docs/onboarding/02-local-inference.md) | Providers (vLLM / Ollama / endpoint), responsibility split, models for 128 GB |
| 3 | [03-day-of-runbook.md](docs/onboarding/03-day-of-runbook.md) | Hour-by-hour plan, commands in order, roles, fallbacks |
| 4 | [04-debugging.md](docs/onboarding/04-debugging.md) | Symptom → layer → command/log |
| — | [glossary.md](docs/onboarding/glossary.md) | Every term in one place |
| — | [judging.md](docs/judging.md) | How we win each 25% criterion |
| — | [sources/INDEX.md](docs/sources/INDEX.md) | Where every fact comes from |

## Tonight's checklist (see runbook §Tonight)

```bash
cp configs/.env.example .env     # fill in NGC_API_KEY, HF_TOKEN, TELEGRAM_BOT_TOKEN
bash scripts/preflight.sh        # does this box look like a GB10? ports free?
bash scripts/bundle-offline.sh   # build the USB (big downloads happen here)
bash scripts/verify-bundle.sh /Volumes/USB   # checksum the USB before we leave
```

All three scripts support `--dry-run` (print what they'd do, change nothing). Model tags live in
[`configs/models.md`](configs/models.md) — scripts read from there, nothing is hardcoded.

## Ground rules baked into this repo

- **Local-first.** Inference route points only at vLLM on the GB10. Prove it in `openshell term`.
- **Clean box.** No personal data, no real accounts — NVIDIA's guidance, and it's a shared venue machine.
- **Secrets never tracked, never in the sandbox.** `.env` is gitignored; the gateway injects keys at egress.
- **Every factual claim is sourced.** Claims trace to `docs-raw/`; anything we couldn't verify is marked **⚠ unverified**.

## Status

| Component | Pinned version | Source |
|---|---|---|
| OpenClaw | `v2026.9.7` | docs-raw deep-dive |
| OpenShell | `0.0.116` (exact, required by NemoClaw) | docs-raw deep-dive |
| Default model | `nvidia/Qwen3.6-35B-A3B-NVFP4` | docs-raw deep-dive |

See the bottom of [03-day-of-runbook.md](docs/onboarding/03-day-of-runbook.md) for **open questions to resolve in the first 10 minutes** — the big one: *is the Dell Pro Max actually detected as a DGX Spark?*

## CareChart handoff frontend

The nurse handoff interface lives in [`frontend/`](frontend/README.md). It includes the
assignment home screen, report preparation, demo recording, review, and incoming
acknowledgement flow. It runs independently of the Python app using local demo data;
backend inference, audio capture/transcription, and real delivery are not wired in yet.

With Node.js 22.12+ and npm installed:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 4173
```

Open http://127.0.0.1:4173. Run `npm test` for frontend state tests and `npm run build`
for the production bundle. See the [frontend README](frontend/README.md) for the
end-to-end demo flow, nurse perspective switching, and integration boundaries.
