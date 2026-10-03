# CareChart frontend ↔ ShiftGuard backend integration — design

**Date:** 2026-10-03
**Branch:** `feat/import-gb10-backend`
**Status:** design, revised 2026-10-03 after the GB10 agent brief. No implementation has started.

**Revision note:** the agent layer was a non-goal in the first draft. The project owner then
required it, pinging Nemotron hosted locally on the GB10. Deployment target moved from
localhost to the GB10, and testing was explicitly scoped down. Sections affected: Non-goals,
Agent layer (new), Deployment (new), Testing.

## Context

Two halves of the project were built independently and have never been connected.

- `frontend/` is **CareChart**: a React 19 / Vite 6 prototype of five nurse-handoff screens.
  It makes **zero network calls**. Every value comes from fixtures in `src/model.js`, and
  session state is persisted to `localStorage` under `carechart-demo-v1`.
- `backend/` is the **ShiftGuard mock backend** imported from the GB10 box on this branch:
  FastAPI on `:8099`, SQLite, nine seeded patients (`P-101`…`P-109`; `SCHEMA.md` says ten,
  the live API returns nine), a 60x ward clock, a `/events` WebSocket
  and a 13-beat `/demo/run`. Every endpoint traces to a numbered requirement (FR-x.y).

This branch **replaced** the earlier hexagonal backend (pure domain + `HandoffService` +
`FlaggingEngine` with two rules, driven by a CLI). None of that code exists here. Any plan
written against `app/domain/`, `app/application/` or `python -m app` is obsolete.

### The two halves were designed for each other

`backend/SCHEMA.md` states that patient **P-109 Theresa Vance** is "the team's handoff script
as structured records: bed 7, day 3 post-op, sedated and ventilated". Verified against the
live API, five of the six transcript lines in `frontend/src/model.js` are backed by real rows:

| `model.js` transcript line | Backend record |
|---|---|
| "Sedation on propofol, RASS minus two overnight" | `sedation`: propofol 20 mcg/kg/min, RASS -2 at 06:00 |
| "Restraints came off at midnight and she settled" | `restraint_events`: 19:00 applied, 00:05 removed |
| "New peripheral line in the left forearm at 23:00" | `devices`: peripheral iv, left forearm, placed 23:00 by N-02 |
| "Family called around 02:00" | `patients.family_updated_at` = 02:00 |
| "PEEP went up from 5 to 8 at about 03:40" | `vent_settings`: 2 rows, 03:40 PEEP 5→8 |
| "Vitals have been stable since" | derived `severity` = "stable" |

The demographics match too: `age` 58, `sex` F, `bed` "7", derived `post_op_day` 3,
`fall_risk` "HIGH". Only `mrn` differs, which `SCHEMA.md` says is deliberate — the script's
partial MRN was not reused.

## Goal

Wire the full handoff lifecycle in the CareChart UI to the live backend: patient list,
draft, required-field entry, coverage check, acknowledgement and close. Retire the handoff
fixtures and `localStorage` handoff state.

### Non-goals

- **Speech-to-text.** There is still no microphone capture. The canned `transcript` array
  remains the sample narrative, and the UI keeps labelling it a demo.
- **The `/events` WebSocket feed.** Deferred; it needs a UI surface the five designs do not
  contain. The UI polls instead.
- **The five other inference points.** Only AI-2 (semantic read-back comparison) is wired.
  AI-1, AI-3, AI-4, AI-5 and AI-6 stay deterministic.
- **OpenClaw / OpenShell sandboxing.** The agent loop calls vLLM directly from the backend
  process, so no gateway egress rule is needed. Running the loop inside OpenShell is later work.
- **Messaging, escalation, oversight, extras** (F4–F9). Backed by the API, not in the UI.

## Verified behaviour

Captured from the running service, not inferred.

```
GET  /clock                                   → {"ward_time":"18:20","speed":"60x"}
GET  /patients/P-109                          → bed 7, age 58 F, post_op_day 3,
                                                 fall_risk HIGH, weight_stale true
POST /handoffs/P-109/draft?giver=N-02&receiver=N-01
                                              → HO-109-xxxx, status "drafting",
                                                 missing_required ["Today's weight"],
                                                 safety_block 9 fields, ipass 5 sections
POST /handoffs/{hid}/readback  (while drafting)→ 409 {"error":"handoff not ready",
                                                      "missing":["Today's weight"]}
PATCH /handoffs/{hid}/fields/baseline_weight  → status "ready", missing_required []
POST /tasks/derive/P-109                      → 6 tasks, all unowned, 2 overdue
GET  /handoffs/{hid}/close-check              → closed false, 16 blockers
```

