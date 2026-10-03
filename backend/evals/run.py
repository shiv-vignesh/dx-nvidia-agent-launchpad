#!/usr/bin/env python3
"""Run the ShiftGuard agent evals against the local vLLM server.

Drives the real agent loop — model emits a tool call, we execute it against the
ShiftGuard backend, append the result, call the model again — then grades the final
answer with programmatic assertions. No LLM judge, so results are reproducible.

    python3 evals/run.py                      # all 5, against nemotron on :8001
    python3 evals/run.py --only S4            # one scenario
    python3 evals/run.py --model qwen3.6 --endpoint http://127.0.0.1:8000/v1

Writes evals/results.json, which the dashboard at /evals reads.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = "http://127.0.0.1:8099"
MAX_TURNS = 6

C = {"ok": "\033[32m", "bad": "\033[31m", "dim": "\033[90m",
     "hd": "\033[1;97m", "warn": "\033[33m", "0": "\033[0m"}


def post(url, body, timeout=180):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def call_backend(method, path, body=None):
    req = urllib.request.Request(
        BACKEND + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"content-type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt else {}
    except Exception as e:
        return {"error": str(e)}


# ------------------------------------------------------------------ the loop

def run_scenario(sc, manifest, system_prompt, model, endpoint, max_tokens):
    """One agent loop. Returns the transcript, the tools it called, the final text."""
    hid = None
    for step in sc.get("setup", []):
        path = step["path"]
        body = step.get("body")
        if "{hid}" in path:
            path = path.replace("{hid}", hid or "")
            if body:
                body = json.loads(json.dumps(body).replace("{hid}", hid or ""))
        out = call_backend(step["method"], path, body)
        if isinstance(out, dict) and out.get("id", "").startswith("HO-"):
            hid = out["id"]

    user = sc["user"].replace("{hid}", hid or "the current handoff")
    allowed = {t["function"]["name"] for t in manifest}
    tools = [t for t in manifest if t["function"]["name"] in set(sc["tools"])]

    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user}]
    called, transcript, usage = [], [], {"prompt": 0, "completion": 0, "reasoning_chars": 0}
    t0 = time.time()
    final, turns, err = "", 0, None

    for turn in range(MAX_TURNS):
        turns = turn + 1
        try:
            r = post(f"{endpoint}/chat/completions", {
                "model": model, "messages": messages, "tools": tools,
                "tool_choice": "auto", "temperature": 0, "max_tokens": max_tokens})
        except Exception as e:
            err = f"model call failed: {e}"
            break
        if "choices" not in r:
            err = f"bad response: {json.dumps(r)[:300]}"
            break
        u = r.get("usage") or {}
        usage["prompt"] += u.get("prompt_tokens", 0)
        usage["completion"] += u.get("completion_tokens", 0)

        choice = r["choices"][0]
        msg = choice["message"]
        tcs = msg.get("tool_calls") or []
        # reasoning models put their chain in a separate field; it costs completion
        # tokens but never appears in `content`
        reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
        usage["reasoning_chars"] += len(reasoning)
        if reasoning:
            transcript.append({"role": "reasoning", "text": reasoning[:1200],
                               "chars": len(reasoning)})
        if choice["finish_reason"] == "length" and not tcs and not (msg.get("content") or ""):
            err = (f"TRUNCATED: the model used all {max_tokens} completion tokens on "
                   f"reasoning ({len(reasoning)} chars) and never emitted an answer. "
                   f"Raise --max-tokens.")
            break
        messages.append({"role": "assistant",
                         "content": msg.get("content") or "",
                         **({"tool_calls": tcs} if tcs else {})})

        if not tcs:
            final = msg.get("content") or ""
            transcript.append({"role": "assistant", "text": final})
            break

        for tc in tcs:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {"_unparseable": tc["function"]["arguments"]}
            called.append(name)
            transcript.append({"role": "tool_call", "name": name, "args": args,
                               "known_tool": name in allowed})
            if name not in allowed:
                content = (f"ERROR: there is no tool called '{name}'. "
                           f"Available: {sorted(allowed)}")
            else:
                res = call_backend("POST", "/agent/call",
                                   {"name": name, "arguments": args,
                                    "tool_call_id": tc["id"]})
                content = res.get("content", json.dumps(res))
            transcript.append({"role": "tool_result", "name": name,
                               "text": content[:1500]})
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "name": name, "content": content})
    else:
        err = f"hit the {MAX_TURNS}-turn limit without a final answer"

    if not final and not err:
        err = "no final answer produced (empty content, no tool call)"

    return {"final": final, "called": called, "transcript": transcript,
            "turns": turns, "seconds": round(time.time() - t0, 1),
            "usage": usage, "error": err, "user_prompt": user, "handoff_id": hid}


# ------------------------------------------------------------------ grading

def grade(sc, run):
    text = (run["final"] or "").lower()
    called = [c.lower() for c in run["called"]]
    results, got, total = [], 0, 0

    for a in sc["assertions"]:
        w = a.get("weight", 1)
        total += w
        kind, val = a["type"], a["value"]
        detail = ""

        if kind == "calls_tool":
            ok = val.lower() in called
            detail = f"called: {', '.join(called) or 'nothing'}"
        elif kind == "not_calls_tool":
            ok = val.lower() not in called
            detail = f"called: {', '.join(called) or 'nothing'}"
        elif kind == "contains_any":
            hits = [v for v in val if v.lower() in text]
            ok = bool(hits)
            detail = f"matched: {', '.join(hits)}" if hits else "none of these appeared"
        elif kind == "contains_all":
            miss = [v for v in val if v.lower() not in text]
            ok = not miss
            detail = "all present" if ok else f"missing: {', '.join(miss)}"
        elif kind == "not_contains":
            hits = [v for v in val if v.lower() in text]
            ok = not hits
            detail = "clean" if ok else f"FOUND: {', '.join(hits)}"
        elif kind == "regex_any":
            hits = [v for v in val if re.search(v, text, re.I | re.S)]
            ok = bool(hits)
            detail = f"matched /{hits[0]}/" if hits else "no pattern matched"
        elif kind == "regex_none":
            hits = [v for v in val if re.search(v, text, re.I | re.S)]
            ok = not hits
            detail = "clean" if ok else f"FOUND /{hits[0]}/"
        elif kind == "order":
            idx = [text.find(v.lower()) for v in val]
            ok = all(i >= 0 for i in idx) and idx == sorted(idx)
            detail = " then ".join(f"{v}@{i}" for v, i in zip(val, idx))
        else:
            ok, detail = False, f"unknown assertion type '{kind}'"

        if ok:
            got += w
        results.append({"type": kind, "value": val, "why": a.get("why", ""),
                        "weight": w, "passed": ok, "detail": detail})

    if run["error"]:
        got = 0
    pct = round(100 * got / total) if total else 0
    return {"assertions": results, "score": got, "max": total, "pct": pct,
            "verdict": "pass" if pct >= 80 else "partial" if pct >= 50 else "fail"}


# -------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:8001/v1")
    ap.add_argument("--model", default="nemotron")
    ap.add_argument("--only", help="scenario id, e.g. S4")
    ap.add_argument("--max-tokens", type=int, default=4000,
                    help="Nemotron is a reasoning model: it spends hundreds to "
                         "thousands of tokens in `reasoning` before emitting "
                         "`content`. Below ~2500 it gets truncated mid-thought.")
    ap.add_argument("--out", default=str(HERE / "results.json"))
    args = ap.parse_args()

    spec = json.loads((HERE / "scenarios.json").read_text())
    manifest = call_backend("GET", "/agent/tools").get("tools", [])
    if not manifest:
        sys.exit(f"could not reach the ShiftGuard backend at {BACKEND}")

    scenarios = [s for s in spec["scenarios"] if not args.only or s["id"] == args.only]
    print(f"{C['hd']}ShiftGuard agent evals{C['0']}  model={args.model}  "
          f"endpoint={args.endpoint}  scenarios={len(scenarios)}\n")

    out = []
    for sc in scenarios:
        print(f"{C['hd']}{sc['id']} {sc['name']}{C['0']}")
        print(f"{C['dim']}   {sc['inference_point']} · tools: {', '.join(sc['tools'])}{C['0']}")
        run = run_scenario(sc, manifest, spec["system_prompt"], args.model,
                           args.endpoint, args.max_tokens)
        g = grade(sc, run)
        col = C["ok"] if g["verdict"] == "pass" else C["warn"] if g["verdict"] == "partial" else C["bad"]
        print(f"   {col}{g['verdict'].upper()}{C['0']}  {g['score']}/{g['max']} ({g['pct']}%)  "
              f"{run['turns']} turns  {run['seconds']}s  "
              f"{run['usage']['prompt'] + run['usage']['completion']} tokens  "
              f"({run['usage']['reasoning_chars']} reasoning chars)")
        if run["error"]:
            print(f"   {C['bad']}error: {run['error']}{C['0']}")
        for a in g["assertions"]:
            m = f"{C['ok']}✓{C['0']}" if a["passed"] else f"{C['bad']}✗{C['0']}"
            print(f"     {m} [{a['weight']}] {a['type']}: {a['detail'][:90]}")
        print()
        out.append({**{k: sc[k] for k in
                       ("id", "name", "inference_point", "why", "tools",
                        "expected_behaviour")},
                    "run": run, "grade": g})

    tot = sum(r["grade"]["score"] for r in out)
    mx = sum(r["grade"]["max"] for r in out)
    passed = sum(1 for r in out if r["grade"]["verdict"] == "pass")
    summary = {
        "model": args.model, "endpoint": args.endpoint,
        "ran_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scenarios": len(out), "passed": passed,
        "partial": sum(1 for r in out if r["grade"]["verdict"] == "partial"),
        "failed": sum(1 for r in out if r["grade"]["verdict"] == "fail"),
        "score": tot, "max": mx, "pct": round(100 * tot / mx) if mx else 0,
        "seconds": round(sum(r["run"]["seconds"] for r in out), 1),
        "tokens": sum(r["run"]["usage"]["prompt"] + r["run"]["usage"]["completion"]
                      for r in out),
        "reasoning_chars": sum(r["run"]["usage"]["reasoning_chars"] for r in out),
        "max_tokens": args.max_tokens,
    }
    Path(args.out).write_text(json.dumps(
        {"summary": summary, "system_prompt": spec["system_prompt"],
         "results": out}, indent=2))
    print(f"{C['hd']}{passed}/{len(out)} scenarios passed · {tot}/{mx} points "
          f"({summary['pct']}%) · {summary['seconds']}s{C['0']}")
    print(f"{C['dim']}written to {args.out} — dashboard at {BACKEND}/evals{C['0']}")


if __name__ == "__main__":
    main()
