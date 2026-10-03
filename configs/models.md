# Models & images — single source of truth

**Scripts read from this file.** Nothing model-related is hardcoded in `scripts/`. The machine-readable blocks
between the `<!-- …-START/END -->` markers are parsed by `bundle-offline.sh` and `verify-bundle.sh`. Edit those
lists to change what lands on the USB. Env vars override the file (see each script's `--help`).

Sizes marked ≈ are estimates (params × bytes), not doc figures. See
[../docs/onboarding/02-local-inference.md](../docs/onboarding/02-local-inference.md) for the full candidate table.

## Chosen models

| Role | HF id | Download size | Notes |
|---|---|---|---|
| **Primary** | `nvidia/Qwen3.6-35B-A3B-NVFP4` | ≈20 GB *(not doc-stated)* | DGX Spark default; A3B decodes fast; **start here** |
| **Backup** | `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4` | 21.56 GB (rev `0dcd680e5585c791728c83342b311d0a0026dbeb`) | NVIDIA-native story; 1 seq |
| Smoke-test | `nvidia/NVIDIA-Nemotron-3-Nano-4B-FP8` | ≈5 GB | Generic-arm64 fallback default; weak at planning |

## Hermes (the organizers' suggestion) — already covered

NVIDIA's Hermes-agent page lists its **agent-ready model as `nvidia/Qwen3.6-35B-A3B-NVFP4`** — the *same* model we
stage as primary. "Hermes" is an **agent runtime** (an OpenClaw alternative that NemoClaw can host — the NemoClaw
repo says *"run agents like Hermes, LangChain Deep Agents, and OpenClaw"*), not separate weights. So:

| Hermes piece | Status |
|---|---|
| Hermes agent-ready **model** | ✅ already staged (`nvidia/Qwen3.6-35B-A3B-NVFP4`) |
| Hermes **runtime** | ✅ ships with NemoClaw (staged by `setup/install-stack.sh`) |
| A literal "Hermes" model to tinker with | optional: `NousResearch/Hermes-3-Llama-3.1-8B` (≈16 GB, canonical tool-calling example) — not in the bundle block by default |

## USB layout (where each lands)

| On the USB | What |
|---|---|
| `hf/hub/` | HF cache (rsync into `~/.cache/huggingface/hub/` at venue) |
| `images/` | `docker save`d, zstd-compressed container tarballs |
| `wheels/` | aarch64 cp312 pip wheels (`--no-index --find-links`) |
| `installers/` | nemoclaw.sh, uninstall.sh, OpenShell release, Node tarball, nemoclaw.bundle |
| `SHA256SUMS` | checksums for everything above |

---

## Machine-readable blocks (do not rename the markers)

HF model ids to bundle (one per line; append `@<revision>` to pin):

<!-- BUNDLE-MODELS-START -->
nvidia/Qwen3.6-35B-A3B-NVFP4
nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4@0dcd680e5585c791728c83342b311d0a0026dbeb
<!-- BUNDLE-MODELS-END -->

Container images to `docker save` (one per line; pin by digest where known):

<!-- BUNDLE-IMAGES-START -->
nvcr.io/nvidia/vllm:26.05.post1-py3@sha256:9204569b17ee4c0eff75194b8e6e458479c8aee18953b5ab9cf359fcdac659e2
busybox:latest
<!-- BUNDLE-IMAGES-END -->

Optional images (uncomment in the block above to include — kept out by default to save space):
`vllm/vllm-openai@sha256:3af90144a0926e5c5fe46ee16e5201e763dd854538b9d7ce433755f11dadaf78` (~12.69 GB, Nemotron backup),
`nvcr.io/nvidia/vllm:26.03.post1-py3` (generic-arm64 fallback image).

Python wheels to download (aarch64, cp312; one per line):

<!-- BUNDLE-WHEELS-START -->
openai
huggingface_hub[cli]
fastapi
uvicorn
pydantic
httpx
pandas
pypdf
mcp
openshell==0.0.116
<!-- BUNDLE-WHEELS-END -->

> **⚠** `openshell==0.0.116` on PyPI is unconfirmed; if `pip download` fails, drop it from the block and use the
> GitHub release asset instead (handled by `bundle-offline.sh`'s installer step).
