# OpenShell on macOS (Apple Silicon) — actually installed & tested

Everything here was **run and verified** on an M5 Pro, Oct 2026. This corrects earlier guesses: the PyPI
`openshell` package is the **Python SDK (client)**, *not* the runtime; the real runtime is a Rust binary that
the installer lands via a **Homebrew tap**, and on macOS it runs sandboxes in a **lightweight Linux VM** (the
`vm` compute driver), not Docker.

## What's what

| Artifact | Install | Role |
|---|---|---|
| OpenShell **runtime** (`openshell`, `openshell-gateway`, `openshell-driver-vm`) | `curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh \| sh` → brew tap `nvidia/openshell` | the CLI + gateway + VM driver |
| OpenShell **Python SDK** (`openshell` on PyPI, 0.1.2) | `pip install openshell` (in a venv) | `SandboxClient`, `Sandbox`, `exec`… — what our product imports to drive sandboxes |

## The two gotchas that cost time (fix before you rely on it)

1. **Gateway won't start: "no compute driver configured."** On macOS set the VM driver:
   ```bash
   OPENSHELL_COMPUTE_DRIVER=vm <gateway>    # or set in the gateway config / brew service env
   ```
2. **`sandbox create` fails: "mke2fs not found."** The VM driver builds an ext4 rootfs and needs e2fsprogs:
   ```bash
   brew install e2fsprogs
   ```

## The procedure that worked

```bash
# 1. install runtime
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh
brew install e2fsprogs

# 2. start the gateway with the vm driver
pkill -f openshell-gateway 2>/dev/null
nohup env OPENSHELL_COMPUTE_DRIVER=vm \
  /opt/homebrew/opt/openshell/libexec/openshell-gateway-homebrew-service >/tmp/openshell-gw.log 2>&1 &
openshell status            # → Connected, Authenticated (mTLS)

# 3. create a sandbox + run in it
openshell sandbox create --name warmup          # pulls a ~512 MB Ubuntu image, boots a Linux VM
openshell sandbox exec -n warmup -- uname -srm   # Linux 6.12.76 aarch64
openshell sandbox list                           # warmup  Ready
```

## What we proved (real output)

| Test | Result |
|---|---|
| Sandbox OS/kernel | `Ubuntu 24.04.5 LTS`, `Linux 6.12.76 aarch64`, user `ubuntu` |
| Filesystem isolation | `/tmp` writable; `/etc` **read-only** |
| Network egress (deny-by-default) | `1.1.1.1:53` and `github:443` both **BLOCKED** from inside the sandbox |
| Policy | `openshell policy get warmup` → effective, source=sandbox |

## How this maps to the hackathon

This is the **OpenShell** third of the stack, genuinely running. Two honest gaps remain for a full local loop:

- **OpenClaw *inside* OpenShell**: the base sandbox image is minimal (no curl/python/node) and egress is denied,
  so installing OpenClaw into it by hand means allowing egress + apt, or baking a custom image (`sandbox create
  --from <image>`). **That gluing is exactly NemoClaw's job** — and NemoClaw is Spark/WSL-only. So the *managed*
  end-to-end (OpenClaw-in-OpenShell with `inference.local` → our registry → vLLM) is a venue task; here we've
  proven each half works.
- **macOS driver ≠ venue driver**: the Mac uses the `vm` driver; the GB10 (Linux) uses a container driver. The
  `e2fsprogs`/`vm` gotchas above are **Mac-warm-up only** — they won't apply on the Spark.

## Teardown

```bash
openshell sandbox delete warmup
pkill -f openshell-gateway        # or: brew services stop openshell
```
