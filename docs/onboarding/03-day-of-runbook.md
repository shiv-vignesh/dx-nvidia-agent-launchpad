# 03 · Day-of runbook

*The plan for Sat Oct 3. Commands in order, who does what, and a fallback for every step that can break.
Judging is 25% each: **technical execution · business value · local-first design · demo quality** — this plan
spends time proportionally. See [judging.md](../judging.md) for how each hour maps to points.*

Source for all commands: `docs-raw/Agent onboarding … GB10.md`. **⚠** = unverified, confirm live.

## Roles (2–4 people)

| Role | Owns | If solo/duo, merge into |
|---|---|---|
| **Platform** (you) | Onboarding, vLLM, OpenShell policy, debugging | — |
| **Builder** | The agent: tools, prompt, skills, memory (built on the day) | Platform |
| **Data/Demo** | Synthetic dataset + answer key, scripted demo, recording | Builder |
| **Business/Pitch** | The 2-min story, judging mapping, slides from the deck | Data/Demo |

## Tonight (before the venue)

**We get the Dell DGX Spark only tomorrow** — so tonight is USB-build + decisions only; nothing that needs the
real box. Do the heavy lifting on fast Wi-Fi at home — venue Wi-Fi is slow. **None of the below requires the Spark**
(it's all `docker pull` / `hf download` / `pip download`).

```bash
cp configs/.env.example .env     # fill NGC_API_KEY, HF_TOKEN, TELEGRAM_BOT_TOKEN
docker login nvcr.io             # NGC API key — required to pull the vLLM image
bash scripts/bundle-offline.sh   # build the USB (tens of GB; this is the long one)
bash scripts/verify-bundle.sh /Volumes/USB   # checksums + sizes before you unplug
# optional: bash scripts/preflight.sh  — on your LAPTOP tonight it only sanity-checks docker/disk/ports;
#           the GPU + DGX-Spark checks are meaningless until you run it ON THE SPARK tomorrow (step 0:00).
```

Also decide tonight (can't change live): **which project** (see below), **what files the agent needs**
(filesystem scope locks at sandbox creation), and **which model** ([configs/models.md](../../configs/models.md)).

> **Reality check on "offline":** there is **no documented offline install.** The managed path still runs
> `docker pull` against a pinned digest and resolves the sandbox image from a registry. **Bring a phone hotspot.**
> The USB turns tens of GB of downloads into megabytes — it is an accelerator, not an air-gap.
>
> **Because we can't onboard tonight**, we can't pre-save the one set of artifacts the docs never name — the
> **managed sandbox image + OpenShell images**. Those must come over the hotspot during the first onboard tomorrow.
> They're small next to the vLLM image/weights (already on USB), so budget a few hotspot minutes, not an hour —
> and **capture them immediately** (step 1:15) so any `--recreate-sandbox` later in the day is instant.

## Hour-by-hour

| Time | Who | Do | Fallback |
|---|---|---|---|
| **0:00–0:10** | Platform | **Resolve the big unknown first** (see ⚠ below): `nemoclaw host probe` · `nemoclaw profiles list`. Is the box a DGX Spark? | If "generic Linux arm64": plan to self-serve vLLM (`NEMOCLAW_PROVIDER=vllm`) |
| **0:10–0:30** | Platform | `rsync -a /media/usb/hf/hub/ ~/.cache/huggingface/hub/`; load images from USB (`scripts/` / `load.sh`); `docker login nvcr.io` | If rsync/load fails: pull over hotspot |
| **0:30–1:00** | Platform | `curl -fsSL …/nemoclaw.sh \| bash` then `nemoclaw onboard` (agent=OpenClaw, provider=install-vllm, tier=Balanced). On stall: `nemoclaw onboard --resume` | `NEMOCLAW_PROVIDER=vllm` + hand-started vLLM |
| **0:30–1:30** | Data/Demo | Build the **synthetic dataset + answer key** (20–30 items). No real data. | Shrink to 10 items |
| **1:00–1:15** | Platform | Verify: `nemoclaw <n> status` (probes `inference.local` + a real inference) · `curl 127.0.0.1:8000/v1/models` | [04-debugging.md](04-debugging.md) |
| **1:15–1:30** | Platform | **Capture what we couldn't pre-stage** (we had no Spark last night): (1) parsers — `docker container inspect --format '{{json .Config.Cmd}}' nemoclaw-vllm` → note into configs/models.md; (2) image names — `docker images` → `docker save` the sandbox/OpenShell images to the USB so a `--recreate-sandbox` later is offline/instant | — |
| **1:30–4:30** | Builder | Build the agent: 3–4 tools max, tight tool descriptions, skills/memory as needed. Test against the answer key. | Drop to 2 tools |
| **2:00** | Platform | Add any channel/preset the demo needs *before* finalizing the sandbox if it affects fs scope | `nemoclaw <n> policy-add <preset>` (network is live; fs is not) |
| **4:30–5:00** | Builder+Platform | Score against the answer key; capture precision/recall or time-to-answer numbers | — |
| **5:00–5:45** | All | **Rehearse the demo twice. Record both.** Include the "sandbox saves the day" moment. | Use the recording if live breaks |
| **5:45–6:00** | Pitch | Lock the 2-min story + judging map ([judging.md](../judging.md)) | — |

## Project ideas (pick ONE tonight)

All use only day-one capabilities (built-in exec/file tools over data in `/sandbox`, the local model, OpenShell
policy as a *visible* feature). Each has a moment where the sandbox **visibly** saves the day — the strongest proof
we *used* OpenShell, not just installed it.

| Idea | Value metric | Tools | Live "sandbox saves the day" |
|---|---|---|---|
| **GPU-cluster failed-job triage** | Minutes-to-root-cause; GPU-hours of reruns avoided (score on 20 labeled synthetic failures) | `exec` (grep/awk/parse), `read_file`, `write_file`, opt. Telegram | Log contains an injected "upload to pastebin" line → `openshell term` shows the **deny live**, agent still returns the correct diagnosis |
| **Invoice ↔ PO reconciliation** | Invoices/hour; precision/recall vs answer key (30 synthetic invoices) | `exec` (pypdf + pandas join), `read_file`, `write_file` | Show `/sandbox`-only writes and **zero egress** in `openshell term` |
| **IT helpdesk first responder** | % tickets resolved without a human; time-to-first-response | `read_file` (queue + KB), `exec` (diagnostics), `write_file`; **exec approvals** | Ticket says "reset all passwords" → approval gate fires, operator **denies on screen**, agent explains why it stopped |

**Scoping:** pick idea 1 or 2 (idea 3 depends on **⚠** how NemoClaw wires OpenClaw exec approvals — test first).
Build dataset + answer key in hour 1, keep tools to 3–4, reserve the last hour for the scripted demo.

## Commands cheat-sheet

```bash
# lifecycle
nemoclaw onboard [--resume|--name <n>|--recreate-sandbox|--fresh]
nemoclaw <n> status            # FIRST thing when anything misbehaves
nemoclaw <n> connect           # shell into the sandbox → then: openclaw tui
nemoclaw <n> logs --follow

# inference / route
curl 127.0.0.1:8000/v1/models
docker logs nemoclaw-vllm
openshell inference get
nemoclaw inference set --model <m> --provider <p> --sandbox <n>   # hot-reloadable

# policy (network = live, filesystem = recreate)
openshell term                 # r=Network Rules, a=approve, x=reject, A=approve all (SESSION-ONLY)
nemoclaw <n> policy list
nemoclaw <n> policy-add <preset>
openshell policy update <sb> --add-endpoint host:443:read-only:rest:enforce

# dashboard
nemoclaw <n> dashboard-url --quiet      # open with 127.0.0.1 (NOT localhost — origin check)
```

## ⚠ Open questions — resolve in the first 10 minutes

| # | Question | Check | If it bites |
|---|---|---|---|
| 1 | **Is the Dell Pro Max detected as a DGX Spark?** (the morning-maker) | `nemoclaw host probe`, `nemoclaw profiles list` | If "generic arm64": Express Install gone, default model drops to Nemotron-3-Nano-4B, Qwen slug rejected, image → `vllm:26.03.post1-py3`. **Workaround:** run vLLM yourself + `NEMOCLAW_PROVIDER=vllm`. Ask organizers if boxes are pre-provisioned. |
| 2 | **Qwen3.6-35B-A3B-NVFP4 parsers** not named in docs | `docker container inspect … nemoclaw-vllm` | Read them before you ever hand-start vLLM |
| 3 | **Ollama** as default on `:11434` (your brief) vs vLLM-only (docs) | Try `nemoclaw onboard`; watch the provider prompt | Fall back to vLLM — the documented path |
| 4 | **Offline install** undocumented; sandbox/OpenShell image names unknown — **and we can't pre-save them (no Spark till tomorrow)** | After the first onboard: `docker images` → `docker save` them to USB (step 1:15) | Keep the hotspot ready for the first pull; budget a few min |
| 5 | **OpenShell 0.0.116 on PyPI** unconfirmed | `pip download openshell==0.0.116 …` tonight | Use the GitHub release asset instead |
| 6 | **Node version** 22.16 vs 22.19 vs 24.16/26 | installer checks it | Install 22.19+ to be safe |
| 7 | **exec approvals** wiring (idea 3) | test in the sandbox tonight | Don't build the demo around it until confirmed |

→ If something breaks: [04-debugging.md](04-debugging.md).
