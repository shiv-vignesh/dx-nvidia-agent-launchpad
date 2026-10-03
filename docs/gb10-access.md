# GB10 access & the stack — teammate guide

How to reach the box, what's running, which inference engine it uses, and how a second dev
works on it from their own user. **Everything below was verified live on the box; items marked
⏳ were still in progress when this was written — re-check them with the commands given.**

## The box

| | |
|---|---|
| Hostname | `promaxgb10-87e8` — NVIDIA **DGX Spark** (Dell Pro Max w/ GB10), Ubuntu 24.04, aarch64 |
| IP | **`172.20.65.125`** (wifi `wlP9s9`, /20) |
| Resources | 121 GB unified RAM · 3.4 TB free on `/` |
| Users | **`dell`** (uid 1000) · **`shiv`** (uid 1001) |

## Inference engine: **vLLM** (not Ollama)

The GB10 stack serves models with **vLLM**. NemoClaw's managed path runs vLLM as a host Docker
container (`nemoclaw-vllm`, port **8000**) and routes the sandboxed agent's `inference.local` to it.
**Ollama is NOT installed** on the GB10 — it was only a laptop warm-up substitute. OpenShell and
OpenClaw don't bundle an engine themselves; the engine is whatever provider NemoClaw configures = vLLM.

## What's installed, and where ⚠ (mostly per-user, in shiv's home)

| Component | Path | Scope |
|---|---|---|
| OpenClaw | `/usr/bin/openclaw` | **global** (all users); config per-user in `~/.openclaw` |
| OpenShell | `~shiv/.local/bin/openshell` | **user-local to shiv**; gateway is per-user (own mTLS, loopback) |
| NemoClaw | `~shiv/.npm-global/bin/nemoclaw` | **user-local to shiv** |

**Implication:** `dell` has `openclaw` (global) but **not** `openshell`/`nemoclaw` on PATH, and cannot
use shiv's gateway (per-user mTLS, bound to loopback). The shareable piece across users is the **vLLM
endpoint on `127.0.0.1:8000`** — any local user can reach it.

## Current status (⏳ re-verify)

As of writing: OpenShell gateway **Connected** (`openshell status` showed `:8080`); OpenClaw default is
still a **cloud** model (local inference not wired yet); **NemoClaw `onboard` was still running** (lock
held) so `nemoclaw-vllm` was **not up** and the inference route was **"Not configured."**

```bash
# run these to see the live state:
nemoclaw shiftguard status
docker ps | grep -i vllm
curl -s 127.0.0.1:8000/v1/models        # 200 = vLLM is serving
openshell inference get                   # shows the inference.local route once onboard finishes
```

## Box owner (shiv): start the server / run onboarding

`onboard` is an interactive wizard; run it in a real terminal (not a non-TTY task):

```bash
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"
source ~/shiftguard-secrets.env                 # NGC_API_KEY + HF_TOKEN
nemoclaw onboard --name shiftguard              # agent=OpenClaw, provider=install-vllm
#   → pulls the vLLM image + Qwen3.6 weights, starts nemoclaw-vllm on :8000, wires inference.local
nemoclaw shiftguard status                       # verify green
```

`nemoclaw-vllm` runs `restart=unless-stopped`, so once up it's a **persistent shared server** on
host `:8000` for every local user. If the Spark model is rejected, re-run with
`NEMOCLAW_PROVIDER=vllm nemoclaw onboard --name shiftguard`.

## Teammate (the other dev): how to access from your user

### Get in
1. **SSH access as `dell`** — add your public key (shiv/admin runs this once):
   ```bash
   sudo mkdir -p /home/dell/.ssh
   echo '<your-ed25519-public-key>' | sudo tee -a /home/dell/.ssh/authorized_keys
   sudo chown -R dell:dell /home/dell/.ssh && sudo chmod 700 /home/dell/.ssh && sudo chmod 600 /home/dell/.ssh/authorized_keys
   ```
   Then: `ssh dell@172.20.65.125`
2. **Docker group** (needed for OpenShell/sandbox work): `sudo usermod -aG docker dell` then re-login.

### Path A — share the vLLM endpoint (recommended for the hackathon)

Use the one expensive shared resource (the model server); don't duplicate the stack.
- **On the box** as `dell`: `curl 127.0.0.1:8000/v1/models` → point your tools / the ShiftGuard
  registry router at `http://127.0.0.1:8000/v1`.
- **From your own laptop**: SSH port-forward it, then hit it as localhost:
  ```bash
  ssh -L 8000:127.0.0.1:8000 dell@172.20.65.125
  # now on your laptop: curl http://localhost:8000/v1/models
  ```
⚠ vLLM has **no auth**. Do **not** bind it to `0.0.0.0` on venue wifi — use SSH forwarding.

### Path B — run your own agent stack (only if you need your own sandbox)

OpenShell/OpenClaw/NemoClaw are per-user. As `dell`:
- `openclaw` is already available (global).
- Install your own OpenShell + NemoClaw (user-local), start your own gateway (docker driver — see
  `setup/gb10/01-openshell.sh` for the `OPENSHELL_COMPUTE_DRIVER=docker` + group-refresh fix), and
  onboard with **`NEMOCLAW_PROVIDER=vllm`** pointing at the **shared** `:8000` so you don't re-pull the model.

Heavier; only needed if your work must run inside your *own* OpenShell sandbox. For app development
against the model, Path A is enough.

## TL;DR

- Engine = **vLLM** on `:8000` (Ollama not used).
- Stack is **per-user**; the shared thing is the **vLLM endpoint**.
- Teammate: `ssh dell@172.20.65.125`, then either forward `:8000` (Path A) or stand up your own
  gateway pointing at the shared vLLM (Path B).
- Keep `:8000` loopback-only; forward over SSH. Re-check status with `nemoclaw shiftguard status`.
