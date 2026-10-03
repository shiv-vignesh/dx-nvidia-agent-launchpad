"""Event bus: broadcasts to /events WebSocket clients, keeps a replay buffer,
and prints a colored ward-time log to the console — that log is the demo visual."""
import asyncio
import json
from collections import deque
from .clock import hhmm, now

_clients: set = set()
_buffer: deque = deque(maxlen=300)

C = {
    "handoff": "\033[36m", "task": "\033[33m", "message": "\033[35m",
    "safety": "\033[31m", "focus": "\033[34m", "oversight": "\033[32m",
    "clock": "\033[90m", "demo": "\033[1;97m", "extra": "\033[90m",
}
RESET = "\033[0m"
ICON = {
    "handoff": "⇄", "task": "☑", "message": "✉", "safety": "⚠",
    "focus": "⛔", "oversight": "▦", "clock": "⏱", "demo": "▶", "extra": "·",
}


def emit(channel: str, text: str, **data):
    ev = {"ch": channel, "t": hhmm(now()), "text": text, "data": data}
    _buffer.append(ev)
    color, icon = C.get(channel, ""), ICON.get(channel, "·")
    print(f"{color}{ev['t']} {icon} {channel:<9}{RESET} {text}", flush=True)
    dead = []
    for ws in _clients:
        try:
            asyncio.create_task(ws.send_text(json.dumps(ev)))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)
    return ev


async def register(ws):
    await ws.accept()
    _clients.add(ws)
    for ev in list(_buffer)[-40:]:
        await ws.send_text(json.dumps(ev))


def unregister(ws):
    _clients.discard(ws)


def recent(n=60):
    return list(_buffer)[-n:]


def clear():
    _buffer.clear()
