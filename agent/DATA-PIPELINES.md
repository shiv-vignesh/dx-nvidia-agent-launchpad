# ShiftGuard — Data Model & Agentic Pipelines

> **Status:** EXPLORATORY / brainstorming (not a locked decision). Date: 2026-10-03.
> This explores an **unstructured-first data model** (MongoDB + extraction pipeline) as an
> alternative/extension to the data-model decision in [`ARCHITECTURE.md`](./ARCHITECTURE.md),
> which currently locks **structured SQLite + narrative handoff**. The realism argument below is
> *why we'd reconsider*; the final call stays with the locked-decisions table until changed there.
> Design doc, not code (hackathon rule: agent built on the day).

## Why unstructured-first

Clean structured JSON is a fine starting point, but the **realism** — and the demo's credibility —
comes from messy, real-world clinical artifacts: handwritten SBAR sheets, dictated verbal handoffs,
scanned MARs, lab PDFs, monitor exports, free-text nursing notes. Modeling that pushes us toward a
**document store (MongoDB)** plus an **agentic multi-step extraction pipeline**, rather than rows in
a relational schema.

This generalizes a pattern proven at **IBM TechXchange 2024**: `document → OCR → entity/information
extraction → rules on extracted values → classify`.

## The reusable pipeline skeleton

The IBM pattern maps onto the handoff problem as a 7-stage pipeline. **MongoDB** stores each stage's
output in its own collection (raw blobs · extracted entities · flags), so any stage is **replayable**
and the agent loop is debuggable under time pressure.

```text
1. INGEST       raw unstructured source lands in Mongo (scan, audio, PDF, note)
2. OCR/ASR      local vision/speech model → text              [NeMo / local]
3. EXTRACT      clinical entity + information extraction       [agent + tools]
4. RULES        apply clinical rules to extracted values       [deterministic]
5. CLASSIFY     label the doc / handoff / patient state        [agent]
6. RECONCILE    cross-check handoff vs. shift records           [agent loop ← real agency]
7. FLAG→CONFIRM propose flags w/ evidence → human confirms      [HITL]
```

The **agency** lives in stages 3 and 6: the agent decides *which* sources to pull, *which* tool to
call next, and *whether it has enough evidence* to propose a flag — not a single prompt→answer. This
keeps it from being "a chatbot that reads medical records."

## Five pipeline scenarios

### Scenario 1 — Paper SBAR sheet reconciliation *(OCR; closest to the IBM flow)*

Nurses still hand-write SBAR handoff sheets.

- **Input:** scanned/photographed handwritten sheet.
- **Pipeline:** OCR → extract meds/vitals/tasks/times → rules (*"med in MAR but absent from sheet → omission"*; *"out-of-range vital not mentioned → flag"*) → classify handoff completeness → reconcile against EHR shift records in Mongo → propose flags.
- **Agency:** deciding which EHR records are relevant to each handwritten line.
- **Demo moment:** scanned sheet on screen, extracted entities overlaid as bounding boxes, flags appear beside the gaps.

### Scenario 2 — Verbal handoff transcription + gap-check *(ASR; best NVIDIA-stack fit)*

Verbal handoff is how it actually happens at the bedside.

- **Input:** recorded audio.
- **Pipeline:** local ASR (NVIDIA **NeMo**, purpose-built, runs on GB10) → transcript → entity extraction → reconcile against structured shift records → detect omissions → flag.
- **Agency:** mapping loose spoken phrasing to concrete records; deciding what *wasn't* said that should have been.
- **Demo moment:** someone *speaks* a deliberately incomplete handoff into a mic; live transcript streams, then flags pop (*"no mention of the pending troponin"*). Highest wow-per-second; leans directly on the NVIDIA speech stack = strong local-first story.

### Scenario 3 — Multi-source cross-document reconciliation *(deepest agent loop)*

- **Input:** several unstructured docs per patient in Mongo — MAR scan, free-text nursing notes, lab PDF, monitor/device export.
- **Pipeline:** extract entities from each source → build a per-patient timeline → agent cross-checks the handoff narrative against the *union* of sources via multi-hop lookups → flag contradictions/omissions.
- **Agency:** the agent must *choose* which sources to consult and iterate (lookup → compare → decide if another lookup is needed). Least "LLM-wrapper" of the five.
- **Demo moment:** the agent's tool trace visibly fans out across 3–4 documents to corroborate one flag.

