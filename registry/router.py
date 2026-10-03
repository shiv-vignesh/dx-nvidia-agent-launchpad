#!/usr/bin/env python3
"""
router.py — our swappable model registry, as a tiny OpenAI-compatible router.

ONE endpoint in front of many inference backends (ollama / vllm / colibri). A request
names a *logical* model (e.g. "qwen2.5:7b"); the router looks it up in registry.json,
rewrites it to the backend's real model id, and forwards to that backend. Swap a model's
backend by editing registry.json — the agent calling this endpoint never changes.

This is the seam the brief asks for: "our own model registry that can be swapped by the
inference software (ollama / vllm / colibri)." Tomorrow, point OpenShell's inference.local
(or OpenClaw's provider) at this router instead of directly at a backend.

Pure stdlib (no pip — safe on any Python). Non-streaming passthrough (buffers, then relays).

Run:    python3 registry/router.py                 # serves on 127.0.0.1:9000
Test:   curl -s localhost:9000/v1/models | jq
        curl -s localhost:9000/registry | jq
        curl -s localhost:9000/v1/chat/completions -H 'content-type: application/json' \
          -d '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"hi"}]}'
Env:    REGISTRY_FILE (default ./registry/registry.json), REGISTRY_PORT (overrides config)
"""
import json, os, re, sys, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_FILE = os.environ.get("REGISTRY_FILE", os.path.join(HERE, "registry.json"))


def load_registry():
    raw = open(REGISTRY_FILE, encoding="utf-8").read()
    raw = re.sub(r'^[ \t]*//.*$', '', raw, flags=re.M)     # strip FULL-LINE // comments only
    return json.loads(raw)                                  # (keeps http:// etc. inside values intact)


def resolve(reg, model):
    """logical model name -> (backend_name, backend_cfg, upstream_model)."""
    model = model or reg.get("default_model")
    entry = reg["models"].get(model)
    if not entry:
        raise KeyError(f"model '{model}' not in registry (have: {', '.join(reg['models'])})")
    bname = entry["backend"]
    backend = reg["backends"].get(bname)
    if not backend:
        raise KeyError(f"backend '{bname}' for model '{model}' is not defined")
    return bname, backend, entry.get("upstream_model", model)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj, raw=False):
        body = obj if raw else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quiet the default noisy logging; we print our own
        pass

    def do_GET(self):
        reg = load_registry()
        if self.path in ("/", "/healthz"):
            return self._send(200, {"status": "ok", "models": list(reg["models"])})
        if self.path == "/registry":
            return self._send(200, reg)
        if self.path.rstrip("/") == "/v1/models":
            data = [{"id": m, "object": "model", "owned_by": e["backend"]}
                    for m, e in reg["models"].items()]
            return self._send(200, {"object": "list", "data": data})
        return self._send(404, {"error": f"no route {self.path}"})

    def do_POST(self):
        if self.path.rstrip("/") != "/v1/chat/completions":
            return self._send(404, {"error": f"no route {self.path}"})
        n = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError as e:
            return self._send(400, {"error": f"bad json: {e}"})

        reg = load_registry()
        requested = payload.get("model")
        try:
            bname, backend, upstream_model = resolve(reg, requested)
        except KeyError as e:
            return self._send(404, {"error": str(e)})

        payload["model"] = upstream_model
        print(f"  [route] model={requested or reg['default_model']!r} "
              f"-> backend={bname} upstream={upstream_model!r} ({backend['base_url']})",
              flush=True)

        url = backend["base_url"].rstrip("/") + "/chat/completions"
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {backend.get('api_key', 'placeholder')}"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return self._send(r.status, r.read(), raw=True)
        except urllib.error.HTTPError as e:
            return self._send(e.code, e.read() or json.dumps({"error": str(e)}).encode(), raw=True)
        except urllib.error.URLError as e:
            return self._send(502, {"error": f"backend '{bname}' unreachable at {url}: {e.reason}. "
                                             f"Is it running?"})


def main():
    reg = load_registry()
    host = reg["router"]["host"]
    port = int(os.environ.get("REGISTRY_PORT", reg["router"]["port"]))
    print(f"model-registry router on http://{host}:{port}  (config: {REGISTRY_FILE})")
    print(f"  default_model = {reg['default_model']}")
    for m, e in reg["models"].items():
        print(f"  {m:14s} -> {e['backend']:8s} ({reg['backends'][e['backend']]['base_url']})")
    print("  edit registry.json to swap a backend; no restart of the agent needed.\n")
    try:
        ThreadingHTTPServer((host, port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