`action_list` is `[]` until `POST /tasks/derive/{pid}` runs. The draft does not derive tasks.

### A defect this surfaced

`POST /handoffs/{hid}/readback` with the UI's real transcript returned **1 gap and 2 covered**,
and both "covered" items are genuine omissions:

- `allergy history has NOT been taken` was scored covered. The transcript never mentions
  allergies. It matched on the word **"been"**, from "Vitals have been stable since".
- `PEEP raised 5→8 at 03:40 with no provider contact recorded` was scored covered. The
  transcript says PEEP went up and she tolerated it; it says nothing about provider contact.

`_covered()` keeps any word longer than 3 characters that is not in a 19-word `STOP` set, then
counts a single hit as coverage. This is the `STUB` the module documents (inference point AI-2).
Wired as-is, the review screen would tell a nurse her narrative was complete when it was not.

## Agent layer (AI-2)

Per `integration/AGENT_PROMPT.md` and `GET /integration/config` on the box, both verified live.

| | |
|---|---|
| Endpoint | `http://127.0.0.1:8001/v1` — loopback on the GB10, so the loop runs **on the box** |
| Model id | `nemotron` (NVIDIA-Nemotron-3-Nano-30B-A3B, NVFP4, `max_model_len` 32768) |
| Params | `temperature: 0`, `max_tokens: 9000`, `tool_choice: "auto"` |
| Reasoning | arrives in `message.reasoning`; **never** echoed back into the history |
| Truncation | `finish_reason == "length"` with empty `content` and no `tool_calls` means the budget went to reasoning — not a model failure |
| Turn cap | 6 |

**Do not use `:8000`.** `qwen3.6` is served without `--enable-auto-tool-choice`, so
`tool_choice: "auto"` returns HTTP 400. Verified: both containers are up, and the registry
router on `:9000` is **not running**, so the direct `:8001` path in the brief is the only
working one. The system prompt is read from `integration/agent_config.json` rather than copied
into code — `tools/smoke.sh` already asserts it stays byte-identical to `evals/scenarios.json`.

### Why coverage must be asynchronous

The brief's measured cost for read-back comparison is **~55,000 reasoning characters and ~258
seconds**. A nurse cannot wait on that, and neither can an HTTP request.

So `POST /handoffs/{hid}/coverage` returns the **deterministic** result immediately and starts
the agent run in the background. `GET /handoffs/{hid}/coverage` returns the latest state, and
the UI polls it every 3s while `status == "running"`, swapping `engine` from `"deterministic"`
to `"nemotron"` when the model lands. If the run times out, truncates on reasoning, or returns
unparseable JSON, the deterministic result stands and `engine` stays `"deterministic"`.

The screen always labels which engine produced what it shows. A keyword match must never be
presented as semantic comparison.

## Deployment — GB10

The backend already runs on the box as `dell`: `~/dir/shiftguard-backend`, uvicorn on
`0.0.0.0:8099`, reachable at `http://172.20.65.125:8099`. That directory is **not a git
repository** and is ahead of this branch by four files plus `integration/` and
`app/static/evals.html`, so the first task brings it under version control before anything
changes.

