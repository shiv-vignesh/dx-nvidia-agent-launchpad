# ShiftGuard — mock backend

A UI-agnostic backend for the caregiver shift-handoff agent. Every endpoint traces to a
numbered requirement (FR-x.y) from the requirements doc.

**Mock, not robust, on purpose:** SQLite, one process, no auth, no migrations, no retries.
Synthetic patients only — no real PHI. **The agent layer is not built** — two spots are
marked `STUB` in `app/modules/handoff.py` where it lands.

## Run

```bash
cd backend                     # in this repo
./run.sh                       # venv, deps, uvicorn on :8099
```

| Where | What |
|---|---|
| `http://<host>:8099/schema` | **Data dictionary** — ids, tables, relationships (also [SCHEMA.md](SCHEMA.md)) |
| `http://<host>:8099/ui` | **Flow walkthrough** — 13 steps against the live API, AI points marked |
| `http://<host>:8099/docs` | **Swagger UI** — every endpoint, grouped by feature, with Try-it-out |
| `http://<host>:8099/redoc` | Reading reference for the same schema |
| `http://<host>:8099/` | Index: module map, ward clock, links |
| `ws://<host>:8099/events` | Live event stream — what a UI attaches to |
| the server console | The colored ward-time log. **This is the demo visual.** |

Swagger assets are vendored in `app/static/`, so `/docs` loads with no internet.

## The demo

```bash
curl -X POST localhost:8099/demo/run           # 13 beats, ~11s, narrate over the console
curl -X POST 'localhost:8099/demo/run?pace=0'  # instant, for a smoke check
curl -X POST localhost:8099/demo/reset         # back to 18:20, ward re-seeded
curl localhost:8099/demo/script                # the beat list, without running it
```

One synthetic patient (Alma Whitfield, CHF, bed 412-A) at a 19:00 shift change. The run
proves each guard rather than narrating it: the read-back is refused while a required
field is empty, the close is refused with 12 blockers, the SBAR refuses to send without
an explicit ask, and the unanswered page re-routes to the backup provider.

## Ward clock

Ward time runs **60x** wall time, so a 10-minute re-route fires in 10 seconds on stage.
Nothing in the app calls `time.time()` — everything calls `clock.now()`.

```bash
curl -X POST localhost:8099/clock/speed/120    # faster
curl -X POST localhost:8099/clock/jump/11      # skip 11 ward minutes onto a deadline
curl -X POST localhost:8099/clock/pause        # freeze mid-demo to talk
```

## Modules

| File | Feature | Does |
|---|---|---|
| `modules/directory.py` | — | **The registry:** patients, RNs, assignments, the records join, the RN panel, `/schema` |
| `schemas.py` | — | Typed request/response models and the id patterns (`P-###`, `X-##`) |
| `modules/handoff.py` | F1, F2 | I-PASS draft from the records with a source on every value; pinned safety block; read-back comparison; per-item sign-off; close rules |
| `modules/tasks.py` | F3 | Derives carry-over tasks from the MAR, pending labs and open orders; one owner each; 30-minute overdue alerts |
| `modules/escalation.py` | F4 | SBAR composer; Background filled from vitals, labs and meds; Recommendation required |
| `modules/messaging.py` | F5, F6 | Message state trail; 10-minute re-route to the backup; focus mode holds routine traffic and releases a digest |
| `modules/oversight.py` | F8 | Charge board, unit report, shift-end nudges, aide observations into the next draft |
| `modules/extras.py` | F7, F9 | Family summary, speak-up concerns, unit transfers, incident linking |
| `scheduler.py` | — | The one background loop: re-routes, overdue tasks, auto-drafts, nudges |
| `seed.py` | — | The synthetic ward, seeded with deliberate gaps so there is something to catch |

## Guards worth demonstrating

| Guard | Requirement | How to show it |
|---|---|---|
| A draft can't be handed over with a required field empty | FR-1.3 | `POST /handoffs/{id}/readback` before filling `baseline_weight` → 409 |
| Every agent-filled value shows its source | FR-1.4, NFR-3 | `source` on every field in `GET /handoffs/{id}` |
| A handoff can't close with items unacknowledged or a task unowned | FR-2.3, FR-3.3 | `GET /handoffs/{id}/close-check` → `blockers` |
| An SBAR can't be sent without the ask | FR-4.1 | `POST /messages/{id}/send` with no Recommendation → 422 |
| Nothing sends itself | FR-4.4, NFR-1 | Send is always a separate human call |
| An unanswered urgent page re-routes | FR-5.2 | Send urgent, wait 10s, re-read the message |

