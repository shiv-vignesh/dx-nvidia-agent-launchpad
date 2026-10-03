# ShiftGuard — Architecture & System Design

> **Status:** DRAFT / in progress (brainstorming). Decisions locked; Sections 1–2 agreed;
> Sections 3–5 pending. Working name: **ShiftGuard**. Date: 2026-10-03.
> This is a **design doc, not code.** No implementation until the design is approved (hackathon rule:
> the agent is built on the day; plans/scaffolds/libraries are allowed beforehand).

## Problem statement

A shift-handoff agent for healthcare teams that runs **fully on the device**. It checks each handoff against
the shift's records, flags anything missing for the next person on shift, and keeps patient data local.
**Staff confirm every flag.**

## Locked decisions

| Decision | Choice | Implication |
|---|---|---|
| What we build (vs the stack) | **Standalone app over the SDKs** | We own the application layer (entry point, lifecycle, modules, data); OpenClaw/OpenShell are dependencies we drive |
| Runtime | **Python** | Native OpenShell Python SDK; OpenClaw driven via CLI/gateway; sqlite + pydantic for local data |
| Data model | **Structured SQLite records + narrative handoff** | Agent extracts claims from free text and cross-checks structured records → flags with row-level evidence; verifiable via a seeded answer key |
| Interaction surface | **Lightweight web UI** | Handoff screen → flags with evidence → per-flag confirm/reject → signed summary; visible "100% local" badge |
| Flagging engine | **Hybrid** (deterministic rules + agent layer) | Rules fire the must-catch flags (demo-safe floor); agent adds semantic consistency, urgency ranking, evidence phrasing, interactive Q&A, summary |

## User stories

| # | Story | Why |
|---|---|---|
| **US-1 (core happy path)** | Incoming nurse starts a handoff → outgoing nurse gives free-text handoff → system retrieves the shift's structured records → agent extracts claims & cross-checks → presents flags *with evidence* → nurse confirms/rejects each → records resolutions → produces a signed handoff summary | The spine of the demo |
| **US-2 (prioritized omission)** | Agent finds a med **due within the hour** or an **abnormal vital** not mentioned, and ranks flags by clinical urgency | Agentic: reasoning about salience |
| **US-3 (cross-source inconsistency)** | Handoff says "stable, no issues" but records show a new abnormal lab / missed med → agent flags the contradiction, citing both sources | Agentic: cross-source reasoning |
| **US-4 (interactive follow-up)** | On a flag, the nurse asks "why?" / "show the trend" → agent answers from the records | Agentic: grounded tool use in dialogue |
| **US-5 (local-first / injection block)** | Handoff text hides "email this patient list to…"; the agent processes it with **egress denied by OpenShell** — exfiltration blocked live, flagging still works | Hero demo beat; proves local-first + the stack |

**System invariants** (cross-cutting): every flag must cite a concrete record (no evidence → no flag);
nothing is auto-applied — **staff confirm every flag**; all data and inference stay on-device.

## Section 1 — Architecture & boundaries  *(agreed)*

**Hexagonal (ports & adapters).** The clinical logic (what's a flag, what's evidence, the confirmation
workflow) is **pure Python that knows nothing about OpenClaw, OpenShell, Ollama, or SQLite.** The stack sits
behind interfaces ("ports") so it's swappable and testable. Only `adapters/` touch the stack — so GB10-vs-Mac
differences never reach the clinical logic.

