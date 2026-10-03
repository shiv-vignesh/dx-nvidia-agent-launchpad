"""ShiftGuard mock backend — entry point.

Mock, not robust: SQLite, one process, no auth, no migrations. Built so any UI
(phone, web, both) can attach later over REST plus a /events WebSocket.
The agent layer is deliberately absent; two spots are marked STUB where it lands.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import clock, events, scheduler
from .agent import router as agent_router
from .db import reset_and_seed, rows, DB_PATH
from .modules import (handoff, tasks, messaging, escalation, oversight, extras,
                      directory)
from .demo import router as demo_router

STATIC = Path(__file__).parent / "static"

TAGS = [
    {"name": "demo", "description": "**Start here.** `GET /demo/script` lists the beats; "
                                    "`POST /demo/run` plays the whole 19:00 shift change."},
    {"name": "handoff", "description": "**F1 + F2** — I-PASS draft with a pinned safety block, "
                                       "read-back comparison, per-item sign-off. "
                                       "FR-1.1–1.7, FR-2.1–2.4."},
    {"name": "tasks", "description": "**F3** — carry-over tasks derived from the MAR, pending "
                                     "labs and open orders. One owner each. FR-3.1–3.4."},
    {"name": "escalation", "description": "**F4** — SBAR composer. Background is filled from the "
                                          "records; the Recommendation is required. FR-4.1–4.4."},
    {"name": "messaging", "description": "**F5** — closed-loop states (sent → delivered → read → "
                                         "responded) and the 10-minute re-route. FR-5.1–5.3."},
    {"name": "focus", "description": "**F6** — focus mode. Routine messages are held during a "
                                     "handoff or med pass; urgent and code break through. FR-6.1–6.3."},
    {"name": "oversight", "description": "**F8** — charge-nurse board, unit report, shift-end "
                                         "nudges, aide observations. FR-8.1–8.7."},
    {"name": "extras", "description": "**F7 + F9** — family summary, speak-up concerns, unit "
                                      "transfers, incident linking. FR-7.1–7.2, FR-9.1–9.6."},
    {"name": "registry", "description": "**Patients, RNs and the assignment linking them.** "
                                     "The two ids every other module keys off. "
                                     "`/schema` is the data dictionary."},
    {"name": "agent", "description": "**The NemoClaw seam.** `/agent/tools` is an "
                                  "OpenAI-style tool manifest; `/agent/call` runs one tool and "
                                  "returns a capped result ready for a `role:tool` message; "
                                  "`/agent/inference-points` lists the six places a model is needed."},
    {"name": "clock", "description": "Ward clock. Runs 60x by default so a 10-minute re-route "
                                     "fires in 10 seconds on stage. Speed, jump, pause, resume."},
    {"name": "events", "description": "Live event stream. `ws://host:8099/events` is the feed a "
                                      "UI attaches to; `/events/recent` replays the buffer."},
    {"name": "meta", "description": "Ward state, raw patient records, and the audit log."},
]

DESCRIPTION = """
Mock backend for **ShiftGuard**, a caregiver shift-handoff agent.
Every endpoint traces to a numbered requirement (FR-x.y) from the requirements doc.

* **Mock, not robust.** SQLite, one process, no auth, no migrations. Synthetic patients only — no real PHI.
* **No agent layer.** Deliberately absent; two spots are marked `STUB` in `modules/handoff.py`.
* **UI-agnostic.** REST plus a `/events` WebSocket, so a phone app, a web app or both can attach later.
* **Local-first.** Swagger assets are served from disk, so this page needs no internet.

Try `POST /demo/run` first, with the server console visible — the colored log is the demo.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DB_PATH.exists():
        reset_and_seed()
        events.emit("clock", "Ward seeded — 3 synthetic patients, no real PHI")
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(
    title="ShiftGuard mock backend",
    version="0.1.0-mock",
    description=DESCRIPTION,
    openapi_tags=TAGS,
    lifespan=lifespan,
    docs_url=None,       # replaced below with a self-hosted Swagger UI
    redoc_url=None,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/docs", include_in_schema=False)
def swagger_ui():
    """Swagger UI, served from disk when the assets are vendored, else the CDN."""
    local = (STATIC / "swagger-ui-bundle.js").exists()
    base = "/static" if local else "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5"
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="ShiftGuard API — endpoint explorer",
        swagger_js_url=f"{base}/swagger-ui-bundle.js",
        swagger_css_url=f"{base}/swagger-ui.css",
        swagger_favicon_url="data:,",
        swagger_ui_parameters={"docExpansion": "none", "tryItOutEnabled": True,
                               "displayRequestDuration": True, "filter": True},
    )


