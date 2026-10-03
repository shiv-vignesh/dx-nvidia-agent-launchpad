"""Demo clock. Ward time runs faster than wall time so a 10-minute re-route
fires in ~10 seconds on stage. Everything in the app calls now() instead of time.time()."""
import time
from datetime import datetime, timedelta

MIN = 60.0
HOUR = 3600.0

# Ward time starts at 18:20 — 40 minutes before a 19:00 shift change.
_ANCHOR = datetime.now().replace(hour=18, minute=20, second=0, microsecond=0)

_state = {
    "ward_start": _ANCHOR.timestamp(),
    "wall_start": time.time(),
    "speed": 60.0,  # 1 wall second = 1 ward minute
    "paused": False,
    "paused_ward": 0.0,
}


def now() -> float:
    if _state["paused"]:
        return _state["paused_ward"]
    elapsed = time.time() - _state["wall_start"]
    return _state["ward_start"] + elapsed * _state["speed"]


def hhmm(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def rel(ts: float | None) -> str | None:
    """Human offset from ward now, e.g. 'in 24m' / '12m ago'."""
    if ts is None:
        return None
    d = ts - now()
    mins = int(abs(d) // 60)
    if mins < 1:
        return "now"
    txt = f"{mins // 60}h{mins % 60:02d}m" if mins >= 60 else f"{mins}m"
    return f"in {txt}" if d > 0 else f"{txt} ago"


def set_speed(speed: float):
    cur = now()
    _state.update(ward_start=cur, wall_start=time.time(), speed=max(1.0, speed))


def pause():
    _state["paused_ward"] = now()
    _state["paused"] = True


def resume():
    if _state["paused"]:
        _state.update(ward_start=_state["paused_ward"], wall_start=time.time(), paused=False)


def jump(minutes: float):
    """Skip ward time forward — lets a demo land on a deadline instantly."""
    _state["ward_start"] = now() + minutes * MIN
    _state["wall_start"] = time.time()
    if _state["paused"]:
        _state["paused_ward"] = _state["ward_start"]


def reset():
    _state.update(ward_start=_ANCHOR.timestamp(), wall_start=time.time(),
                  speed=60.0, paused=False, paused_ward=0.0)


def status():
    return {
        "ward_time": hhmm(now()),
        "speed": f"{_state['speed']:.0f}x",
        "paused": _state["paused"],
        "note": f"1 real second = {_state['speed']:.0f} ward seconds",
    }


def at(hour: int, minute: int = 0) -> float:
    """Ward timestamp for a clock time today (next day if already past)."""
    base = datetime.fromtimestamp(_state["ward_start"]).replace(
        hour=hour, minute=minute, second=0, microsecond=0)
    if base.timestamp() < _state["ward_start"] - 12 * HOUR:
        base += timedelta(days=1)
    return base.timestamp()