### Scenario 4 — Incoming-shift risk triage *(document classification → prioritized worklist)*

Reframes the output from "completeness" to "prioritization."

- **Input:** unstructured notes across all the incoming nurse's patients.
- **Pipeline:** extract deterioration/sepsis/fall-risk signals → rules → **classify each patient** red/amber/green → produce a ranked worklist, surfacing high-risk omissions first.
- **Agency:** acuity reasoning over noisy notes; ranking under uncertainty.
- **Demo moment:** a ranked worklist with color-coded risk — the most "a manager would pay for this" artifact.

### Scenario 5 — Discharge/transfer packet gap-check *(packet generation + readiness classification)*

- **Input:** the patient's unstructured record set at transfer/discharge.
- **Pipeline:** extract → rules (*"pending lab unresulted," "follow-up not booked," "med reconciliation gap"*) → classify discharge readiness → assemble a structured transfer packet + flags for the receiving unit.
- **Agency:** judging "ready vs. not ready" from incomplete evidence.
- **Demo moment:** a generated transfer packet with a readiness verdict and a punch-list of blockers. Highest raw business value, but scope drifts beyond *shift* handoff.

## Scoring against the judging criteria

Four criteria, equally weighted (25% each), scored 1–5.

| Scenario | Technical execution | Business value | Local-first | Demo quality | **Total /20** |
|---|:--:|:--:|:--:|:--:|:--:|
| 1. Paper SBAR OCR | 4 | 4 | 5 | 4 | **17** |
| 2. Verbal handoff ASR | 4 | 4 | **5** | **5** | **18** |
| 3. Multi-source reconcile | **5** | 5 | 4 | 3 | **17** |
| 4. Risk triage classify | 4 | **5** | 4 | 5 | **18** |
| 5. Discharge packet | 3 | 5 | 4 | 3 | **15** |

**Key swings:**

- **ASR (2)** maxes *local-first* and *demo* — NeMo ASR is a native GB10 win and live speech is the most visceral demo beat.
- **Multi-source (3)** maxes *technical* (genuine iterative agent loop) but is the hardest to land cleanly on stage under time pressure.
- **Triage (4)** maxes *business value* — prioritization is directly measurable (minutes saved, missed-deterioration rate).

## Recommendation — a hybrid spine, not one scenario

The criteria are equally weighted, so the winner maximizes the **minimum** across all four. No single
scenario does that — but a thin vertical slice combining **2 + 3 + 4** does, and all three share the
same pipeline and Mongo schema:

> **Verbal handoff (ASR input)** → **multi-source reconciliation (agent loop)** →
> output as a **risk-ranked worklist (classification)**, every flag human-confirmed.

This delivers on all four criteria at once:

| Criterion | How the hybrid wins it |
|---|---|
| Technical execution | Real, non-wrapper agent loop (Scenario 3) |
| Business value | Risk-ranked worklist a manager would pay for (Scenario 4) |
| Local-first | ASR on GB10 via the NVIDIA stack (Scenario 2) |
| Demo quality | Speak → flags appear → ranked worklist (2 + 4) |

**Build order:** ship Scenario 2's path end-to-end first as the spine; branch 3 and 4 off it if time
allows. This mirrors the "thin vertical slice" principle in the breakdown doc.

## Open items before this can supersede the locked decision

- **Reconcile with [`ARCHITECTURE.md`](./ARCHITECTURE.md):** the locked data-model row says *structured SQLite + narrative handoff*. Adopting Mongo/unstructured means updating that table and the `adapters/records_*` plan.
- **Collection schema:** define `raw` / `extracted` / `flags` collections + the answer-key representation for seeded demo scenarios.
- **Tool surface:** which pipeline stages are *agent tools* vs. *deterministic application logic* (e.g., OCR/ASR = tool; rules engine = deterministic).
- **Local models:** confirm the OCR/ASR models that run on GB10 (NeMo ASR; a local vision/OCR model for scans) — flag anything to verify against official NVIDIA docs.
