import json, sys, urllib.request

def post(u, b, t=180):
    r = urllib.request.Request(u, data=json.dumps(b).encode(),
                               headers={"content-type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(r, timeout=t).read())

sid = sys.argv[1] if len(sys.argv) > 1 else "S4"
mt = int(sys.argv[2]) if len(sys.argv) > 2 else 900
spec = json.load(open("evals/scenarios.json"))
manifest = json.loads(urllib.request.urlopen("http://127.0.0.1:8099/agent/tools").read())["tools"]
sc = [s for s in spec["scenarios"] if s["id"] == sid][0]
tools = [t for t in manifest if t["function"]["name"] in set(sc["tools"])]
msgs = [{"role": "system", "content": spec["system_prompt"]},
        {"role": "user", "content": sc["user"]}]

for turn in range(5):
    r = post("http://127.0.0.1:8001/v1/chat/completions",
             {"model": "nemotron", "messages": msgs, "tools": tools,
              "tool_choice": "auto", "temperature": 0, "max_tokens": mt})
    ch = r["choices"][0]
    m = ch["message"]
    tcs = m.get("tool_calls") or []
    print("--- turn %d: finish=%s completion=%d" % (turn, ch["finish_reason"], r["usage"]["completion_tokens"]))
    print("    content=%d reasoning=%d tool_calls=%s" % (
        len(m.get("content") or ""), len(m.get("reasoning") or ""),
        [t["function"]["name"] for t in tcs]))
    msgs.append({"role": "assistant", "content": m.get("content") or "",
                 **({"tool_calls": tcs} if tcs else {})})
    if not tcs:
        print("    FINAL: %r" % ((m.get("content") or "")[:400],))
        print("    REASONING TAIL: %r" % ((m.get("reasoning") or "")[-400:],))
        break
    for tc in tcs:
        res = post("http://127.0.0.1:8099/agent/call",
                   {"name": tc["function"]["name"],
                    "arguments": json.loads(tc["function"]["arguments"] or "{}")})
        msgs.append({"role": "tool", "tool_call_id": tc["id"],
                     "name": tc["function"]["name"], "content": res.get("content", "")})
