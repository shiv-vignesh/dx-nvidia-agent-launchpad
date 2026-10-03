#!/usr/bin/env python3
"""Colored live feed of the backend's event stream. Run beside the server on stage."""
import json, sys, urllib.request
try:
    from websockets.sync.client import connect
except ImportError:
    sys.exit("pip install websockets  (or just watch the server's own console)")

HOST = sys.argv[1] if len(sys.argv) > 1 else "localhost:8099"
C = {"handoff": "\033[36m", "task": "\033[33m", "message": "\033[35m", "safety": "\033[31m",
     "focus": "\033[34m", "oversight": "\033[32m", "clock": "\033[90m",
     "demo": "\033[1;97m", "extra": "\033[90m"}
with connect(f"ws://{HOST}/events") as ws:
    print(f"— attached to {HOST} —")
    while True:
        ev = json.loads(ws.recv())
        print(f"{C.get(ev['ch'],'')}{ev['t']} {ev['ch']:<9}\033[0m {ev['text']}", flush=True)
