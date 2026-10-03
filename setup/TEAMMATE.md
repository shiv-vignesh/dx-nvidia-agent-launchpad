# Teammate runbook — build the USB (and install at the venue)

Answers "I'll `git clone` and run the setup script — what else?" Short version: **clone + one script gets you ~90%;
the other 10% is secrets and 3 by-hand binaries that can't be scripted.**

## Does our setup satisfy the organizers' two requirements?

| Requirement | Covered by | Status |
|---|---|---|
| "Bring the **full NemoClaw + OpenClaw + OpenShell** stack on USB" | `setup/install-stack.sh stage` (git bundles + OpenShell wheel + OpenClaw npm tarball + colibri) | ✅ + 2 by-hand release binaries |
| "…along with your **models**" | `scripts/bundle-offline.sh` (Qwen3.6-35B + Nemotron backup + vLLM image + wheels) | ✅ needs NGC + HF tokens |
| "Bring a **specific model/library** (e.g. **Hermes**)" | Hermes model = Qwen3.6-35B (already staged); Hermes runtime ships in NemoClaw | ✅ see [configs/models.md](../configs/models.md#hermes) |
| "Don't do the 30–60 min download on venue Wi-Fi" | everything above is pre-staged to USB | ✅ (not a full air-gap — keep a hotspot; no documented offline install) |

`setup/stage-all.sh` runs both stagers + verify in one command.

## What the teammate needs BEYOND `git clone` (the real answer)

1. **A staging machine with fast Wi-Fi** and these tools: `git docker node npm python3 pip curl` (+ `hf` CLI, `zstd` optional). Docker Desktop **running**. ~120 GB+ free disk.
2. **Secrets — the actual blocker. These are NOT in the repo:**
   - `NGC_API_KEY` (ngc.nvidia.com) — to pull the vLLM image
   - `HF_TOKEN` (huggingface.co) — to download weights
   - `TELEGRAM_BOT_TOKEN` — only if the demo uses Telegram
   Put them in `.env`: `cp configs/.env.example .env` then fill. Then `docker login nvcr.io` (use the NGC key).
3. **A USB/SSD** ≥256 GB, exFAT or ext4 (FAT32 can't hold >4 GB files).

## Steps

```bash
git clone <this-repo> && cd <repo>
cp configs/.env.example .env            # fill NGC_API_KEY + HF_TOKEN
docker login nvcr.io                    # NGC key

bash setup/stage-all.sh --usb /Volumes/USB --dry-run   # preview everything first
bash setup/stage-all.sh --usb /Volumes/USB             # the real download (tens of GB, 30–60 min)
```

Then the **3 by-hand downloads** `stage-all.sh` prints (release pages need a human click):

- OpenShell linux-arm64 release binary → `…/stack-bundle/openshell-bin/`
- colibri linux-arm64 release binary → `…/stack-bundle/colibri-bin/` (optional)
- Real NGC NemoClaw installer: `curl -fsSLo /Volumes/USB/stack-bundle/installers/nemoclaw.sh https://www.nvidia.com/nemoclaw.sh`
- Node.js 22.19+ linux-arm64 tarball → `…/stack-bundle/installers/`

Finally verify: `bash scripts/verify-bundle.sh /Volumes/USB` (checksums + presence).

## At the venue (on the GB10)

```bash
rsync -a /Volumes/USB/hf/hub/ ~/.cache/huggingface/hub/     # reuse weights
# load the saved docker images (see scripts/ output), then:
bash setup/install-stack.sh install --dir /Volumes/USB/stack-bundle
bash /Volumes/USB/stack-bundle/installers/nemoclaw.sh        # NGC login
nemoclaw onboard                                             # provider=install-vllm, tier=Balanced
```

Point the inference route at our [registry router](../registry/README.md) to keep backends swappable.
Full hour-by-hour + fallbacks: [docs/onboarding/03-day-of-runbook.md](../docs/onboarding/03-day-of-runbook.md).

## Honest caveats (don't get surprised)

- **Not a true air-gap.** No documented offline NemoClaw install; the managed path still does a `docker pull` and
  resolves the sandbox image from a registry. USB makes it minutes, not an hour — **bring a phone hotspot.**
- **Cross-arch npm.** OpenClaw's npm deps + native modules (`koffi`, `esbuild`) rebuild per-arch at install; a
  Mac-staged npm cache won't satisfy the Linux GB10. Expect a short `npm` fetch at install unless you warm the
  cache *on a Linux arm64 box*.
- **NemoClaw is Spark/WSL only** — don't try to run the managed path on a Mac. OpenClaw (+ our registry) is what
  runs locally for warm-up; see [warmup/complex](../warmup/complex/README.md).
- **Secrets never go on the USB.** Carry them in a password manager.
