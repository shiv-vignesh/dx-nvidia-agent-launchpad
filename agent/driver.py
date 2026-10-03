#!/usr/bin/env python3
"""ShiftGuard inference driver — nemotron drives the CareChart backend's inference points
via tool calling, with accurate context pulled from the backend's own tools.

Data-driven: fetches the tool manifest (/agent/tools) and the inference points
(/agent/inference-points) from the backend, then for each point runs a tool-calling loop:

    nemotron(task + tools) → tool_calls → POST /agent/call → feed results back → … → result

Pure stdlib. Run on the GB10 (where backend :8099 and nemotron :8001 live).

    python3 agent/driver.py                 # all points
    python3 agent/driver.py --point AI-5    # one point
Env: BACKEND_URL(:8099) INFERENCE_BASE_URL(:8001/v1) INFERENCE_MODEL(nemotron)
     PATIENT(P-101) TEMPERATURE(0.6) MAX_TOKENS(1024) VLLM_API_KEY(optional)
"""
from __future__ import annotations
import argparse, json, os, sys, urllib.request, urllib.error

BACKEND  = os.environ.get("BACKEND_URL", "http://127.0.0.1:8099")
NEMOTRON = os.environ.get("INFERENCE_BASE_URL", "http://127.0.0.1:8001/v1")
MODEL    = os.environ.get("INFERENCE_MODEL", "nemotron")
API_KEY  = os.environ.get("VLLM_API_KEY", "x")
TEMP     = float(os.environ.get("TEMPERATURE", "0.6"))   # README: 0.6 for tool calling
MAXTOK   = int(os.environ.get("MAX_TOKENS", "8192"))    # reasoning model: <1-2k starves it → finish=length
PATIENT  = os.environ.get("PATIENT", "P-101")
MAX_STEPS = 8

C = {"b": "\033[1m", "g": "\033[32m", "c": "\033[36m", "y": "\033[33m", "x": "\033[0m"}


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def _post(url, body, headers=None):
    h = {"Content-Type": "application/json"}; h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def run_tool(name, arguments):
    try:
        res = _post(f"{BACKEND}/agent/call", {"name": name, "arguments": arguments})
        return res.get("content", json.dumps(res))
    except Exception as e:  # keep the loop alive if a tool errors
        return f"ERROR calling {name}: {e}"


def resolve_handoff_id(patient):
    """Accurate context: find the patient's real handoff id so nemotron doesn't guess it."""
    num = "".join(c for c in patient if c.isdigit())   # P-101 -> 101
    try:
        for h in _get(f"{BACKEND}/handoffs"):
            if num and num in h.get("id", ""):
                return h["id"]
    except Exception:
        pass
    return None


def nemotron(messages, tools):
    body = {"model": MODEL, "messages": messages, "tools": tools,
            "tool_choice": "auto", "temperature": TEMP, "max_tokens": MAXTOK}
    return _post(f"{NEMOTRON}/chat/completions", body, {"Authorization": f"Bearer {API_KEY}"})


def run_point(point, all_tools, patient, handoff_id=None):
    names = set(point.get("tools", []))
    tools = [t for t in all_tools if t["function"]["name"] in names]
    system = ("You are a clinical shift-handoff assistant. ALWAYS use the provided tools to fetch "
              "accurate patient context before answering — never invent clinical facts, labs, meds, "
              f"or vitals. The patient is {patient}.")
    ctx = f"Patient id: {patient}."
    if handoff_id:
        ctx += f" Current handoff id: {handoff_id}."
    user = (f"Task ({point['id']} — {point.get('where','')}): {point['needs_model']}\n"
            f"{ctx} Use these EXACT ids with the tools — do not invent ids. Then give the final result.")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    print(f"\n{C['b']}=== {point['id']} [step {point.get('step','?')}] {point.get('where','')} ==={C['x']}")
    for _ in range(MAX_STEPS):
        try:
            resp = nemotron(messages, tools)
        except urllib.error.URLError as e:
            print(f"  {C['y']}nemotron unreachable: {e}{C['x']}"); return None
        msg = resp["choices"][0]["message"]
        tcs = msg.get("tool_calls") or []
        if tcs:
            messages.append(msg)
            for tc in tcs:
                fn = tc["function"]["name"]
                raw = tc["function"].get("arguments") or "{}"
                args = json.loads(raw) if isinstance(raw, str) and raw.strip() else (raw or {})
                print(f"  {C['c']}→ tool{C['x']} {fn}({json.dumps(args)})")
                content = run_tool(fn, args)
                print(f"    {C['g']}↩{C['x']} {content[:120].replace(chr(10),' ')}…")
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                                 "name": fn, "content": content})
            continue
        if msg.get("reasoning_content"):
            print(f"  {C['y']}reasoning:{C['x']} {msg['reasoning_content'][:200].strip()}…")
        print(f"  {C['b']}RESULT:{C['x']}\n{(msg.get('content') or '(empty)').strip()}")
        return msg.get("content")
    print(f"  {C['y']}(max steps reached without a final answer){C['x']}")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--point", help="inference point id, e.g. AI-5 (default: all)")
    ap.add_argument("--patient", default=PATIENT)
    a = ap.parse_args()
    tools = _get(f"{BACKEND}/agent/tools")["tools"]
    points = _get(f"{BACKEND}/agent/inference-points")["points"]
    if a.point:
        points = [p for p in points if p["id"].lower() == a.point.lower()]
        if not points:
            sys.exit(f"no inference point {a.point!r}")
    hid = resolve_handoff_id(a.patient)
    print(f"driver: {MODEL} @ {NEMOTRON} · backend {BACKEND} · patient {a.patient} "
          f"· handoff {hid} · points {[p['id'] for p in points]}")
    for p in points:
        run_point(p, tools, a.patient, hid)


if __name__ == "__main__":
    main()
