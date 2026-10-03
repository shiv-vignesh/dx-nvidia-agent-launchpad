"""The one background loop. Ticks on ward time, so every deadline in the
requirements fires on stage in seconds instead of minutes."""
import asyncio
import traceback
from .events import emit
from .clock import status

_task = None


async def _loop():
    from .modules import tasks, messaging, oversight
    while True:
        try:
            messaging.check_reroute()     # FR-5.2
            tasks.check_overdue()         # FR-3.4
            oversight.check_draft_ready() # FR-1.5
            oversight.check_nudges()      # FR-8.4
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(1.0)


def start():
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())
        emit("clock", f"Scheduler running — {status()['note']}")


def stop():
    if _task:
        _task.cancel()
