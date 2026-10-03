# Stack setup — NemoClaw + OpenClaw + OpenShell (+ colibri)

Bring the stack on a USB; install at the venue. `install-stack.sh stage` downloads tonight;
`install-stack.sh install` installs from the staged dir. This file is the **ground truth** for *which*
package is real — because several obvious ones are squats.

## ⚠ Verified install sources (checked against npm/PyPI/GitHub metadata)

| Tool | ✅ Install this | ❌ Do NOT install |
|---|---|---|
| **OpenClaw** | `npm i -g openclaw` (repo-linked, `2026.9.8`) | — |
| **OpenShell** | **PyPI `openshell` (`0.1.2`)** — summary + URLs match NVIDIA; or `install.sh` | **npm `openshell@0.1.0`** (no repo/home = squat) |
| **NemoClaw** | `nemoclaw.sh` installer / `git clone NVIDIA/NemoClaw` | **npm `nemoclaw@0.1.0`** and **PyPI `nemoclaw`** (squats) |
| **colibri** | **`git clone JustVugg/colibri`** + build, or release binary | **PyPI `colibri`** — that's an unrelated *AMQP client* |

The real NemoClaw installer is NGC-gated; fetch it with your NGC login:
```bash
curl -fsSLo nemoclaw.sh https://www.nvidia.com/nemoclaw.sh   # then: bash nemoclaw.sh
```

## Platform support (from each project's README)

| Tool | Linux arm64 (GB10) | macOS Apple Silicon | Notes |
|---|:--:|:--:|---|
| OpenClaw | ✅ | ✅ | Node 22.19+/24/26; installed + verified on the Mac |
| OpenShell | ✅ | ✅ (claims support) | needs Docker/Podman; **unverified on our Mac — test before relying on it** |
| NemoClaw | ✅ (DGX) | ❌ | "supported DGX or WSL host" — **Spark-side only** |
| colibri | ✅ | ✅ | pure C + OpenMP; OpenAI-compatible server on `:8000` (we map it to `:8001`) |

**Consequence:** the *full* NemoClaw-managed path only exists on the GB10. On the Mac we can run OpenClaw
(+ maybe OpenShell) against our [registry router](../registry/README.md) → Ollama. That's what the
[complex warm-up](../warmup/complex/README.md) does.

## The hard truth about "offline"

| Artifact | Offline-stageable? | How |
|---|---|---|
| Source repos | ✅ | git bundles (`repos/*.bundle`) — platform-agnostic |
| OpenShell | ✅ | PyPI wheel for `manylinux2014_aarch64` (`wheels/`) + release binary |
| colibri | ✅ | linux-arm64 release binary, or build from the bundle on the venue box |
| OpenClaw | ⚠ partial | `npm pack` gives the tarball, but **npm still resolves deps at install time** unless you also copy a warmed `~/.npm` cache *from a matching-arch box*. Native deps (`koffi`, `esbuild`) rebuild per-arch — a Mac cache won't satisfy the Linux box. |
| NemoClaw managed images/weights | ✅ (separate) | handled by [`scripts/bundle-offline.sh`](../scripts/bundle-offline.sh) |

So: stage everything you can, but **keep a phone hotspot** for npm deps and the NemoClaw image pull. The USB turns
tens of GB into a few MB of leftover fetches — it is not a full air-gap (the docs confirm no documented offline install).

## Usage

```bash
# tonight, fast Wi-Fi:
setup/install-stack.sh stage --dir /Volumes/USB/stack-bundle            # add --dry-run to preview
# (then grab the two by-hand release binaries noted in the output)

# at the venue, from the USB:
setup/install-stack.sh install --dir /Volumes/USB/stack-bundle
# then the NGC-gated NemoClaw installer, then:
nemoclaw onboard
```

Both commands are idempotent, `set -euo pipefail`, and support `--dry-run`. This script stages the **stack**;
[`scripts/bundle-offline.sh`](../scripts/bundle-offline.sh) stages the **models + docker images**. Run both.

## Install order (venue)

1. OpenShell (sandbox + gateway) · 2. OpenClaw (agent runtime) · 3. colibri (optional backend) ·
4. NemoClaw (orchestrator — wires 1+2 and sets the inference route) → `nemoclaw onboard`.
Point the inference route at our [registry router](../registry/README.md) to keep backends swappable.
