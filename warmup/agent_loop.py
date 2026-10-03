#!/usr/bin/env python3
"""
agent_loop.py — a hand-rolled agent loop in ~120 lines, pure stdlib.

Purpose: feel the loop before tomorrow. This is NOT the hackathon agent — it's a
teaching rig that hits a local OpenAI-compatible endpoint (Ollama on :11434) and
prints every step of docs/onboarding/00-agents-101.md:

    render → decode → parse → execute → append → re-send   (repeat)

What to watch for (you're an inference engineer — these are the "aha"s):
  1. ONE user turn costs MULTIPLE model requests (count them below).
  2. Every request re-sends the WHOLE growing history → repeated prefill.
     That's why agent latency ≈ TTFT × rounds + tool time, not decode speed.
     On real serving this is exactly where prefix caching earns its keep.
  3. The model only ever emits TEXT. The server's parser turns it into
     message.tool_calls[]. Nothing executes inside the model server.
  4. finish_reason flips: "tool_calls" (keep looping) vs "stop" (done).

Run:  OLLAMA_MODEL=qwen2.5:7b python3 warmup/agent_loop.py
      python3 warmup/agent_loop.py "What's the weather in Boston in Fahrenheit?"
"""
import json, os, sys, urllib.request, urllib.error

BASE  = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
C = {"dim": "\033[2m", "b": "\033[1m", "g": "\033[32m", "y": "\033[33m",
     "c": "\033[36m", "r": "\033[31m", "x": "\033[0m"}

# ── Tools: a 2-step chain so you SEE multiple loop rounds ────────────────────
# "weather in Boston in Fahrenheit" → get_weather(Boston)=12C → convert_temp(12,F)
WEATHER = {"boston": (12, "rain"), "san francisco": (17, "fog"),
           "austin": (31, "sun"), "new york": (9, "wind")}

def get_weather(city: str):
    t, cond = WEATHER.get(city.strip().lower(), (20, "clear"))
    return {"city": city, "celsius": t, "conditions": cond}

def convert_temp(value: float, to: str):
    value = float(value)
    out = value * 9 / 5 + 32 if to.lower().startswith("f") else (value - 32) * 5 / 9
    return {"value": round(out, 1), "unit": to.upper()[0]}

TOOLS_IMPL = {"get_weather": get_weather, "convert_temp": convert_temp}

TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "get_weather", "description": "Current weather for a city (temp in Celsius).",
        "parameters": {"type": "object",
                       "properties": {"city": {"type": "string"}}, "required": ["city"]}}},
    {"type": "function", "function": {
        "name": "convert_temp", "description": "Convert a temperature to F or C.",
        "parameters": {"type": "object",
                       "properties": {"value": {"type": "number"},
                                      "to": {"type": "string", "enum": ["F", "C"]}},
                       "required": ["value", "to"]}}},
]

def call_model(messages):
    """One HTTP round trip to /v1/chat/completions. This is the ONLY network call."""
    body = json.dumps({"model": MODEL, "messages": messages,
                       "tools": TOOLS_SCHEMA, "tool_choice": "auto",
                       "temperature": 0}).encode()
    req = urllib.request.Request(f"{BASE}/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer placeholder-key"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.URLError as e:
        sys.exit(f"{C['r']}Can't reach {BASE} — is `ollama serve` running? ({e}){C['x']}")

def approx_tokens(messages):
    return len(json.dumps(messages)) // 4  # rough; just to SHOW the context growing

def run(user_msg):
    messages = [{"role": "user", "content": user_msg}]
    print(f"{C['b']}USER:{C['x']} {user_msg}\n")
    rounds = 0
    while True:
        rounds += 1
        print(f"{C['dim']}{'─'*70}{C['x']}")
        print(f"{C['b']}→ model request #{rounds}{C['x']}  "
              f"{C['dim']}(history: {len(messages)} msgs, ~{approx_tokens(messages)} prompt tokens — "
              f"re-prefilled every round){C['x']}")
        resp = call_model(messages)
        msg = resp["choices"][0]["message"]
        finish = resp["choices"][0].get("finish_reason")
        print(f"  {C['dim']}finish_reason = {finish}{C['x']}")

        tcs = msg.get("tool_calls") or []
        if not tcs:
            print(f"\n{C['g']}{C['b']}FINAL:{C['x']} {msg.get('content','').strip()}")
            print(f"\n{C['y']}★ one user turn took {rounds} model request(s). "
                  f"Each re-sent the full history.{C['x']}")
            return

        # append the assistant message that asked for tools (MUST include tool_calls)
        messages.append(msg)
        for tc in tcs:
            name = tc["function"]["name"]
            raw  = tc["function"]["arguments"]            # a JSON *string*
            args = json.loads(raw) if isinstance(raw, str) else raw
            print(f"  {C['c']}tool_call{C['x']} {name}({json.dumps(args)})  "
                  f"{C['dim']}id={tc.get('id','?')}{C['x']}")
            try:
                result = TOOLS_IMPL[name](**args)        # EXECUTE happens here, in the client
                out = json.dumps(result)
            except Exception as e:
                out = json.dumps({"error": str(e)})
            print(f"    {C['dim']}→ result: {out}{C['x']}")
            # append the tool result so the next request can see it
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "name": name, "content": out})
        print()

if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What's the weather in Boston, in Fahrenheit?"
    print(f"{C['dim']}model={MODEL}  endpoint={BASE}{C['x']}\n")
    run(q)