@app.get("/ui", include_in_schema=False)
def walkthrough():
    """The flow walkthrough: 13 steps against the live API, AI points marked."""
    f = STATIC / "ui.html"
    if not f.exists():
        return HTMLResponse("<h1>ui.html not deployed</h1>", status_code=404)
    return HTMLResponse(f.read_text())


@app.get("/redoc", include_in_schema=False)
def redoc_ui():
    local = (STATIC / "redoc.standalone.js").exists()
    js = "/static/redoc.standalone.js" if local else \
        "https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"
    return get_redoc_html(openapi_url="/openapi.json",
                          title="ShiftGuard API — reference",
                          redoc_js_url=js, redoc_favicon_url="data:,")

for r in (handoff.router, tasks.router, messaging.router, messaging.focus_router,
          escalation.router, oversight.router, extras.router, agent_router,
          directory.patients_router, directory.staff_router, directory.meta_router,
          demo_router):
    app.include_router(r)


@app.get("/", tags=["meta"])
def index():
    return {
        "service": "ShiftGuard mock backend",
        "ward_clock": clock.status(),
        "modules": {
            "F1+F2 handoff": "/handoffs",
            "F3 tasks": "/tasks",
            "F4 escalation": "/escalations",
            "F5 messaging": "/messages",
            "F6 focus mode": "/focus",
            "F7+F9 extras": "/family-summary/{pid}, /concerns, /transfers, /incidents",
            "F8 oversight": "/oversight/board, /oversight/report, /oversight/observations",
            "registry": "/patients, /nurses, /assignments, /schema",
        },
        "demo": {"script": "GET /demo/script", "run": "POST /demo/run",
                 "reset": "POST /demo/reset"},
        "live": "ws://<host>:8099/events",
        "walkthrough": "/ui",
        "agent_surface": {"manifest": "/agent/tools", "dispatch": "POST /agent/call",
                          "inference_points": "/agent/inference-points"},
        "explore": {"swagger": "/docs", "reference": "/redoc", "schema": "/openapi.json"},
        "agent_layer": "not built — 6 inference points at /agent/inference-points",
    }


@app.get("/ward", tags=["meta"])
def ward():
    return {
        "ward_time": clock.hhmm(clock.now()),
        "patients": rows("SELECT id,name,room,dx,code_status,fall_score FROM patients ORDER BY room"),
        "staff": [{**s, "shift_start": clock.hhmm(s["shift_start"]),
                   "shift_end": clock.hhmm(s["shift_end"])}
                  for s in rows("SELECT * FROM staff")],
    }


@app.get("/audit", tags=["meta"])
def audit_log(limit: int = 50):
    return [{"at": clock.hhmm(a["t"]), "actor": a["actor"], "action": a["action"],
             "detail": a["detail"]}
            for a in rows("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]


# ------------------------------------------------------------------ clock control

@app.get("/clock", tags=["clock"])
def get_clock():
    return clock.status()


@app.post("/clock/speed/{speed}", tags=["clock"])
def set_speed(speed: float):
    clock.set_speed(speed)
    events.emit("clock", f"Ward clock speed set to {speed:.0f}x")
    return clock.status()


@app.post("/clock/jump/{minutes}", tags=["clock"])
def jump(minutes: float):
    clock.jump(minutes)
    events.emit("clock", f"Ward clock jumped {minutes:+.0f} minutes → {clock.hhmm(clock.now())}")
    return clock.status()


@app.post("/clock/pause", tags=["clock"])
def pause():
    clock.pause()
    events.emit("clock", "Ward clock paused")
    return clock.status()


@app.post("/clock/resume", tags=["clock"])
def resume():
    clock.resume()
    events.emit("clock", "Ward clock resumed")
    return clock.status()


# ------------------------------------------------------------------ live stream

@app.get("/events/recent", tags=["events"])
def recent_events(n: int = 60):
    return events.recent(n)


@app.websocket("/events")
async def events_ws(ws: WebSocket):
    await events.register(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        events.unregister(ws)
    except Exception:
        events.unregister(ws)


from .coverage import router as _coverage_router  # noqa: E402  (AI-2 semantic coverage)
app.include_router(_coverage_router)

# CareChart UI, built and served from this same process (one origin, no CORS, no tunnel).
_WEBUI = Path(__file__).parent / "webui"
if _WEBUI.exists():
    app.mount("/app", StaticFiles(directory=_WEBUI, html=True), name="carechart")