The frontend is built **on the box** (node v22.23.3 is installed; the local v20.18.0 trips
`@vitejs/plugin-react`'s engine floor) and served by the same FastAPI process as a static
mount. One process, one port, no CORS, no second server, no SSH tunnel — the app is at
`http://172.20.65.125:8099/app`.

`:8099` has **no authentication**, matching the warning in `docs/gb10-access.md`. Acceptable
for synthetic data on a lab network; it must not carry real PHI.

## Architecture

```
  browser                       GB10 172.20.65.125
┌──────────────────┐          ┌─────────────────────────────┐
│ Vite :5173       │          │ FastAPI (uvicorn)            │
│                  │  REST    │  /patients  /handoffs        │
│  App.jsx         │ ───────> │  /tasks     /clock           │
│   └─ api.js      │          │                              │
│      (all I/O +  │          │  SQLite shiftguard.db        │
│       mapping)   │          │  ward clock 60x              │
└──────────────────┘          └─────────────────────────────┘
```

`CORSMiddleware(allow_origins=["*"])` is already configured in `app/main.py`. Served from the
same origin on the box, CORS is not even exercised; it only matters for local development
against the box. **No Vite proxy is needed.** Base URL comes from `VITE_API_BASE`, defaulting
to the empty string (same origin), set to `http://172.20.65.125:8099` for local dev.

### Lifecycle

```
prepare   POST /tasks/derive/{pid}          → carry-over tasks exist
          POST /handoffs/{pid}/draft        → hid, safety_block, ipass, missing_required
          PATCH /handoffs/{hid}/fields/{k}  → clears the 409 guard, status → ready
review    POST /handoffs/{hid}/coverage     → covered[], gaps[]        (NEW endpoint)
                                            no status precondition; repeatable
incoming  POST /handoffs/{hid}/readback     → receiver's read-back, status → in_progress
          POST /tasks/{tid}/assign          → tasks get owners
          POST /handoffs/{hid}/ack          → per-item acknowledgement
          GET  /handoffs/{hid}/close-check  → blockers[] or closed

The read-back belongs to the incoming nurse, not to delivery: `/readback` records what the
receiver said back, so it fires on the incoming screen. Delivery itself is a UI transition.
```

## Backend changes

### 1. New endpoint: `POST /handoffs/{hid}/coverage`

Request `{text: str, actor: str = "N-02"}`, response `{handoff, covered[], gaps[], note}` —
the same shape `/readback` returns.

It reuses `_expected()` and `_covered()` unchanged and is **non-mutating**: it does not set
`status`, does not persist `readback`, and emits no `handoff` event. It also has **no status
precondition** — unlike `/readback` it works while the handoff is still `drafting`, so the
outgoing nurse sees her gaps before she has filled the required weight field. That is the whole reason
it exists rather than reusing `/readback`:

- `/readback` is the **receiving** nurse's formal read-back. It transitions
  `ready → in_progress` and stores the text as the record of what was said back.
- `/coverage` is the **outgoing** nurse checking her own draft narrative before she delivers
  it. She will run it repeatedly as she edits, and none of those runs are a read-back.

It emits one `safety` event per gap, as `/readback` does, so the console log still shows the
catch. Roughly 20 lines in `app/modules/handoff.py`.

### 2. Tighten `_covered()` — the fallback path only

Nemotron now does the real comparison, so this is no longer the fix for AI-2; it is hardening
of the path the UI falls back to when the model is unreachable. Still worth the six lines,
because a fallback that reports genuine omissions as covered is worse than no fallback.

- Expand `STOP` from 19 words to a general English stop list (~80 words), including "been",
  "have", "with", "about", "after", "that", "this", "from", "were", "came".
- Raise the minimum keyword length from `> 3` to `>= 5`.
- Require **two** distinct keyword hits rather than one.
- Keep the `keys[:6]` cap.

Expected effect on the verified run: the allergy contingency and the PEEP contingency both
become gaps even without the model. The review screen is additionally badged "deterministic match" so it never
claims semantic comparison it does not do.

This is a heuristic, not a fix for AI-2. "K+" still will not match "potassium". The semantic
comparison remains an open inference point and needs its own spec.

## Frontend changes

### New: `src/api.js`

The only module that performs I/O. One function per endpoint, plus the mapping functions.
Preserves HTTP status and the parsed `detail` body on failure as a typed `ApiError`, because
409 carries `missing[]` that the UI must render as a prompt rather than an error.

```
listPatients()                      getHandoff(hid)
draftHandoff(pid, giver, receiver)  editField(hid, key, value, actor)
checkCoverage(hid, text)            postReadback(hid, text, actor)
deriveTasks(pid)                    assignTask(tid, ownerId)
ackItem(hid, kind, ref, actor)      closeCheck(hid)
getClock()
```

### Changed: `src/model.js`

Delete the `patients`, `changes` and `tasks` fixtures. **Keep** `transcript` — there is no STT,
so it stays the sample narrative submitted to `/coverage`. Keep the pure helpers `timecode`,
`counts` and `decide`. `initialRecords()` is reshaped: per-patient records are keyed by backend
`patient_id` (`P-101`…`P-109`) and carry `hid`, `status` from the server, and client-only UI
state.

### Changed: `src/App.jsx`

The largest piece of work. It currently holds all lifecycle state locally and hydrates from
`localStorage`. It gains:

- A `hid` per patient, obtained from the draft call.
- Loading and error state per screen.
- Server `status` (`drafting | ready | in_progress | closed`) as the source of truth for which
  screen a patient is on, replacing the local `stage` string where they overlap.
- A required-field prompt driven by `missing_required`, which the designs do not currently
  contain: a labelled input that PATCHes `baseline_weight`.
- `blockers[]` rendered as the reason close is disabled.

`localStorage` is retired for handoff state. It may stay for pure UI preferences (sort order,
selected tab) — those never need to reach the server.

### Mapping

| UI field | Backend source |
|---|---|
| patient `name`, `bed`, `mrn` | `name`, `bed`, `mrn` |
| patient `age` | `` `${age} ${sex}` `` → "58 F" |
| patient `context` | `dx` + `post-op day ${post_op_day}` |
| patient `attention` | `fall_risk === "HIGH" \|\| weight_stale` |
| review card `title` | gap item `text` |
| review card `lines[]` | field `value` split on `;` |
| review card `source` | field `source`, e.g. `vent_settings (2 rows)` |
| review card `severity` | `safety_block` → red, `contingency` → amber, `task` → teal |
| task `time`, `text`, `owner`, `status` | `action_list[]` `due`/`due_rel`, `text`, `owner`, `status` |
| all clock displays | `ward_time`, replacing the hardcoded `06:47` / `07:30` / `08:00` |

The UI's four `changes` fixtures (potassium/KCl, norepinephrine, lab orders, family follow-up)
have no backend counterpart — P-109's seeded gaps are allergy history, stale weight, the PEEP
escalation and the restraint reassessment. That fixture copy is replaced by live content.

## Error handling

With the fixtures deleted there is nothing to fall back to, so each screen renders an explicit
unreachable state naming the base URL, with retry. A fixture fallback is specifically rejected:
silently showing demo data when the backend is down is how a demo lies.

- **The required-field prompt** is driven by `missing_required` on the draft response, not by a
  409. Since `/coverage` has no status precondition, 409 is reachable only from `/readback` on
  the incoming screen; there it is not an error either — render `missing[]` and keep the
  read-back disabled.
- **422** (validation, e.g. a role/prefix mismatch) renders the FastAPI detail verbatim; it means
  the client built a bad request.
- **404 on a `hid`** means the database was re-seeded underneath the UI (`/demo/reset` drops it).
  Clear the stored `hid` and return the patient to prepare.

## Ward clock staging

The clock seeds at 18:20 for the Alma 19:00 shift change, but P-109's handoff is ~07:00, so her
derived tasks read "12h05m ago". A setup script calls `POST /clock/pause` then
`POST /clock/jump/{minutes}` to land near 06:45 before the CareChart demo. `POST /demo/reset`
returns the ward to 18:20 and re-seeds.

## Testing

Deliberately minimal, at the project owner's instruction. The backend already ships its own
acceptance test, so the work is to run it rather than to write a parallel suite.

- **The eval suite is the acceptance test for the agent layer.** `evals/run.py`, 5 scenarios,
  expect 48/50. `--only S5` is the refusal guardrail and runs in ~8s; it is the one to run most
  often, because a model that claims it paged a doctor is the failure that ends the project.
- **Four new `tools/smoke.sh` checks** — the existing harness, same `chk` style: coverage
  returns deterministic immediately, the `engine` field is present, the allergy and PEEP
  contingencies are gaps, and `/app` serves the built frontend.
- **One new frontend test file** for `map.js`, covering null field values and severity mapping.
  No new test infrastructure; `node --test`, as the repo already does.
- `npm run build` must run before `npm run test:sites` — that suite asserts on gitignored
  `dist/` output and fails on a clean tree otherwise.

No pytest is added: the backend has no Python test suite on this branch and does not need one
for this work.

## Risks

- **`App.jsx` size.** At 1,872 lines, threading async state through it is the main source of
  risk. If it resists, extracting the lifecycle into a hook is in scope; broader refactoring
  is not.
- **The matcher stays a heuristic.** Tightening reduces false "covered" results on the known
  transcript; it does not generalise. Any claim beyond "deterministic keyword match" would be
  false.
- **Re-seeding invalidates stored ids.** `/demo/reset` drops the database, so any `hid` the UI
  holds 404s. Handled above, but it will be hit during development.
- **No auth, no PHI.** The backend has no authentication by design. Synthetic patients only.
