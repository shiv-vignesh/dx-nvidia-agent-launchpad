#!/usr/bin/env bash
# Stage 1 — OpenShell (sandbox + gateway) on the GB10 (Linux arm64). Idempotent.
#
# Two Linux-specific gotchas (confirmed on this box, fixed below):
#  1. compute driver: auto-detect finds nothing → must set OPENSHELL_COMPUTE_DRIVER=docker
#     (the deb only ships the vm driver binary; `docker` is compiled-in). We set it via a
#     systemd *user* override so the gateway service uses it.
#  2. the gateway runs as a systemd USER service; if your user-manager started before you
#     were added to the `docker` group (stage 0), it can't reach the docker socket. We refresh
#     the manager's groups once with `sudo systemctl restart user@<uid>` (survives ssh; a
#     reboot would also fix it permanently since you're now in the docker group).
set -euo pipefail

echo "== install OpenShell runtime (deb) =="
if command -v openshell >/dev/null 2>&1; then
  echo "openshell present: $(openshell --version 2>&1 | head -1)"
else
  curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh
fi
command -v openshell >/dev/null 2>&1 || { echo "ERROR: openshell not on PATH"; exit 1; }

echo "== compute-driver override (docker) =="
mkdir -p ~/.config/systemd/user/openshell-gateway.service.d
cat > ~/.config/systemd/user/openshell-gateway.service.d/10-driver.conf <<'OVR'
[Service]
Environment=OPENSHELL_COMPUTE_DRIVER=docker
OVR
systemctl --user daemon-reload

bring_up() {
  systemctl --user restart openshell-gateway 2>/dev/null || true
  for _ in $(seq 1 25); do sleep 1; openshell status 2>/dev/null | grep -qi Connected && return 0; done
  return 1
}

echo "== start gateway =="
if ! bring_up; then
  echo "not up yet — refreshing user-manager groups (docker group added after login), retrying"
  sudo systemctl restart "user@$(id -u).service" || true
  sleep 2; systemctl --user daemon-reload
  bring_up || {
    echo "GATEWAY NOT CONNECTED — diagnostics:"; openshell status 2>&1 | head
    systemctl --user status openshell-gateway --no-pager 2>&1 | head -20
    echo "== stage 1 INCOMPLETE =="; exit 1; }
fi
echo "--- openshell status ---"; openshell status 2>&1 | head -6

echo "== verify: one-shot sandbox (docker driver) =="
# IMPORTANT: `create` with NO command opens an interactive shell and blocks forever under
# runway (no TTY/stdin). Always pass `-- <cmd>`; `--no-keep` auto-deletes; </dev/null + timeout
# make it impossible to hang the task.
openshell sandbox delete stack-check >/dev/null 2>&1 || true
timeout 180 openshell sandbox create --name stack-check --no-keep -- \
  sh -lc 'echo "SANDBOX OK: $(uname -srm)"' </dev/null 2>&1 | grep -vE '^(→|\[)'
rc=${PIPESTATUS[0]}
openshell sandbox delete stack-check >/dev/null 2>&1 || true   # belt-and-suspenders cleanup
[ "$rc" = 0 ] && echo "== stage 1 OK ==" || { echo "== stage 1 FAILED (sandbox verify rc=$rc) =="; exit 1; }