## Seeded gaps

The ward is built so the demo has real things to catch: a **pending troponin** on Alma, a
**missed enoxaparin** dose on Dmitri, a **critical potassium of 3.1**, an **SpO2 limit
dropped 92% → 88%** and a **monitor silenced for 15 minutes**, an aide note about **new
confusion**, and a **turn 20 minutes overdue**. `baseline_weight` has no record behind it,
so it is always the missing required field.

## What a UI needs

REST for state changes, `ws://host:8099/events` for the live feed. Every event is
`{ch, t, text, data}` — `ch` is one of `handoff`, `task`, `message`, `safety`, `focus`,
`oversight`, `clock`, `demo`, `extra`. `GET /events/recent` replays the last 300 so a
screen can attach late and still render.

## Checks

```bash
bash tools/smoke.sh localhost:8099    # 27 checks, one per module and guard
python3 tools/watch.py localhost:8099 # colored feed from another terminal
```

## Walkthrough UI (`/ui`)

Thirteen steps through one shift change. Each one calls the real backend and shows the real
response — the guards are demonstrated, not described. Steps are tagged:

* **DETERMINISTIC** (teal) — runs today, no model involved.
* **AI INFERENCE NEEDED** (purple) — a model is required. The card shows what happens today
  without one, what the model must do, which tools it would call, and a **sample response**.

The ward clock is **paused on load**, so the shift doesn't race past while you read. "Resume
ward clock" runs it at 60x; the re-route step advances it explicitly either way.

## NemoClaw / OpenClaw integration

The agent layer is not built. This is the seam it plugs into.

| Endpoint | Purpose |
|---|---|
| `GET /agent/tools` | OpenAI-style `tools[]` (JSON Schema). Paste into a `/v1/chat/completions` request. |
| `POST /agent/call` | Run one tool. Returns `{role:"tool", content, approx_tokens, truncated}` — drop straight into the history. |
| `GET /agent/inference-points` | The six places a model is genuinely needed, with sample responses. |

Six tools, not fifteen: `get_patient_snapshot`, `get_care_team`, `get_handoff_draft`,
`list_open_items`, `search_notes`, `submit_analysis`. Two rules from `docs/onboarding/00-agents-101.md` are
enforced in code:

* **Summarize, never dump.** Every result is capped at 1,200 chars and reports its token
  cost. A tool result is re-prefilled on every later turn of the loop, so a 4,000-row dump
  is paid for repeatedly. `get_patient_snapshot` returns ~90 tokens, not the raw tables.
* **Few tools, tight descriptions.** Fewer tools select better.

`submit_analysis` is how the model's finding re-enters the system. It records a **proposal**
and emits a safety event — it changes no care and sends nothing. That keeps NFR-1 true even
once the agent is wired in.

### Two things to settle when wiring it up

1. **Sandbox egress.** OpenClaw runs inside OpenShell with deny-by-default egress, so the
   gateway policy needs a rule allowing the sandbox to reach this backend's host and port.
   Without it the tools return nothing and the failure looks like a model problem.
2. **Where the tools execute.** Either the runtime calls `POST /agent/call` over HTTP (needs
   the rule above), or the tools are defined as OpenClaw exec tools that curl localhost. The
   manifest is the same either way.

## Where a model is actually needed

| | Step | Today | Needs a model for |
|---|---|---|---|
| AI-1 | Draft | Free-text notes are copied in verbatim | Turning shift notes into I-PASS claims with a pointer to the source sentence |
| AI-2 | Read-back | `STUB` — keyword match; "K+" never matches "potassium" | Semantic comparison, so a paraphrase counts and a real omission is caught |
| AI-3 | Ranking | Sorted by due time; a chart review ranks beside a missed dose | Ranking by clinical consequence |
| AI-4 | SBAR | Template assembly; Background is a row dump | Prose a tired provider reads in ten seconds |
| AI-5 | Inconsistency | **Not implemented at all** | Catching "stable, no concerns" when the records disagree |
| AI-6 | Family | Template, 3-word glossary, language stored but unused | 6th-grade reading level in the patient's own language |

AI-5 is the one with no deterministic version — it is the clearest argument for the agent.