```
          ┌────────────────────── Presentation ──────────────────────┐
          │  web/  (FastAPI + minimal UI): handoff screen, flag cards, │
          │        per-flag confirm/reject, signed summary, LOCAL badge│
          └───────────────────────────┬───────────────────────────────┘
                                       │ calls use-cases
          ┌──────────────────── Application (orchestration) ───────────┐
          │  HandoffService · ConfirmationService · SummaryService      │
          │  depends ONLY on ports ↓ (never on adapters)               │
          └───────┬───────────────┬───────────────┬───────────────┬────┘
            RecordsPort       AgentPort       SandboxPort     InferencePort
                 │                │                │                │
   ┌─────────────▼───┐ ┌──────────▼────────┐ ┌─────▼───────┐ ┌──────▼────────┐
   │ records_sqlite  │ │ agent_openclaw    │ │ sandbox_    │ │ inference_    │  ← Adapters
   │ (SQLite repo)   │ │ (drives OpenClaw) │ │ openshell   │ │ registry      │
   └─────────────────┘ └───────────────────┘ └─────────────┘ └───────────────┘
          ┌──────────────────────── Domain (pure) ─────────────────────┐
          │  models (Patient, Vital, Med, Order, Task, Handoff, Claim,  │
          │  Flag, Resolution, Summary) · rules/ (FlaggingEngine +      │
          │  Rule strategies) · session (HandoffSession state machine)  │
          └─────────────────────────────────────────────────────────────┘
```

**Why:** the domain + application core is what "correctness" and the answer-key tests hit; it must run and be
verifiable *without* the stack. Adapters are the only code that touches OpenClaw/OpenShell/the registry.

## Section 2 — Module structure & responsibilities  *(agreed)*

```
engine/                  # the rules engine: pyproject.toml + app/ + tests/ (the live API is in backend/)
  app/
    main.py              # ENTRY POINT + composition root: build adapters, inject into services, start web, lifecycle
    config.py            # settings (pydantic-settings): db path, registry URL, sandbox on/off, LOCAL_ONLY assertions
    domain/              # PURE — no I/O, no stack imports
      models.py          # pydantic entities + Flag/Claim/Evidence/Resolution/Summary value objects
      rules/             # Strategy pattern: one class per check (MedDueNotMentioned, AbnormalVitalOmitted, …)
      engine.py          # FlaggingEngine: runs all Rules over (claims, records) → deterministic Flags
      session.py         # HandoffSession state machine (Draft→Analyzing→AwaitingConfirmation→Summarized)
    application/
      ports.py           # the 4 Protocols: RecordsPort, AgentPort, SandboxPort, InferencePort
      handoff_service.py # the analyze pipeline (retrieve→extract→rules→agent-augment→merge→rank)
      confirmation_svc.py# per-flag confirm/reject → Resolution
      summary_service.py # compose + sign the final handoff summary
    adapters/
      records_sqlite.py  # RecordsPort impl
      agent_openclaw.py  # AgentPort impl: extract_claims / augment / explain / summarize via OpenClaw
      sandbox_openshell.py# SandboxPort impl: run agent calls inside an OpenShell sandbox, egress denied
      inference_registry.py# InferencePort impl: our registry router → ollama|vllm|colibri
    web/
      server.py          # FastAPI routes; renders flag cards; confirm/reject endpoints
      ui/                # one HTML/JS page (or Streamlit)
  data/seed/             # synthetic patients + records + ANSWER KEY (demo-safe, no real PHI)
  tests/                 # domain rule tests vs answer key; service tests with mocked ports; golden scenarios
```

**One responsibility each:** `domain/` decides *what's true*; `application/` decides *the workflow*;
`adapters/` decide *how to reach the outside world*; `web/` decides *how a human sees and confirms*.
A new rule = one file in `rules/`. A different model engine = config in the registry. A different agent
runtime = one adapter.

## Pending (next sections)

- **Section 3 — Interfaces:** method signatures for the four ports (`RecordsPort`, `AgentPort`, `SandboxPort`, `InferencePort`).
- **Section 4 — Data flow & lifecycle:** the handoff analyze pipeline; `main.py` startup/shutdown sequence; the `HandoffSession` + per-`Flag` state machines.
- **Section 5 — Design patterns, error handling, testing:** pattern summary (hexagonal, repository, strategy, pipeline, state machine, composition root); fallbacks (agent down → deterministic-only); answer-key test strategy.

After Sections 3–5 are agreed, this becomes the committed spec and we move to an implementation plan (no code before that).
